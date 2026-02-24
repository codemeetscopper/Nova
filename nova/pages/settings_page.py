from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from nova.core.config import SettingItem
from nova.ui.components.settings_widgets import BaseSettingWidget, BoolSettingWidget, create_setting_widget

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_font(path: str, app) -> None:
    if not path:
        return
    p = Path(path)
    if p.exists() and p.suffix.lower() in (".ttf", ".otf"):
        try:
            from PySide6.QtGui import QFont, QFontDatabase
            from nova.core.style import StyleManager
            fid = QFontDatabase.addApplicationFont(str(p))
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                StyleManager.set_font_family(families[0])
                app.setFont(QFont(families[0]))
        except Exception as exc:
            _log.warning("Failed to apply font '%s': %s", path, exc)


def _reapply_style(app, ctx) -> None:
    try:
        accent = ctx.config.get_value("appearance.accent", "#0088CC")
        theme  = ctx.config.get_value("appearance.theme",  "dark")
        ctx.style.initialise(accent, theme=theme)
        qss_path = Path(__file__).parent.parent / "resources" / "nova.qss"
        if qss_path.exists():
            ctx.style.apply_theme(app, qss_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _log.warning("Failed to reapply style: %s", exc)


# ---------------------------------------------------------------------------
# SettingRow
# ---------------------------------------------------------------------------

class SettingRow(QWidget):
    def __init__(self, key: str, item: SettingItem, ctx,
                 on_plugins_path_changed: Optional[Callable[[str], None]] = None,
                 on_style_changed: Optional[Callable[[], None]] = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._key = key
        self._item = item
        self._ctx = ctx
        self._on_plugins_path_changed = on_plugins_path_changed
        self._on_style_changed = on_style_changed
        self.setObjectName("SettingRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(20)

        # Left: name + description (expands)
        info = QVBoxLayout()
        info.setSpacing(2)
        name_lbl = QLabel(item.name)
        name_lbl.setObjectName("SettingName")
        desc_lbl = QLabel(item.description)
        desc_lbl.setObjectName("SettingDesc")
        desc_lbl.setWordWrap(True)
        info.addWidget(name_lbl)
        info.addWidget(desc_lbl)
        layout.addLayout(info, 3)

        # Right side: control widget
        self._widget: Optional[BaseSettingWidget] = create_setting_widget(item)
        if self._widget is not None:
            self._widget.value_changed.connect(self._on_value_changed)
            if isinstance(self._widget, BoolSettingWidget):
                layout.addWidget(self._widget, 0, Qt.AlignRight | Qt.AlignVCenter)
            else:
                right = QWidget()
                right.setObjectName("SettingRowRight")
                right.setStyleSheet("QWidget#SettingRowRight { background: transparent; }")
                right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                right_layout = QHBoxLayout(right)
                right_layout.setContentsMargins(0, 0, 0, 0)
                right_layout.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
                right_layout.addWidget(self._widget)
                self._widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                layout.addWidget(right, 2)

    def _on_value_changed(self, value: Any) -> None:
        try:
            self._ctx.config.set_value(self._key, value)
        except Exception as exc:
            _log.warning("SettingRow: failed to save '%s': %s", self._key, exc)
            return

        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()

        if self._key in ("appearance.accent", "appearance.theme"):
            if app:
                _reapply_style(app, self._ctx)
            if self._on_style_changed:
                self._on_style_changed()
        elif self._key == "appearance.font":
            if app:
                _apply_font(str(value), app)
                _reapply_style(app, self._ctx)
        elif self._key == "system.plugins_path":
            if self._on_plugins_path_changed is not None:
                self._on_plugins_path_changed(str(value))


# ---------------------------------------------------------------------------
# SettingsPage
# ---------------------------------------------------------------------------

_APP_SETTINGS: list[tuple[str, str, str, str, list]] = [
    ("appearance.accent", "Accent Color",
     "Primary accent colour for the application.",
     "colorpicker", ["#0088CC", "#2196F3", "#9C27B0", "#F44336", "#4CAF50", "#FF9800"]),
    ("appearance.theme", "Theme Mode",
     "Colour theme: dark, light, or follow system preference.",
     "dropdown", ["dark", "light", "system"]),
    ("appearance.font", "Font File",
     "Path to a .ttf/.otf font file to apply globally.",
     "fontbrowse", []),
    ("system.plugins_path", "Plugins Folder",
     "Folder where Nova loads plugins from. Changes apply immediately.",
     "folderbrowse", []),
]

_APP_GROUPS: dict[str, str] = {
    "appearance.accent":   "Appearance",
    "appearance.theme":    "Appearance",
    "appearance.font":     "Appearance",
    "system.plugins_path": "System",
}


class SettingsPage(QWidget):
    plugins_path_changed = Signal(str)
    style_changed = Signal()

    def __init__(self, ctx, plugin_manager, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx = ctx
        self._pm = plugin_manager
        self.setObjectName("SettingsPage")

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        container.setObjectName("SettingsContainer")
        self._root = QVBoxLayout(container)
        self._root.setContentsMargins(24, 24, 24, 24)
        self._root.setSpacing(20)

        self._build_app_settings()

        self._plugin_container = QWidget()
        self._plugin_layout = QVBoxLayout(self._plugin_container)
        self._plugin_layout.setContentsMargins(0, 0, 0, 0)
        self._plugin_layout.setSpacing(16)
        self._root.addWidget(self._plugin_container)

        if self._pm:
            self._pm.plugin_imported.connect(lambda _: self._rebuild_plugin_settings())
            self._pm.plugin_loaded.connect(lambda _: self._rebuild_plugin_settings())
            self._rebuild_plugin_settings()

        self._root.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Public API ────────────────────────────────────────────

    def update_plugin_manager(self, pm) -> None:
        self._pm = pm
        if pm:
            pm.plugin_imported.connect(lambda _: self._rebuild_plugin_settings())
            pm.plugin_loaded.connect(lambda _: self._rebuild_plugin_settings())
        self._rebuild_plugin_settings()

    # ── App settings ──────────────────────────────────────────

    def _build_app_settings(self) -> None:
        groups: dict[str, list[tuple[str, SettingItem]]] = {}
        for key, name, desc, typ, values in _APP_SETTINGS:
            group = _APP_GROUPS.get(key, "General")
            try:
                raw_value = self._ctx.config.get_value(key, "")
            except Exception:
                raw_value = ""
            item = SettingItem(
                name=name, shortname=key.split(".")[-1], value=raw_value,
                values=values, description=desc, type=typ,
                accessibility="user", group=group, icon="",
            )
            groups.setdefault(group, []).append((key, item))
        for group_name, rows in groups.items():
            self._root.addWidget(self._build_section(group_name, rows))

    def _build_section(self, title: str,
                       rows: list[tuple[str, SettingItem]]) -> QWidget:
        """Return a section widget: small title label above a card frame."""
        wrapper = QWidget()
        wrapper.setObjectName("SettingSectionWrapper")
        v = QVBoxLayout(wrapper)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        # Section title — sits ABOVE the card
        title_lbl = QLabel(title.upper())
        title_lbl.setObjectName("SectionGroupTitle")

        # Card frame
        card = QFrame()
        card.setObjectName("SettingCard")
        card.setFrameShape(QFrame.NoFrame)
        card_v = QVBoxLayout(card)
        card_v.setContentsMargins(0, 0, 0, 0)
        card_v.setSpacing(0)

        for idx, (key, item) in enumerate(rows):
            if idx > 0:
                sep = QFrame()
                sep.setObjectName("SettingRowSep")
                sep.setFrameShape(QFrame.HLine)
                card_v.addWidget(sep)
            row = SettingRow(key, item, self._ctx,
                             on_plugins_path_changed=self._on_plugins_path_changed,
                             on_style_changed=self._emit_style_changed)
            card_v.addWidget(row)

        v.addWidget(title_lbl)
        v.addWidget(card)
        return wrapper

    def _on_plugins_path_changed(self, new_path: str) -> None:
        self.plugins_path_changed.emit(new_path)

    def _emit_style_changed(self) -> None:
        self.style_changed.emit()

    # ── Plugin settings ───────────────────────────────────────

    def _rebuild_plugin_settings(self) -> None:
        while self._plugin_layout.count():
            child = self._plugin_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        if not self._pm:
            return
        for manifest in self._pm.manifests():
            record = self._pm._records.get(manifest.id)
            if not record or not record.plugin:
                continue
            try:
                plugin_settings = []
                if hasattr(record.plugin, "get_settings"):
                    plugin_settings = record.plugin.get_settings() or []
            except Exception:
                continue
            if not plugin_settings:
                continue
            rows: list[tuple[str, SettingItem]] = []
            for s in plugin_settings:
                full_key = f"plugins.{manifest.id}.{s.key}"
                try:
                    raw_value = self._ctx.config.get_value(full_key, s.default)
                except Exception:
                    raw_value = s.default
                item = SettingItem(
                    name=s.name, shortname=s.key, value=raw_value,
                    values=getattr(s, "values", []) or [],
                    description=getattr(s, "description", ""),
                    type=s.type, accessibility="user", group=manifest.name, icon="",
                )
                try:
                    self._ctx.config.get_value(full_key)
                except KeyError:
                    self._ctx.config.add_user_setting(full_key, item)
                rows.append((full_key, item))
            if rows:
                self._plugin_layout.addWidget(self._build_section(manifest.name, rows))
