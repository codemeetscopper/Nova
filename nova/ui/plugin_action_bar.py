from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QPushButton, QWidget,
)

_log = logging.getLogger(__name__)

_BTN_SIZE = 30
_ICON_SIZE = 16


def _fg1() -> str:
    try:
        from nova.core.style import StyleManager
        return StyleManager.get_colour("fg1")
    except Exception:
        return "#888888"


def _accent() -> str:
    try:
        from nova.core.style import StyleManager
        return StyleManager.get_colour("accent")
    except Exception:
        return "#0088CC"


def _set_btn_icon(btn: QPushButton, icon_name: str, color: str,
                  size: int = _ICON_SIZE) -> None:
    try:
        from nova.core.icons import IconManager
        px = IconManager.get_pixmap(icon_name, color, size)
        if px and not px.isNull():
            btn.setIcon(px)
            btn.setIconSize(QSize(size, size))
            btn.setText("")
            return
    except Exception:
        pass


def _make_btn(icon_name: str, color: str, tooltip: str,
              object_name: str) -> QPushButton:
    btn = QPushButton()
    btn.setFixedSize(_BTN_SIZE, _BTN_SIZE)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setToolTip(tooltip)
    btn.setObjectName(object_name)
    _set_btn_icon(btn, icon_name, color)
    return btn


class PluginActionBar(QWidget):
    """
    Row of icon buttons for plugin actions: start, stop, reload, favorite, info.
    Emits signals without plugin_id — the owner maps them to the current plugin.
    """

    start_clicked = Signal()
    stop_clicked = Signal()
    reload_clicked = Signal()
    favorite_toggled = Signal(bool)   # new desired state
    info_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PluginActionBar")
        self._is_favorite = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        fg1 = _fg1()

        self._start_btn = _make_btn("play", "#22C55E", "Start plugin",
                                    "ActionBarStart")
        self._start_btn.clicked.connect(self.start_clicked)
        layout.addWidget(self._start_btn)

        self._stop_btn = _make_btn("stop", "#EF4444", "Stop plugin",
                                   "ActionBarStop")
        self._stop_btn.clicked.connect(self.stop_clicked)
        self._stop_btn.setEnabled(False)
        layout.addWidget(self._stop_btn)

        self._reload_btn = _make_btn("refresh", fg1, "Reload plugin",
                                     "ActionBarIcon")
        self._reload_btn.clicked.connect(self.reload_clicked)
        layout.addWidget(self._reload_btn)

        self._fav_btn = _make_btn("favorite_border", fg1, "Pin to sidebar",
                                  "ActionBarFav")
        self._fav_btn.clicked.connect(self._on_fav_clicked)
        layout.addWidget(self._fav_btn)

        self._info_btn = _make_btn("info", fg1, "Plugin info",
                                   "ActionBarIcon")
        self._info_btn.clicked.connect(self.info_clicked)
        layout.addWidget(self._info_btn)

        # For theme refresh
        self._icon_btns: List[Tuple[QPushButton, str, str]] = [
            (self._reload_btn, "refresh", "fg1"),
            (self._info_btn, "info", "fg1"),
        ]

    # ── Public API ────────────────────────────────────────────

    def set_active(self, active: bool):
        self._start_btn.setEnabled(not active)
        self._stop_btn.setEnabled(active)

    def set_favorite(self, is_favorite: bool):
        self._is_favorite = is_favorite
        self._update_fav_icon()

    def refresh_icons(self):
        fg1 = _fg1()
        for btn, icon, _color_key in self._icon_btns:
            _set_btn_icon(btn, icon, fg1)
        _set_btn_icon(self._start_btn, "play", "#22C55E")
        _set_btn_icon(self._stop_btn, "stop", "#EF4444")
        self._update_fav_icon()

    # ── Internal ──────────────────────────────────────────────

    def _on_fav_clicked(self):
        self.favorite_toggled.emit(not self._is_favorite)

    def _update_fav_icon(self):
        if self._is_favorite:
            icon = "favorite"
            color = _accent()
            tip = "Remove from sidebar"
        else:
            icon = "favorite_border"
            color = _fg1()
            tip = "Pin to sidebar"
        _set_btn_icon(self._fav_btn, icon, color)
        self._fav_btn.setToolTip(tip)
