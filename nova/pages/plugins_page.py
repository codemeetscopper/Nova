from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

_log = logging.getLogger(__name__)

_COLOR_RUNNING = "#22C55E"
_COLOR_CRASHED = "#EF4444"

_BTN = 24  # unified icon-button size

# Fixed pop colours for action buttons in the plugin list view
_ICON_COLORS = {
    "play":            "#22C55E",  # green
    "stop":            "#EF4444",  # red
    "extension":       "#3B82F6",  # blue
    "refresh":         "#F59E0B",  # amber
    "favorite":        "#EC4899",  # pink
    "favorite_border": "#EC4899",  # pink
    "info":            "#6366F1",  # indigo
    "backup":          "#14B8A6",  # teal
    "delete":          "#EF4444",  # red
}


def _fg1_color() -> str:
    try:
        from nova.core.style import StyleManager
        return StyleManager.get_colour("fg1")
    except Exception:
        return "#888888"


def _fg2_color() -> str:
    try:
        from nova.core.style import StyleManager
        return StyleManager.get_colour("fg2")
    except Exception:
        return "#888888"


def _accent_color() -> str:
    try:
        from nova.core.style import StyleManager
        return StyleManager.get_colour("accent")
    except Exception:
        return "#0088CC"


def _render_plugin_icon(icon_str: str, color: str, size: int = 20):
    try:
        from nova.core.icons import IconManager
        if icon_str.strip().startswith("<"):
            return IconManager.render_svg_string(icon_str, color, size)
        return IconManager.get_pixmap(icon_str or "extension", color, size)
    except Exception:
        return None


def _icon_btn(icon_name: str, tooltip: str, size: int = _BTN,
              parent: QWidget | None = None) -> QPushButton:
    """Flat icon-only button."""
    btn = QPushButton(parent)
    btn.setToolTip(tooltip)
    btn.setFixedSize(size, size)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setObjectName("IconButton")
    _refresh_icon(btn, icon_name, size)
    return btn


def _refresh_icon(btn: QPushButton, icon_name: str, size: int,
                  color: str | None = None) -> None:
    _FALLBACKS = {
        "favorite": "★", "favorite_border": "☆",
        "delete": "✕", "refresh": "↺",
        "backup": "⤓", "info": "ℹ",
        "play": "▶", "stop": "■",
        "check": "✓", "close": "✕",
        "open_in_new": "⇱", "add": "+",
        "extension": "◈",
    }
    try:
        from nova.core.icons import IconManager
        from nova.core.style import StyleManager
        c = color or StyleManager.get_colour("fg1")
        ico = size - 6
        px = IconManager.get_pixmap(icon_name, c, ico)
        if px and not px.isNull():
            btn.setIcon(px)
            btn.setIconSize(QSize(ico, ico))
            btn.setText("")
            return
    except Exception:
        pass
    btn.setText(_FALLBACKS.get(icon_name, "?"))


def _toolbar_btn(icon_name: str, label: str, tooltip: str,
                 parent: QWidget | None = None) -> QPushButton:
    """Flat toolbar button with icon + text."""
    btn = QPushButton(label, parent)
    btn.setToolTip(tooltip)
    btn.setFixedHeight(24)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setObjectName("ToolbarButton")
    try:
        from nova.core.icons import IconManager
        from nova.core.style import StyleManager
        c = StyleManager.get_colour("fg1")
        px = IconManager.get_pixmap(icon_name, c, 14)
        if px and not px.isNull():
            btn.setIcon(px)
            btn.setIconSize(QSize(14, 14))
    except Exception:
        pass
    return btn


# ─────────────────────────────────────────────────────────────
#  Dialogs
# ─────────────────────────────────────────────────────────────

class _NewPluginDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("New Plugin")
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(8)
        self._id = QLineEdit(); self._id.setPlaceholderText("e.g. my_plugin")
        self._name = QLineEdit(); self._name.setPlaceholderText("e.g. My Plugin")
        self._author = QLineEdit(); self._author.setPlaceholderText("e.g. Your Name")
        self._desc = QLineEdit(); self._desc.setPlaceholderText("One-line description")
        form.addRow("Plugin ID:", self._id)
        form.addRow("Name:", self._name)
        form.addRow("Author:", self._author)
        form.addRow("Description:", self._desc)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        import re
        pid = self._id.text().strip()
        if not re.match(r"^[a-z][a-z0-9_]{0,63}$", pid):
            QMessageBox.warning(self, "Invalid ID",
                "Plugin ID must be lowercase letters/digits/underscores and start with a letter.")
            return
        if not self._name.text().strip():
            QMessageBox.warning(self, "Missing Name", "Please enter a plugin name.")
            return
        self.accept()

    def values(self):
        return (self._id.text().strip(), self._name.text().strip(),
                self._author.text().strip() or "Unknown",
                self._desc.text().strip() or "A Nova plugin")


class _InfoDialog(QDialog):
    def __init__(self, manifest, state, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Plugin Info — {manifest.name}")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        def row(label, value):
            h = QHBoxLayout()
            lbl = QLabel(f"<b>{label}</b>"); lbl.setFixedWidth(130)
            val = QLabel(str(value)); val.setWordWrap(True)
            h.addWidget(lbl); h.addWidget(val, 1)
            layout.addLayout(h)

        row("ID", manifest.id); row("Name", manifest.name)
        row("Version", manifest.version); row("Author", manifest.author)
        row("Description", manifest.description)
        row("Category", manifest.category)
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); layout.addWidget(sep)
        row("Enabled", "Yes" if state.enabled else "No")
        row("Favorite", "Yes" if state.favorite else "No")
        row("Run count", str(state.run_count))
        row("Last run", state.last_run or "Never")
        row("Crash count", str(state.crash_count))
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)


# ─────────────────────────────────────────────────────────────
#  Plugin List Item (replaces PluginCard)
# ─────────────────────────────────────────────────────────────

class PluginListItem(QFrame):
    """A single row in the plugin list — compact horizontal layout."""

    start_clicked    = Signal(str)
    stop_clicked     = Signal(str)
    view_clicked     = Signal(str)
    favorite_toggled = Signal(str, bool)
    reload_clicked   = Signal(str)
    export_clicked   = Signal(str)
    delete_clicked   = Signal(str)
    info_clicked     = Signal(str)
    selection_changed = Signal(str, bool)

    def __init__(self, manifest, plugin_manager, parent: QWidget | None = None):
        super().__init__(parent)
        self._manifest = manifest
        self._pm = plugin_manager
        self._is_favorite = plugin_manager.is_favorite(manifest.id)
        self._icon_str = manifest.icon or ""

        self.setObjectName("PluginListItem")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(56)

        h = QHBoxLayout(self)
        h.setContentsMargins(12, 6, 12, 6)
        h.setSpacing(8)

        # Checkbox
        self._checkbox = QCheckBox()
        self._checkbox.setToolTip("Select for bulk actions")
        self._checkbox.setFixedSize(20, 20)
        self._checkbox.toggled.connect(
            lambda checked: self.selection_changed.emit(manifest.id, checked)
        )
        h.addWidget(self._checkbox)

        # Plugin icon
        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(22, 22)
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_lbl.setStyleSheet("background: transparent;")
        h.addWidget(self._icon_lbl)

        # Name + description column
        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(1)

        self._name_lbl = QLabel(manifest.name)
        self._name_lbl.setObjectName("PluginListName")
        info_col.addWidget(self._name_lbl)

        desc_text = manifest.description or "No description"
        if manifest.author:
            desc_text += f"  ·  {manifest.author}"
        self._desc_lbl = QLabel(desc_text)
        self._desc_lbl.setObjectName("PluginListDesc")
        self._desc_lbl.setWordWrap(False)
        info_col.addWidget(self._desc_lbl)

        h.addLayout(info_col, 1)

        # Category badge
        self._cat_lbl = QLabel(manifest.category)
        self._cat_lbl.setObjectName("PluginListCategory")
        self._cat_lbl.setAlignment(Qt.AlignCenter)
        h.addWidget(self._cat_lbl)

        # Status label
        self._status_lbl = QLabel("Offline")
        self._status_lbl.setObjectName("PluginStatusLabel")
        self._status_lbl.setFixedWidth(55)
        self._status_lbl.setAlignment(Qt.AlignCenter)
        h.addWidget(self._status_lbl)

        # Version
        ver_lbl = QLabel(f"v{manifest.version}")
        ver_lbl.setObjectName("PluginListVersion")
        ver_lbl.setFixedWidth(40)
        ver_lbl.setAlignment(Qt.AlignCenter)
        h.addWidget(ver_lbl)

        # ── Action buttons ──────────────────────────────────
        self._play_btn = _icon_btn("play", "Start plugin")
        self._play_btn.clicked.connect(lambda: self.start_clicked.emit(manifest.id))

        self._stop_btn = _icon_btn("stop", "Stop plugin")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(lambda: self.stop_clicked.emit(manifest.id))

        self._view_btn = _icon_btn("extension", "View plugin")
        self._view_btn.setEnabled(False)
        self._view_btn.clicked.connect(lambda: self.view_clicked.emit(manifest.id))

        self._reload_btn = _icon_btn("refresh", "Reload plugin")
        self._reload_btn.clicked.connect(lambda: self.reload_clicked.emit(manifest.id))

        self._fav_btn = _icon_btn("favorite_border", "Pin to sidebar")
        self._fav_btn.setObjectName("FavoriteButton")
        self._fav_btn.clicked.connect(self._on_favorite_clicked)

        self._info_btn = _icon_btn("info", "Plugin info")
        self._info_btn.clicked.connect(lambda: self.info_clicked.emit(manifest.id))

        self._export_btn = _icon_btn("backup", "Export as .zip")
        self._export_btn.clicked.connect(lambda: self.export_clicked.emit(manifest.id))

        self._delete_btn = _icon_btn("delete", "Delete plugin")
        self._delete_btn.setObjectName("DeleteButton")
        self._delete_btn.clicked.connect(lambda: self.delete_clicked.emit(manifest.id))

        # Apply pop colours
        for btn, name in [
            (self._play_btn, "play"), (self._stop_btn, "stop"),
            (self._view_btn, "extension"), (self._reload_btn, "refresh"),
            (self._info_btn, "info"), (self._export_btn, "backup"),
            (self._delete_btn, "delete"),
        ]:
            _refresh_icon(btn, name, _BTN, _ICON_COLORS.get(name))

        # Store for icon refresh
        self._icon_btns: List[Tuple[QPushButton, str]] = [
            (self._play_btn,   "play"),
            (self._stop_btn,   "stop"),
            (self._view_btn,   "extension"),
            (self._reload_btn, "refresh"),
            (self._info_btn,   "info"),
            (self._export_btn, "backup"),
            (self._delete_btn, "delete"),
        ]

        h.addWidget(self._play_btn)
        h.addWidget(self._stop_btn)
        h.addWidget(self._view_btn)
        h.addWidget(self._reload_btn)
        h.addWidget(self._fav_btn)
        h.addWidget(self._info_btn)
        h.addWidget(self._export_btn)
        h.addWidget(self._delete_btn)

        # Initial state
        self._apply_status("Offline", _fg2_color())
        self._update_fav_icon()

    # ── Public API ────────────────────────────────────────────

    @property
    def manifest_id(self) -> str:
        return self._manifest.id

    @property
    def category(self) -> str:
        return self._manifest.category

    def set_active(self, active: bool):
        self._play_btn.setEnabled(not active)
        self._stop_btn.setEnabled(active)
        self._view_btn.setEnabled(active)
        if active:
            self._apply_status("Online", _COLOR_RUNNING)
        else:
            self._apply_status("Offline", _fg2_color())

    def set_crashed(self):
        self._play_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._view_btn.setEnabled(False)
        self._apply_status("Crashed", _COLOR_CRASHED)

    @property
    def is_selected(self) -> bool:
        return self._checkbox.isChecked()

    def set_selected(self, value: bool):
        self._checkbox.setChecked(value)

    def set_favorite(self, value: bool):
        self._is_favorite = value
        self._update_fav_icon()

    def refresh_icons(self) -> None:
        for btn, name in self._icon_btns:
            _refresh_icon(btn, name, _BTN, _ICON_COLORS.get(name))
        self._update_fav_icon()
        self._set_plugin_icon()

    def matches_filter(self, search: str, category: str) -> bool:
        """Return True if this item matches the current filter criteria."""
        if category and category != "All" and self._manifest.category != category:
            return False
        if search:
            s = search.lower()
            if (s not in self._manifest.name.lower()
                    and s not in self._manifest.id.lower()
                    and s not in (self._manifest.description or "").lower()
                    and s not in (self._manifest.author or "").lower()
                    and s not in self._manifest.category.lower()):
                return False
        return True

    # ── Internal ──────────────────────────────────────────────

    def _set_plugin_icon(self):
        px = _render_plugin_icon(self._icon_str, _accent_color(), 20)
        if px and not px.isNull():
            self._icon_lbl.setPixmap(px)
        else:
            self._icon_lbl.setText("?")

    def _apply_status(self, text: str, color: str) -> None:
        self._set_plugin_icon()
        self._status_lbl.setText(text)
        weight = "600" if text != "Offline" else "400"
        self._status_lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: {weight}; background: transparent;"
        )

    def _on_favorite_clicked(self):
        self.favorite_toggled.emit(self._manifest.id, not self._is_favorite)

    def _update_fav_icon(self):
        icon = "favorite" if self._is_favorite else "favorite_border"
        tip = "Remove from sidebar" if self._is_favorite else "Pin to sidebar"
        self._fav_btn.setToolTip(tip)
        _refresh_icon(self._fav_btn, icon, _BTN, _ICON_COLORS.get(icon))


# Keep backward-compat alias for main_window.py imports
PluginCard = PluginListItem


# ─────────────────────────────────────────────────────────────
#  Plugins Page
# ─────────────────────────────────────────────────────────────

class PluginsPage(QWidget):
    navigate_to_plugin = Signal(str)

    def __init__(self, plugin_manager, parent: QWidget | None = None):
        super().__init__(parent)
        self._pm = plugin_manager
        self._cards: Dict[str, PluginListItem] = {}
        self.setObjectName("PluginsPage")

        self._pm.plugin_started.connect(self._on_plugin_started)
        self._pm.plugin_stopped.connect(self._on_plugin_stopped)
        self._pm.plugin_crashed.connect(self._on_plugin_crashed)
        self._pm.plugin_favorite_changed.connect(self._on_favorite_changed)
        self._pm.plugin_deleted.connect(self._on_plugin_deleted)
        self._pm.plugin_imported.connect(self._on_plugin_imported)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self._container = QWidget()
        self._container.setObjectName("PluginsContainer")
        self._root = QVBoxLayout(self._container)
        self._root.setContentsMargins(20, 16, 20, 20)
        self._root.setSpacing(8)

        # ── Search / filter bar ────────────────────────────────
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        self._search = QLineEdit()
        self._search.setObjectName("PluginSearchBox")
        self._search.setPlaceholderText("Search plugins...")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(28)
        self._search.textChanged.connect(self._apply_filter)
        filter_bar.addWidget(self._search, 1)

        self._category_filter = QComboBox()
        self._category_filter.setObjectName("PluginCategoryFilter")
        self._category_filter.setFixedHeight(28)
        self._category_filter.setMinimumWidth(120)
        self._category_filter.addItem("All")
        self._category_filter.currentTextChanged.connect(self._apply_filter)
        filter_bar.addWidget(self._category_filter)

        self._root.addLayout(filter_bar)

        # ── Toolbar: batch actions (left) | management (right) ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._select_all_btn = _toolbar_btn("check", "Select All", "Select all plugins")
        self._select_all_btn.clicked.connect(self._on_select_all)
        toolbar.addWidget(self._select_all_btn)

        self._start_sel_btn = _toolbar_btn("play", "Start", "Start selected plugins")
        self._start_sel_btn.setEnabled(False)
        self._start_sel_btn.clicked.connect(self._on_start_selected)
        toolbar.addWidget(self._start_sel_btn)

        self._stop_sel_btn = _toolbar_btn("stop", "Stop", "Stop selected plugins")
        self._stop_sel_btn.setEnabled(False)
        self._stop_sel_btn.clicked.connect(self._on_stop_selected)
        toolbar.addWidget(self._stop_sel_btn)

        toolbar.addStretch()

        self._import_btn = _toolbar_btn("add", "Import", "Import plugin from .zip")
        self._import_btn.clicked.connect(self._on_import_clicked)
        toolbar.addWidget(self._import_btn)

        self._new_btn = _toolbar_btn("add", "New", "Create new plugin template")
        self._new_btn.clicked.connect(self._on_new_plugin_clicked)
        toolbar.addWidget(self._new_btn)

        self._root.addLayout(toolbar)

        # ── List container ──────────────────────────────────────
        self._list_widget = QWidget()
        self._list_widget.setObjectName("PluginListContainer")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()

        self._root.addWidget(self._list_widget)
        self._root.addStretch()

        scroll.setWidget(self._container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Public API ────────────────────────────────────────────

    def update_plugin_manager(self, pm) -> None:
        self._pm = pm
        pm.plugin_started.connect(self._on_plugin_started)
        pm.plugin_stopped.connect(self._on_plugin_stopped)
        pm.plugin_crashed.connect(self._on_plugin_crashed)
        pm.plugin_favorite_changed.connect(self._on_favorite_changed)
        pm.plugin_deleted.connect(self._on_plugin_deleted)
        pm.plugin_imported.connect(self._on_plugin_imported)
        self.refresh()

    def refresh(self):
        # Remove all items
        while self._list_layout.count() > 1:  # keep the trailing stretch
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._cards.clear()

        for manifest in self._pm.manifests():
            self._add_item(manifest)
        self._update_selection_buttons()
        self._rebuild_category_filter()
        self._apply_filter()

    def refresh_icons(self) -> None:
        for card in self._cards.values():
            card.refresh_icons()

    def add_plugin_card(self, manifest):
        if manifest.id not in self._cards:
            self._add_item(manifest)
            self._rebuild_category_filter()

    # ── Internal — item lifecycle ────────────────────────────

    def _add_item(self, manifest):
        item = PluginListItem(manifest, self._pm)
        item.start_clicked.connect(self._on_start_clicked)
        item.stop_clicked.connect(self._on_stop_clicked)
        item.view_clicked.connect(self.navigate_to_plugin)
        item.favorite_toggled.connect(self._pm.set_favorite)
        item.reload_clicked.connect(self._on_reload_clicked)
        item.export_clicked.connect(self._on_export_clicked)
        item.delete_clicked.connect(self._on_delete_clicked)
        item.info_clicked.connect(self._on_info_clicked)
        item.selection_changed.connect(self._on_card_selection_changed)
        item.set_active(self._pm.is_active(manifest.id))
        # Insert before trailing stretch
        self._list_layout.insertWidget(self._list_layout.count() - 1, item)
        self._cards[manifest.id] = item

    def _rebuild_category_filter(self):
        """Update the category filter dropdown from current plugins."""
        current = self._category_filter.currentText()
        categories = sorted({item.category for item in self._cards.values()})
        self._category_filter.blockSignals(True)
        self._category_filter.clear()
        self._category_filter.addItem("All")
        for cat in categories:
            self._category_filter.addItem(cat)
        # Restore selection
        idx = self._category_filter.findText(current)
        if idx >= 0:
            self._category_filter.setCurrentIndex(idx)
        self._category_filter.blockSignals(False)

    def _apply_filter(self, _=None):
        """Show/hide items based on search text and category."""
        search = self._search.text().strip()
        category = self._category_filter.currentText()
        for item in self._cards.values():
            item.setVisible(item.matches_filter(search, category))

    # ── Internal — selection & bulk actions ──────────────────

    def _selected_ids(self) -> list[str]:
        return [pid for pid, card in self._cards.items() if card.is_selected]

    def _all_selected(self) -> bool:
        visible = [c for c in self._cards.values() if c.isVisible()]
        return bool(visible) and all(c.is_selected for c in visible)

    def _update_selection_buttons(self):
        has_sel = any(c.is_selected for c in self._cards.values())
        self._start_sel_btn.setEnabled(has_sel)
        self._stop_sel_btn.setEnabled(has_sel)
        if self._all_selected():
            self._select_all_btn.setText("Deselect All")
            self._select_all_btn.setToolTip("Deselect all plugins")
        else:
            self._select_all_btn.setText("Select All")
            self._select_all_btn.setToolTip("Select all plugins")

    def _on_card_selection_changed(self, _pid: str, _checked: bool):
        self._update_selection_buttons()

    def _on_select_all(self):
        target = not self._all_selected()
        for card in self._cards.values():
            if card.isVisible():
                card.set_selected(target)

    def _on_start_selected(self):
        for pid in self._selected_ids():
            if not self._pm.is_active(pid):
                if not self._pm.is_loaded(pid):
                    self._pm.load(pid)
                self._pm.start(pid)

    def _on_stop_selected(self):
        for pid in self._selected_ids():
            if self._pm.is_active(pid):
                self._pm.stop(pid)

    # ── Internal — plugin actions ─────────────────────────────

    def _on_start_clicked(self, pid: str):
        if not self._pm.is_loaded(pid):
            self._pm.load(pid)
        self._pm.start(pid)

    def _on_stop_clicked(self, pid: str):
        self._pm.stop(pid)

    def _on_reload_clicked(self, pid: str):
        self._pm.reload_plugin(pid)

    def _on_export_clicked(self, pid: str):
        d = QFileDialog.getExistingDirectory(self, "Select Export Folder", str(Path.home()))
        if not d:
            return
        ok, result = self._pm.export_plugin(pid, Path(d))
        if ok:
            QMessageBox.information(self, "Export Successful", f"Plugin exported to:\n{result}")
        else:
            QMessageBox.warning(self, "Export Failed", result)

    def _on_delete_clicked(self, pid: str):
        reply = QMessageBox.question(
            self, "Delete Plugin",
            f"Permanently delete plugin '{pid}' and all its files?\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            ok, err = self._pm.delete_plugin(pid)
            if not ok:
                QMessageBox.warning(self, "Delete Failed", err)

    def _on_info_clicked(self, pid: str):
        record = self._pm._records.get(pid)
        if record is None:
            return
        dlg = _InfoDialog(record.manifest, self._pm.get_state(pid), self)
        dlg.exec()

    def _on_import_clicked(self):
        z, _ = QFileDialog.getOpenFileName(self, "Import Plugin", str(Path.home()), "Plugin Archives (*.zip)")
        if not z:
            return
        ok, result = self._pm.import_plugin(Path(z))
        if ok:
            QMessageBox.information(self, "Import Successful",
                f"Plugin '{result}' imported successfully.\nLoad and start it from the Plugin Manager.")
        else:
            QMessageBox.warning(self, "Import Failed", result)

    def _on_new_plugin_clicked(self):
        dlg = _NewPluginDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        pid, name, author, desc = dlg.values()
        target = self._pm._plugins_dir / pid
        if target.exists():
            QMessageBox.warning(self, "Already Exists", f"A plugin named '{pid}' already exists.")
            return
        from nova.core.plugin_spec import create_plugin_template
        try:
            created = create_plugin_template(pid, name, author, desc, self._pm._plugins_dir)
            self._pm.plugin_imported.emit(pid)
            QMessageBox.information(self, "Plugin Created",
                f"Plugin template created at:\n{created}\n\nEdit plugin_main.py to implement your logic.")
        except Exception as exc:
            QMessageBox.warning(self, "Creation Failed", str(exc))

    # ── Internal — signal handlers ────────────────────────────

    def _on_plugin_started(self, pid: str):
        if pid in self._cards: self._cards[pid].set_active(True)

    def _on_plugin_stopped(self, pid: str):
        if pid in self._cards: self._cards[pid].set_active(False)

    def _on_plugin_crashed(self, pid: str, _msg: str):
        if pid in self._cards: self._cards[pid].set_crashed()

    def _on_favorite_changed(self, pid: str, is_fav: bool):
        if pid in self._cards: self._cards[pid].set_favorite(is_fav)

    def _on_plugin_deleted(self, _pid: str):
        self.refresh()

    def _on_plugin_imported(self, pid: str):
        if self._pm.load(pid):
            self.refresh()
