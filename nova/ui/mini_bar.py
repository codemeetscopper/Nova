"""
Minimal Mode Bar
================
A slim floating toolbar that replaces the main window in minimal mode.
Shows the Nova logo, start/stop all buttons, and favorited plugin icons.
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

_BAR_H = 44
_ICON_BTN = 36
_ICO = 20
_CTRL_BTN = 28
_CTRL_ICO = 14


class MiniBar(QWidget):
    """Slim floating bar — the minimal-mode UI."""

    restore_requested = Signal()
    plugin_clicked = Signal(str)  # page_id
    start_all_clicked = Signal()
    stop_all_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Nova")
        self.setObjectName("MiniBar")
        self.setFixedHeight(_BAR_H)
        self.setMinimumWidth(180)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        # Window icon
        accent = StyleManager.get_colour("accent")
        icon_px = IconManager.get_pixmap("logo", accent, 25)
        if icon_px:
            self.setWindowIcon(QIcon(icon_px))

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(10, 0, 10, 0)
        self._layout.setSpacing(6)

        # Logo button — click to restore
        self._logo_btn = QPushButton()
        self._logo_btn.setObjectName("MiniBarLogo")
        self._logo_btn.setFixedSize(_ICON_BTN, _ICON_BTN)
        self._logo_btn.setCursor(Qt.PointingHandCursor)
        self._logo_btn.setToolTip("Restore Nova")
        self._logo_btn.clicked.connect(self.restore_requested)
        self._refresh_logo()
        self._layout.addWidget(self._logo_btn)

        # Separator 1
        sep1 = QLabel()
        sep1.setFixedSize(1, 28)
        sep1.setObjectName("MiniBarSep")
        self._layout.addWidget(sep1)

        # Start All button
        self._start_all_btn = QPushButton()
        self._start_all_btn.setObjectName("MiniBarCtrl")
        self._start_all_btn.setFixedSize(_CTRL_BTN, _CTRL_BTN)
        self._start_all_btn.setCursor(Qt.PointingHandCursor)
        self._start_all_btn.setToolTip("Start all plugins")
        self._start_all_btn.clicked.connect(self.start_all_clicked)
        self._layout.addWidget(self._start_all_btn)

        # Stop All button
        self._stop_all_btn = QPushButton()
        self._stop_all_btn.setObjectName("MiniBarCtrl")
        self._stop_all_btn.setFixedSize(_CTRL_BTN, _CTRL_BTN)
        self._stop_all_btn.setCursor(Qt.PointingHandCursor)
        self._stop_all_btn.setToolTip("Stop all plugins")
        self._stop_all_btn.clicked.connect(self.stop_all_clicked)
        self._layout.addWidget(self._stop_all_btn)

        self._refresh_ctrl_icons()

        # Separator 2
        sep2 = QLabel()
        sep2.setFixedSize(1, 28)
        sep2.setObjectName("MiniBarSep")
        self._layout.addWidget(sep2)

        # Stretch at the end
        self._layout.addStretch()

        # Track plugin buttons: page_id -> QPushButton
        self._plugin_btns: dict[str, QPushButton] = {}

    # ── Public API ────────────────────────────────────────────

    def set_plugin(self, page_id: str, title: str, icon_str: str,
                   active: bool, has_window: bool = False):
        """Add or update a plugin button on the bar."""
        if page_id in self._plugin_btns:
            btn = self._plugin_btns[page_id]
            self._style_plugin_btn(btn, icon_str, title, active, has_window)
            return

        btn = QPushButton()
        btn.setObjectName("MiniBarPlugin")
        btn.setFixedSize(_ICON_BTN, _ICON_BTN)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(title)
        btn.clicked.connect(lambda _=False, pid=page_id: self.plugin_clicked.emit(pid))
        self._style_plugin_btn(btn, icon_str, title, active, has_window)

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

    def refresh_theme(self):
        self._refresh_logo()
        self._refresh_ctrl_icons()

    # ── Internal ──────────────────────────────────────────────

    def _refresh_logo(self):
        accent = StyleManager.get_colour("accent")
        px = IconManager.get_pixmap("logo", accent, _ICO)
        if px and not px.isNull():
            self._logo_btn.setIcon(QIcon(px))
            self._logo_btn.setIconSize(QSize(_ICO, _ICO))
            self._logo_btn.setText("")

    def _refresh_ctrl_icons(self):
        fg1 = StyleManager.get_colour("fg1")
        for btn, name in ((self._start_all_btn, "play"), (self._stop_all_btn, "stop")):
            px = IconManager.get_pixmap(name, fg1, _CTRL_ICO)
            if px and not px.isNull():
                btn.setIcon(QIcon(px))
                btn.setIconSize(QSize(_CTRL_ICO, _CTRL_ICO))
                btn.setText("")
            else:
                btn.setText("▶" if name == "play" else "■")

    def _style_plugin_btn(self, btn: QPushButton, icon_str: str,
                          title: str, active: bool, has_window: bool):
        btn.setToolTip(f"{title} — {'Online' if active else 'Offline'}")
        # Colored icon if the plugin window is open, dimmed otherwise
        if has_window:
            color = StyleManager.get_colour("accent")
        elif active:
            color = StyleManager.get_colour("fg1")
        else:
            color = StyleManager.get_colour("fg2")
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
        # logo + sep + start + stop + sep + plugins + margins
        n = len(self._plugin_btns)
        w = (10 + _ICON_BTN + 6 + 1 + 6
             + _CTRL_BTN + 6 + _CTRL_BTN + 6 + 1 + 6
             + n * (_ICON_BTN + 6) + 10)
        self.setMinimumWidth(max(180, w))
        self.resize(max(180, w), _BAR_H)
