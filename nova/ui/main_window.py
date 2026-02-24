from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

from nova.core.icons import IconManager
from nova.core.style import StyleManager
from nova.ui.sidebar import Sidebar

_log = logging.getLogger(__name__)


class PageHeader(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PageHeader")
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(0)

        self._title = QLabel()
        self._title.setObjectName("PageHeaderTitle")
        self._title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        layout.addWidget(self._title)
        layout.addStretch()

    def set_title(self, title: str):
        self._title.setText(title)


class MainWindow(QMainWindow):
    """
    Nova main window.
    Layout:  Sidebar | (PageHeader / QStackedWidget)
    """

    def __init__(self, ctx, plugin_manager, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx = ctx
        self._pm = plugin_manager
        self._pages: Dict[str, Tuple[str, QWidget]] = {}
        self._current: Optional[str] = None

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
        self._sidebar.item_clicked.connect(self.navigate)
        h_layout.addWidget(self._sidebar)

        content = QWidget()
        content.setObjectName("ContentArea")
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        v_layout = QVBoxLayout(content)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(0)

        self._header = PageHeader()
        self._stack = QStackedWidget()
        self._stack.setObjectName("PageStack")

        v_layout.addWidget(self._header)
        v_layout.addWidget(self._stack, 1)
        h_layout.addWidget(content, 1)



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
        self._stack.addWidget(widget)
        if in_sidebar:
            self._sidebar.add_plugin_item(page_id, title, icon)

    def remove_plugin_page(self, page_id: str):
        entry = self._pages.pop(page_id, None)
        if entry is None:
            return
        _title, widget = entry
        if self._current == page_id:
            self.navigate("home")
        self._stack.removeWidget(widget)
        widget.deleteLater()
        self._sidebar.remove_item(page_id)

    def show_plugin_in_sidebar(self, page_id: str, title: str, icon: str):
        if page_id in self._pages:
            self._sidebar.add_plugin_item(page_id, title, icon)

    def hide_plugin_from_sidebar(self, page_id: str):
        self._sidebar.remove_item(page_id)

    def add_separator(self):
        self._sidebar.add_separator()

    def navigate(self, page_id: str):
        entry = self._pages.get(page_id)
        if entry is None:
            return
        title, widget = entry
        self._stack.setCurrentWidget(widget)
        self._header.set_title(title)
        self._sidebar.set_active(page_id)
        self._current = page_id
