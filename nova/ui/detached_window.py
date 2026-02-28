from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from nova.core.icons import IconManager
from nova.core.style import StyleManager
from nova.ui.plugin_action_bar import PluginActionBar

_log = logging.getLogger(__name__)

_COLOR_RUNNING = "#22C55E"
_COLOR_OFFLINE = "#888888"


class _DockToolbar(QWidget):
    """Slim toolbar: status | action buttons | dock-back icon."""

    dock_clicked = Signal()

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DetachedToolbar")
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        # Status dot
        self._status_dot = QLabel()
        self._status_dot.setFixedSize(8, 8)
        self._status_dot.setObjectName("DetachedStatusDot")
        self._set_status_style(_COLOR_OFFLINE)
        layout.addWidget(self._status_dot, 0, Qt.AlignVCenter)

        # Status text
        self._status_label = QLabel("Offline")
        self._status_label.setObjectName("DetachedStatusLabel")
        self._set_status_label(_COLOR_OFFLINE, "Offline")
        layout.addWidget(self._status_label, 0, Qt.AlignVCenter)

        layout.addStretch()

        # Plugin action bar
        self._action_bar = PluginActionBar()
        layout.addWidget(self._action_bar, 0, Qt.AlignVCenter)

        # Dock-back icon button
        self._dock_btn = QPushButton()
        self._dock_btn.setObjectName("DetachedDockButton")
        self._dock_btn.setFixedSize(30, 30)
        self._dock_btn.setCursor(Qt.PointingHandCursor)
        self._dock_btn.setToolTip("Dock back to main window")
        self._dock_btn.clicked.connect(self.dock_clicked)
        self._refresh_dock_icon()
        layout.addWidget(self._dock_btn, 0, Qt.AlignVCenter)

    @property
    def action_bar(self) -> PluginActionBar:
        return self._action_bar

    def set_status(self, active: bool):
        if active:
            self._set_status_style(_COLOR_RUNNING)
            self._set_status_label(_COLOR_RUNNING, "Online")
        else:
            self._set_status_style(_COLOR_OFFLINE)
            self._set_status_label(_COLOR_OFFLINE, "Offline")

    def refresh_icons(self):
        self._refresh_dock_icon()
        self._action_bar.refresh_icons()

    def _refresh_dock_icon(self):
        accent = StyleManager.get_colour("accent")
        px = IconManager.get_pixmap("dock_window", accent, 16)
        if px and not px.isNull():
            self._dock_btn.setIcon(px)
            self._dock_btn.setIconSize(QSize(16, 16))
            self._dock_btn.setText("")

    def _set_status_style(self, color: str):
        self._status_dot.setStyleSheet(
            f"background-color: {color}; border-radius: 4px; border: none;"
        )

    def _set_status_label(self, color: str, text: str):
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 500; background: transparent;"
        )


class DetachedPluginWindow(QWidget):
    """
    A standalone window that hosts an undocked plugin widget.
    Uses the native OS window frame for reliable drag/resize/minimize/maximize/close.
    Contains a toolbar with status, plugin action buttons, and dock-back icon.
    """

    dock_requested = Signal(str)   # page_id

    def __init__(self, page_id: str, title: str, icon_str: str,
                 widget: QWidget, parent: QWidget | None = None):
        super().__init__(parent, Qt.Window)
        self._page_id = page_id
        self._plugin_widget = widget
        self._is_active = False

        self.setWindowTitle(f"{title} — Nova")
        self.setObjectName("DetachedPluginWindow")
        self.setMinimumSize(420, 320)
        self.resize(640, 480)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        # Window icon
        accent = StyleManager.get_colour("accent")
        icon_px = IconManager.get_pixmap("logo", accent, 25)
        if icon_px:
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(icon_px))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Toolbar
        self._toolbar = _DockToolbar(title)
        self._toolbar.dock_clicked.connect(self._on_dock)
        root.addWidget(self._toolbar)

        # Separator
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setObjectName("DetachedHeaderSep")
        root.addWidget(sep)

        # Plugin widget — show() needed because QStackedWidget hides non-current
        root.addWidget(widget, 1)
        widget.show()

    @property
    def page_id(self) -> str:
        return self._page_id

    @property
    def plugin_widget(self) -> QWidget:
        return self._plugin_widget

    @property
    def action_bar(self) -> PluginActionBar:
        return self._toolbar.action_bar

    def set_plugin_status(self, active: bool):
        self._is_active = active
        self._toolbar.set_status(active)
        self._toolbar.action_bar.set_active(active)

    def refresh_theme(self):
        self._toolbar.refresh_icons()

    def take_widget(self) -> QWidget:
        """Remove and return the plugin widget without deleting it."""
        self.layout().removeWidget(self._plugin_widget)
        self._plugin_widget.setParent(None)
        return self._plugin_widget

    def _on_dock(self):
        self.dock_requested.emit(self._page_id)

    def closeEvent(self, event):
        self.dock_requested.emit(self._page_id)
        event.ignore()
