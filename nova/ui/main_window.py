from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QPushButton, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

from nova.core.icons import IconManager
from nova.core.style import StyleManager
from nova.ui.detached_window import DetachedPluginWindow
from nova.ui.sidebar import Sidebar

_log = logging.getLogger(__name__)

_COLOR_RUNNING = "#22C55E"
_COLOR_OFFLINE = "#888888"


class PageHeader(QWidget):
    undock_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PageHeader")
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(8)

        self._title = QLabel()
        self._title.setObjectName("PageHeaderTitle")
        self._title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        layout.addWidget(self._title)

        layout.addStretch()

        self._status_dot = QLabel()
        self._status_dot.setFixedSize(8, 8)
        self._status_dot.setObjectName("HeaderStatusDot")
        self._status_dot.hide()
        layout.addWidget(self._status_dot, 0, Qt.AlignVCenter)

        self._status_label = QLabel()
        self._status_label.setObjectName("HeaderStatusLabel")
        self._status_label.hide()
        layout.addWidget(self._status_label, 0, Qt.AlignVCenter)

        # Undock button — only visible for plugin pages
        self._undock_btn = QPushButton()
        self._undock_btn.setObjectName("UndockButton")
        self._undock_btn.setFixedSize(28, 28)
        self._undock_btn.setCursor(Qt.PointingHandCursor)
        self._undock_btn.setToolTip("Undock to separate window")
        self._undock_btn.hide()
        self._undock_btn.clicked.connect(self.undock_clicked)
        self._refresh_undock_icon()
        layout.addWidget(self._undock_btn, 0, Qt.AlignVCenter)

    def set_title(self, title: str):
        self._title.setText(title)

    def set_status(self, text: str | None, color: str | None = None):
        if text is None:
            self._status_dot.hide()
            self._status_label.hide()
            return
        self._status_dot.setStyleSheet(
            f"background-color: {color or '#888'}; border-radius: 4px; border: none;"
        )
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color: {color or '#888'}; font-size: 11px; font-weight: 500; background: transparent;"
        )
        self._status_dot.show()
        self._status_label.show()

    def set_undock_visible(self, visible: bool):
        self._undock_btn.setVisible(visible)

    def refresh_undock_icon(self):
        self._refresh_undock_icon()

    def _refresh_undock_icon(self):
        fg1 = StyleManager.get_colour("fg1")
        px = IconManager.get_pixmap("open_in_new", fg1, 16)
        if px and not px.isNull():
            self._undock_btn.setIcon(px)
            self._undock_btn.setIconSize(QSize(16, 16))
            self._undock_btn.setText("")
        else:
            self._undock_btn.setText("⇱")


class MainWindow(QMainWindow):
    """
    Nova main window.
    Layout:  Sidebar | (PageHeader / QStackedWidget)
    """

    plugin_undocked = Signal(str)  # page_id
    plugin_docked = Signal(str)    # page_id

    def __init__(self, ctx, plugin_manager, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx = ctx
        self._pm = plugin_manager
        self._pages: Dict[str, Tuple[str, QWidget]] = {}
        self._current: Optional[str] = None
        self._detached: Dict[str, DetachedPluginWindow] = {}
        self._plugin_icons: Dict[str, str] = {}

        self.setWindowTitle("Nova")
        self.setWindowIcon(IconManager.get_pixmap('logo', StyleManager.get_colour("accent"), 25))
        self.setObjectName("NovaMainWindow")

        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)

        h_layout = QHBoxLayout(central)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.item_clicked.connect(self._on_sidebar_click)
        h_layout.addWidget(self._sidebar)

        content = QWidget()
        content.setObjectName("ContentArea")
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        v_layout = QVBoxLayout(content)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(0)

        self._header = PageHeader()
        self._header.undock_clicked.connect(self._on_undock_current)
        self._stack = QStackedWidget()
        self._stack.setObjectName("PageStack")

        v_layout.addWidget(self._header)
        v_layout.addWidget(self._stack, 1)
        h_layout.addWidget(content, 1)

    # ── Page management ───────────────────────────────────────

    def add_page(self, page_id: str, title: str, icon: str, widget: QWidget):
        if page_id in self._pages:
            return
        self._pages[page_id] = (title, widget)
        self._stack.addWidget(widget)
        self._sidebar.add_item(page_id, title, icon)

    def add_plugin_page(self, page_id: str, title: str, icon: str,
                        widget: QWidget, in_sidebar: bool = True):
        if page_id in self._pages:
            return
        self._pages[page_id] = (title, widget)
        self._plugin_icons[page_id] = icon
        self._stack.addWidget(widget)
        if in_sidebar:
            self._sidebar.add_plugin_item(page_id, title, icon)

    def remove_plugin_page(self, page_id: str):
        # If the plugin is detached, close the detached window first
        if page_id in self._detached:
            dw = self._detached.pop(page_id)
            dw.take_widget()
            dw.close()
            dw.deleteLater()

        entry = self._pages.pop(page_id, None)
        self._plugin_icons.pop(page_id, None)
        if entry is None:
            return
        _title, widget = entry
        if self._current == page_id:
            self.navigate("home")
        self._stack.removeWidget(widget)
        widget.deleteLater()
        self._sidebar.remove_item(page_id)

    def show_plugin_in_sidebar(self, page_id: str, title: str, icon: str):
        if page_id in self._pages or page_id in self._detached:
            self._sidebar.add_plugin_item(page_id, title, icon)

    def hide_plugin_from_sidebar(self, page_id: str):
        self._sidebar.remove_item(page_id)

    def add_separator(self):
        self._sidebar.add_separator()

    # ── Navigation ────────────────────────────────────────────

    def navigate(self, page_id: str):
        # If the plugin is detached, raise its window instead
        if page_id in self._detached:
            dw = self._detached[page_id]
            dw.showNormal()
            dw.activateWindow()
            dw.raise_()
            return

        entry = self._pages.get(page_id)
        if entry is None:
            return
        title, widget = entry
        self._stack.setCurrentWidget(widget)
        self._header.set_title(title)
        self._sidebar.set_active(page_id)
        self._current = page_id

        # Show status + undock button for plugin pages
        if page_id.startswith("plugin_") and self._pm:
            pid = page_id[len("plugin_"):]
            if self._pm.is_active(pid):
                self._header.set_status("Online", _COLOR_RUNNING)
            else:
                self._header.set_status("Offline", _COLOR_OFFLINE)
            self._header.set_undock_visible(True)
        else:
            self._header.set_status(None)
            self._header.set_undock_visible(False)

    def update_plugin_status(self, plugin_id: str, active: bool):
        page_id = f"plugin_{plugin_id}"

        # Update detached window status if applicable
        if page_id in self._detached:
            self._detached[page_id].set_plugin_status(active)

        # Update header if currently viewing this plugin
        if self._current == page_id:
            if active:
                self._header.set_status("Online", _COLOR_RUNNING)
            else:
                self._header.set_status("Offline", _COLOR_OFFLINE)

    # ── Undock / Dock ─────────────────────────────────────────

    def undock_plugin(self, page_id: str):
        if page_id in self._detached:
            return
        entry = self._pages.get(page_id)
        if entry is None:
            return

        title, widget = entry
        icon_str = self._plugin_icons.get(page_id, "extension")

        # Remove widget from stack (don't delete it)
        self._stack.removeWidget(widget)
        del self._pages[page_id]

        # Create detached window
        dw = DetachedPluginWindow(page_id, title, icon_str, widget, None)
        dw.dock_requested.connect(self.dock_plugin)

        # Set initial status
        pid = page_id[len("plugin_"):]
        if self._pm and self._pm.is_active(pid):
            dw.set_plugin_status(True)

        self._detached[page_id] = dw

        # Position near main window, clamped to screen
        geo = self.geometry()
        target_x = geo.x() + geo.width() + 10
        target_y = geo.y()
        screen = QGuiApplication.screenAt(geo.center())
        if screen is not None:
            avail = screen.availableGeometry()
            if target_x + dw.width() > avail.right():
                target_x = max(avail.x(), geo.x() - dw.width() - 10)
            target_y = max(avail.y(), min(target_y, avail.bottom() - dw.height()))
        dw.move(target_x, target_y)
        dw.show()

        # Navigate away from the undocked page
        if self._current == page_id:
            self.navigate("home")

        # Update sidebar to show detached indicator
        self._sidebar.set_detached(page_id, True)

        self.plugin_undocked.emit(page_id)
        _log.debug("Undocked plugin: %s", page_id)

    def dock_plugin(self, page_id: str):
        dw = self._detached.pop(page_id, None)
        if dw is None:
            return

        # Take the widget back
        widget = dw.take_widget()
        title = dw.windowTitle().replace(" — Nova", "")

        # Re-add to pages and stack
        self._pages[page_id] = (title, widget)
        self._stack.addWidget(widget)

        # Close the detached window
        dw.close()
        dw.deleteLater()

        # Update sidebar
        self._sidebar.set_detached(page_id, False)

        # Navigate to the docked plugin
        self.navigate(page_id)

        self.plugin_docked.emit(page_id)
        _log.debug("Docked plugin: %s", page_id)

    def dock_all(self):
        for page_id in list(self._detached.keys()):
            self.dock_plugin(page_id)

    def close_all_detached(self):
        for page_id, dw in list(self._detached.items()):
            dw.take_widget()
            dw.close()
            dw.deleteLater()
        self._detached.clear()

    def refresh_detached_themes(self):
        for dw in self._detached.values():
            dw.refresh_theme()

    def is_detached(self, page_id: str) -> bool:
        return page_id in self._detached

    # ── Internal ──────────────────────────────────────────────

    def _on_sidebar_click(self, page_id: str):
        self.navigate(page_id)

    def _on_undock_current(self):
        if self._current and self._current.startswith("plugin_"):
            self.undock_plugin(self._current)

    def closeEvent(self, event):
        # Dock all detached windows back before closing
        self.dock_all()
        super().closeEvent(event)
