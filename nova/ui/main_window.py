from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QMenu, QPushButton,
    QSizePolicy, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from nova.core.icons import IconManager
from nova.core.style import StyleManager
from nova.ui.detached_window import DetachedPluginWindow
from nova.ui.mini_bar import MiniBar
from nova.ui.plugin_action_bar import PluginActionBar
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
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        title_area = QVBoxLayout()
        title_area.setContentsMargins(0, 4, 0, 4)
        title_area.setSpacing(1)

        self._title = QLabel()
        self._title.setObjectName("PageHeaderTitle")
        self._title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        title_area.addWidget(self._title)

        self._subtitle = QLabel()
        self._subtitle.setObjectName("PageHeaderSubtitle")
        self._subtitle.setStyleSheet("color: #888; font-size: 10px;")
        self._subtitle.hide()
        title_area.addWidget(self._subtitle)

        layout.addLayout(title_area)
        layout.addStretch()

        # Status dot + label
        self._status_dot = QLabel()
        self._status_dot.setFixedSize(8, 8)
        self._status_dot.setObjectName("HeaderStatusDot")
        self._status_dot.hide()
        layout.addWidget(self._status_dot, 0, Qt.AlignVCenter)

        self._status_label = QLabel()
        self._status_label.setObjectName("HeaderStatusLabel")
        self._status_label.hide()
        layout.addWidget(self._status_label, 0, Qt.AlignVCenter)

        # Plugin action bar — only visible for plugin pages
        self._action_bar = PluginActionBar()
        self._action_bar.hide()
        layout.addWidget(self._action_bar, 0, Qt.AlignVCenter)

        # Undock button — only visible for plugin pages
        self._undock_btn = QPushButton()
        self._undock_btn.setObjectName("UndockButton")
        self._undock_btn.setFixedSize(30, 30)
        self._undock_btn.setCursor(Qt.PointingHandCursor)
        self._undock_btn.setToolTip("Undock to separate window")
        self._undock_btn.hide()
        self._undock_btn.clicked.connect(self.undock_clicked)
        self._refresh_undock_icon()
        layout.addWidget(self._undock_btn, 0, Qt.AlignVCenter)

    @property
    def action_bar(self) -> PluginActionBar:
        return self._action_bar

    def set_title(self, title: str):
        self._title.setText(title)

    def set_subtitle(self, text: str | None):
        if text:
            self._subtitle.setText(text)
            self._subtitle.show()
        else:
            self._subtitle.setText("")
            self._subtitle.hide()

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

    def set_plugin_controls_visible(self, visible: bool):
        self._undock_btn.setVisible(visible)
        self._action_bar.setVisible(visible)

    def refresh_icons(self):
        self._refresh_undock_icon()
        self._action_bar.refresh_icons()

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
        self._plugin_descriptions: Dict[str, str] = {}
        self._minimal_mode = False
        self._force_quit = False

        self.setWindowTitle("Nova")
        self._app_icon = IconManager.get_app_icon(
            primary=StyleManager.get_colour("accent"),
        )
        self.setWindowIcon(self._app_icon)
        self.setObjectName("NovaMainWindow")

        # ── System tray ──────────────────────────────────────
        self._tray = QSystemTrayIcon(self._app_icon, self)
        self._tray.setToolTip("Nova")
        self._tray.activated.connect(self._on_tray_activated)

        tray_menu = QMenu()
        act_show = QAction("Show Nova", self)
        act_show.triggered.connect(self._restore_from_tray)
        tray_menu.addAction(act_show)

        act_mini = QAction("Minimal Mode", self)
        act_mini.triggered.connect(self.enter_minimal_mode)
        tray_menu.addAction(act_mini)

        tray_menu.addSeparator()

        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(self._quit_app)
        tray_menu.addAction(act_quit)

        self._tray.setContextMenu(tray_menu)
        self._tray.show()

        # ── Mini bar ─────────────────────────────────────────
        self._mini_bar = MiniBar()
        self._mini_bar.restore_requested.connect(self.exit_minimal_mode)
        self._mini_bar.plugin_clicked.connect(self._on_mini_bar_plugin_click)
        self._mini_bar.hide()

        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)

        h_layout = QHBoxLayout(central)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.item_clicked.connect(self._on_sidebar_click)
        self._sidebar.minimal_mode_clicked.connect(self.enter_minimal_mode)
        h_layout.addWidget(self._sidebar)

        content = QWidget()
        content.setObjectName("ContentArea")
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        v_layout = QVBoxLayout(content)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(0)

        self._header = PageHeader()
        self._header.undock_clicked.connect(self._on_undock_current)

        # Connect header action bar signals
        ab = self._header.action_bar
        ab.start_clicked.connect(self._on_action_start)
        ab.stop_clicked.connect(self._on_action_stop)
        ab.reload_clicked.connect(self._on_action_reload)
        ab.favorite_toggled.connect(self._on_action_favorite)
        ab.info_clicked.connect(self._on_action_info)

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
                        widget: QWidget, in_sidebar: bool = True,
                        description: str = ""):
        if page_id in self._pages:
            return
        self._pages[page_id] = (title, widget)
        self._plugin_icons[page_id] = icon
        if description:
            self._plugin_descriptions[page_id] = description
        # Disable widget until plugin is started (online)
        pid = page_id[len("plugin_"):] if page_id.startswith("plugin_") else ""
        active = self._pm.is_active(pid) if self._pm and pid else False
        widget.setEnabled(active)
        self._stack.addWidget(widget)
        if in_sidebar:
            self._sidebar.add_plugin_item(page_id, title, icon)

    def remove_plugin_page(self, page_id: str):
        if page_id in self._detached:
            dw = self._detached.pop(page_id)
            dw.take_widget()
            dw.close()
            dw.deleteLater()

        entry = self._pages.pop(page_id, None)
        self._plugin_icons.pop(page_id, None)
        self._plugin_descriptions.pop(page_id, None)
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

        if page_id.startswith("plugin_") and self._pm:
            pid = page_id[len("plugin_"):]
            active = self._pm.is_active(pid)
            if active:
                self._header.set_status("Online", _COLOR_RUNNING)
            else:
                self._header.set_status("Offline", _COLOR_OFFLINE)
            self._header.set_plugin_controls_visible(True)
            self._header.action_bar.set_active(active)
            self._header.action_bar.set_favorite(self._pm.is_favorite(pid))
            self._header.set_subtitle(self._plugin_descriptions.get(page_id))
        else:
            self._header.set_status(None)
            self._header.set_plugin_controls_visible(False)
            self._header.set_subtitle(None)

    def update_plugin_status(self, plugin_id: str, active: bool):
        page_id = f"plugin_{plugin_id}"

        # Enable/disable plugin widget based on running state
        entry = self._pages.get(page_id)
        if entry:
            _, widget = entry
            widget.setEnabled(active)

        if page_id in self._detached:
            dw = self._detached[page_id]
            dw.set_plugin_status(active)

        # Update mini bar
        self.update_mini_bar_status(plugin_id, active)

        if self._current == page_id:
            if active:
                self._header.set_status("Online", _COLOR_RUNNING)
            else:
                self._header.set_status("Offline", _COLOR_OFFLINE)
            self._header.action_bar.set_active(active)

    def update_plugin_favorite(self, plugin_id: str, is_fav: bool):
        """Sync favorite icon in header and detached window action bars."""
        page_id = f"plugin_{plugin_id}"
        if self._current == page_id:
            self._header.action_bar.set_favorite(is_fav)
        if page_id in self._detached:
            self._detached[page_id].action_bar.set_favorite(is_fav)

    # ── Undock / Dock ─────────────────────────────────────────

    def undock_plugin(self, page_id: str):
        if page_id in self._detached:
            return
        entry = self._pages.get(page_id)
        if entry is None:
            return

        title, widget = entry
        icon_str = self._plugin_icons.get(page_id, "extension")

        self._stack.removeWidget(widget)
        del self._pages[page_id]

        # Use the stack widget size so the detached window matches the docked area
        content_size = self._stack.size()

        desc = self._plugin_descriptions.get(page_id, "")
        dw = DetachedPluginWindow(page_id, title, icon_str, widget, None,
                                  description=desc)
        dw.resize(content_size)
        dw.dock_requested.connect(self.dock_plugin)

        # Wire detached window action bar signals
        dab = dw.action_bar
        dab.start_clicked.connect(lambda pid=page_id: self._on_detached_action_start(pid))
        dab.stop_clicked.connect(lambda pid=page_id: self._on_detached_action_stop(pid))
        dab.reload_clicked.connect(lambda pid=page_id: self._on_detached_action_reload(pid))
        dab.favorite_toggled.connect(lambda v, pid=page_id: self._on_detached_action_favorite(pid, v))
        dab.info_clicked.connect(lambda pid=page_id: self._on_detached_action_info(pid))

        # Set initial state
        pid = page_id[len("plugin_"):]
        active = self._pm.is_active(pid) if self._pm else False
        dw.set_plugin_status(active)
        dab.set_active(active)
        dab.set_favorite(self._pm.is_favorite(pid) if self._pm else False)

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

        if self._current == page_id:
            self.navigate("home")

        self._sidebar.set_detached(page_id, True)
        self.plugin_undocked.emit(page_id)
        _log.debug("Undocked plugin: %s", page_id)

    def dock_plugin(self, page_id: str):
        dw = self._detached.pop(page_id, None)
        if dw is None:
            return

        widget = dw.take_widget()
        title = dw.windowTitle().replace(" — Nova", "")

        self._pages[page_id] = (title, widget)
        self._stack.addWidget(widget)

        dw.close()
        dw.deleteLater()

        self._sidebar.set_detached(page_id, False)
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
        self._mini_bar.refresh_theme()

    def is_detached(self, page_id: str) -> bool:
        return page_id in self._detached

    # ── Internal: sidebar ─────────────────────────────────────

    def _on_sidebar_click(self, page_id: str):
        self.navigate(page_id)

    def _on_undock_current(self):
        if self._current and self._current.startswith("plugin_"):
            self.undock_plugin(self._current)

    # ── Internal: header action bar handlers ──────────────────

    def _current_pid(self) -> Optional[str]:
        if self._current and self._current.startswith("plugin_"):
            return self._current[len("plugin_"):]
        return None

    def _on_action_start(self):
        pid = self._current_pid()
        if pid and self._pm:
            if not self._pm.is_loaded(pid):
                self._pm.load(pid)
            self._pm.start(pid)

    def _on_action_stop(self):
        pid = self._current_pid()
        if pid and self._pm:
            self._pm.stop(pid)

    def _on_action_reload(self):
        pid = self._current_pid()
        if pid and self._pm:
            self._pm.reload_plugin(pid)

    def _on_action_favorite(self, new_state: bool):
        pid = self._current_pid()
        if pid and self._pm:
            self._pm.set_favorite(pid, new_state)

    def _on_action_info(self):
        pid = self._current_pid()
        if pid and self._pm:
            self._show_info_dialog(pid)

    # ── Internal: detached action bar handlers ────────────────

    def _on_detached_action_start(self, page_id: str):
        pid = page_id[len("plugin_"):]
        if self._pm:
            if not self._pm.is_loaded(pid):
                self._pm.load(pid)
            self._pm.start(pid)

    def _on_detached_action_stop(self, page_id: str):
        pid = page_id[len("plugin_"):]
        if self._pm:
            self._pm.stop(pid)

    def _on_detached_action_reload(self, page_id: str):
        pid = page_id[len("plugin_"):]
        if self._pm:
            self._pm.reload_plugin(pid)

    def _on_detached_action_favorite(self, page_id: str, new_state: bool):
        pid = page_id[len("plugin_"):]
        if self._pm:
            self._pm.set_favorite(pid, new_state)

    def _on_detached_action_info(self, page_id: str):
        pid = page_id[len("plugin_"):]
        if self._pm:
            self._show_info_dialog(pid)

    def _show_info_dialog(self, pid: str):
        from nova.pages.plugins_page import _InfoDialog
        record = self._pm._records.get(pid)
        if record is None:
            return
        dlg = _InfoDialog(record.manifest, self._pm.get_state(pid), self)
        dlg.exec()

    # ── Minimal mode ─────────────────────────────────────────

    def enter_minimal_mode(self):
        """Undock all plugins, hide main window, show mini bar."""
        if self._minimal_mode:
            return
        self._minimal_mode = True

        # Undock every loaded plugin so they become standalone windows
        for page_id in list(self._pages.keys()):
            if page_id.startswith("plugin_"):
                self.undock_plugin(page_id)

        # Populate mini bar with all known plugins
        self._sync_mini_bar()

        # Position mini bar at top-centre of primary screen
        screen = QGuiApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            x = avail.x() + (avail.width() - self._mini_bar.width()) // 2
            self._mini_bar.move(x, avail.y())

        self._mini_bar.show()
        self._mini_bar.raise_()
        self.hide()
        _log.debug("Entered minimal mode")

    def exit_minimal_mode(self):
        """Dock all plugins back, show main window, hide mini bar."""
        if not self._minimal_mode:
            self._restore_from_tray()
            return
        self._minimal_mode = False

        self._mini_bar.hide()
        self.dock_all()
        self.showNormal()
        self.activateWindow()
        self.raise_()
        _log.debug("Exited minimal mode")

    def _sync_mini_bar(self):
        """Refresh mini bar plugin list from current plugin manager state."""
        # Clear existing
        for pid in list(self._mini_bar._plugin_btns.keys()):
            self._mini_bar.remove_plugin(pid)

        if not self._pm:
            return
        for record in self._pm._records.values():
            page_id = f"plugin_{record.manifest.id}"
            icon_str = record.manifest.icon or "extension"
            active = self._pm.is_active(record.manifest.id)
            self._mini_bar.set_plugin(page_id, record.manifest.name,
                                       icon_str, active)

    def update_mini_bar_status(self, plugin_id: str, active: bool):
        """Called when plugin starts/stops to keep mini bar in sync."""
        page_id = f"plugin_{plugin_id}"
        if self._mini_bar.isVisible():
            record = self._pm._records.get(plugin_id) if self._pm else None
            icon_str = record.manifest.icon or "extension" if record else "extension"
            title = record.manifest.name if record else plugin_id
            self._mini_bar.set_plugin(page_id, title, icon_str, active)

    def _on_mini_bar_plugin_click(self, page_id: str):
        """Raise the detached window for the clicked plugin."""
        if page_id in self._detached:
            dw = self._detached[page_id]
            dw.showNormal()
            dw.activateWindow()
            dw.raise_()

    # ── System tray ──────────────────────────────────────────

    def minimize_to_tray(self):
        self.hide()
        self._tray.showMessage("Nova", "Running in background",
                               QSystemTrayIcon.Information, 2000)

    def _restore_from_tray(self):
        if self._minimal_mode:
            self.exit_minimal_mode()
        else:
            self.showNormal()
            self.activateWindow()
            self.raise_()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._restore_from_tray()

    def _quit_app(self):
        self._force_quit = True
        self._mini_bar.hide()
        self._mini_bar.close()
        self.dock_all()
        self._tray.hide()
        QApplication.quit()

    # ── Close ─────────────────────────────────────────────────

    def closeEvent(self, event):
        if self._force_quit:
            self.dock_all()
            super().closeEvent(event)
            return

        # If in minimal mode, just ignore close — user uses tray to quit
        if self._minimal_mode:
            event.ignore()
            return

        # Check user preference for minimize-to-tray
        minimize_to_tray = False
        try:
            minimize_to_tray = self._ctx.config.get_value(
                "system.minimize_to_tray", False
            )
            if isinstance(minimize_to_tray, str):
                minimize_to_tray = minimize_to_tray.lower() == "true"
        except Exception:
            pass

        if minimize_to_tray:
            event.ignore()
            self.minimize_to_tray()
        else:
            self.dock_all()
            self._tray.hide()
            super().closeEvent(event)
