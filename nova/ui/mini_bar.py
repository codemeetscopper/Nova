"""
Minimal Mode Bar
================
A slim floating toolbar that replaces the main window in minimal mode.
Shows the Nova logo and running plugin icons as clickable buttons.
Clicking a plugin opens/raises its detached window.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget,
)

from nova.core.icons import IconManager
from nova.core.style import StyleManager

_log = logging.getLogger(__name__)

_BAR_H = 40
_ICON_BTN = 32
_ICO = 18


class MiniBar(QWidget):
    """Slim floating bar — the minimal-mode UI."""

    restore_requested = Signal()
    plugin_clicked = Signal(str)  # page_id

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Nova")
        self.setObjectName("MiniBar")
        self.setFixedHeight(_BAR_H)
        self.setMinimumWidth(120)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        # Window icon
        accent = StyleManager.get_colour("accent")
        icon_px = IconManager.get_pixmap("logo", accent, 25)
        if icon_px:
            self.setWindowIcon(QIcon(icon_px))

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 0, 8, 0)
        self._layout.setSpacing(4)

        # Logo button — click to restore
        self._logo_btn = QPushButton()
        self._logo_btn.setObjectName("MiniBarLogo")
        self._logo_btn.setFixedSize(_ICON_BTN, _ICON_BTN)
        self._logo_btn.setCursor(Qt.PointingHandCursor)
        self._logo_btn.setToolTip("Restore Nova")
        self._logo_btn.clicked.connect(self.restore_requested)
        self._refresh_logo()
        self._layout.addWidget(self._logo_btn)

        # Separator
        sep = QLabel()
        sep.setFixedSize(1, 24)
        sep.setObjectName("MiniBarSep")
        self._layout.addWidget(sep)

        # Stretch at the end
        self._layout.addStretch()

        # Track plugin buttons: page_id -> QPushButton
        self._plugin_btns: dict[str, QPushButton] = {}

    # ── Public API ────────────────────────────────────────────

    def set_plugin(self, page_id: str, title: str, icon_str: str,
                   active: bool):
        """Add or update a plugin button on the bar."""
        if page_id in self._plugin_btns:
            btn = self._plugin_btns[page_id]
            self._style_plugin_btn(btn, icon_str, title, active)
            return

        btn = QPushButton()
        btn.setObjectName("MiniBarPlugin")
        btn.setFixedSize(_ICON_BTN, _ICON_BTN)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(title)
        btn.clicked.connect(lambda _=False, pid=page_id: self.plugin_clicked.emit(pid))
        self._style_plugin_btn(btn, icon_str, title, active)

        # Insert before the stretch
        idx = self._layout.count() - 1  # before stretch
        self._layout.insertWidget(idx, btn)
        self._plugin_btns[page_id] = btn
        self._resize_to_content()

    def remove_plugin(self, page_id: str):
        btn = self._plugin_btns.pop(page_id, None)
        if btn:
            self._layout.removeWidget(btn)
            btn.deleteLater()
            self._resize_to_content()

    def update_plugin_status(self, page_id: str, active: bool):
        btn = self._plugin_btns.get(page_id)
        if btn:
            opacity = "1.0" if active else "0.4"
            btn.setStyleSheet(
                f"opacity: {opacity}; border: none; background: transparent;"
            )
            btn.setEnabled(True)

    def refresh_theme(self):
        self._refresh_logo()

    # ── Internal ──────────────────────────────────────────────

    def _refresh_logo(self):
        accent = StyleManager.get_colour("accent")
        px = IconManager.get_pixmap("logo", accent, _ICO)
        if px and not px.isNull():
            self._logo_btn.setIcon(QIcon(px))
            self._logo_btn.setIconSize(QSize(_ICO, _ICO))
            self._logo_btn.setText("")

    def _style_plugin_btn(self, btn: QPushButton, icon_str: str,
                          title: str, active: bool):
        btn.setToolTip(f"{title} — {'Online' if active else 'Offline'}")
        color = StyleManager.get_colour("accent") if active else StyleManager.get_colour("fg2")
        px = None
        if icon_str.strip().startswith("<"):
            px = IconManager.render_svg_string(icon_str, color, _ICO)
        else:
            px = IconManager.get_pixmap(icon_str or "extension", color, _ICO)
        if px and not px.isNull():
            btn.setIcon(QIcon(px))
            btn.setIconSize(QSize(_ICO, _ICO))
            btn.setText("")
        else:
            btn.setText(title[:2])

    def _resize_to_content(self):
        # logo + sep + plugins + margins
        n = len(self._plugin_btns)
        w = 8 + _ICON_BTN + 1 + 4 + n * (_ICON_BTN + 4) + 8
        self.setMinimumWidth(max(120, w))
        self.resize(max(120, w), _BAR_H)
