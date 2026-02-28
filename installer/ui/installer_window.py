"""
InstallerWindow — Main window for the installer wizard.

Layout:
  _TitleBar (custom frameless: icon + title + minimize/close, draggable)
  StepTopbar (progress stepper)
  ContentArea (PageStack)
  BottomBar (Back / Next / Install / Cancel)
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from installer.core.icons import IconManager
from installer.core.style import StyleManager
from installer.ui.step_topbar import StepTopbar

_log = logging.getLogger(__name__)


# ── Title Bar ──────────────────────────────────────────────────

class _TitleBar(QWidget):
    """Custom title bar with app icon, title, minimize and close buttons."""

    minimize_clicked = Signal()
    close_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(36)
        self._drag_pos: Optional[QPoint] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 4, 0)
        layout.setSpacing(8)

        # App icon
        self._icon = QLabel()
        self._icon.setObjectName("TitleBarIcon")
        self._icon.setFixedSize(20, 20)
        self._icon.setAlignment(Qt.AlignCenter)
        app_icon = IconManager.get_app_icon()
        px = app_icon.pixmap(QSize(20, 20))
        if px and not px.isNull():
            self._icon.setPixmap(px)
        layout.addWidget(self._icon)

        # Title
        self._title = QLabel("Nova Installer")
        self._title.setObjectName("TitleBarTitle")
        layout.addWidget(self._title)

        layout.addStretch()

        # Minimize button
        self._minimize_btn = QPushButton()
        self._minimize_btn.setObjectName("TitleBarMinimize")
        self._minimize_btn.setFixedSize(32, 28)
        self._minimize_btn.setCursor(Qt.PointingHandCursor)
        accent = StyleManager.get_colour("accent")
        px = IconManager.get_pixmap("minimize", accent, 16)
        if px and not px.isNull():
            self._minimize_btn.setIcon(QIcon(px))
            self._minimize_btn.setIconSize(QSize(16, 16))
        self._minimize_btn.clicked.connect(self.minimize_clicked)
        layout.addWidget(self._minimize_btn)

        # Close button
        self._close_btn = QPushButton()
        self._close_btn.setObjectName("TitleBarClose")
        self._close_btn.setFixedSize(32, 28)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        px = IconManager.get_pixmap("close", accent, 14)
        if px and not px.isNull():
            self._close_btn.setIcon(QIcon(px))
            self._close_btn.setIconSize(QSize(14, 14))
        self._close_btn.clicked.connect(self.close_clicked)
        layout.addWidget(self._close_btn)

    def set_title(self, text: str):
        self._title.setText(text)

    # ── Drag handling ──────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            win = self.window()
            win.move(win.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


# ── Bottom Bar ─────────────────────────────────────────────────

class BottomBar(QWidget):
    """Navigation bar at the bottom: Back | spacer | Cancel | Next/Install/Finish."""

    back_clicked = Signal()
    next_clicked = Signal()
    cancel_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("BottomBar")
        self.setFixedHeight(48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        self._back_btn = QPushButton("Back")
        self._back_btn.setObjectName("BottomBarBack")
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.clicked.connect(self.back_clicked)
        layout.addWidget(self._back_btn)

        layout.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("BottomBarCancel")
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.clicked.connect(self.cancel_clicked)
        layout.addWidget(self._cancel_btn)

        self._next_btn = QPushButton("Next")
        self._next_btn.setObjectName("BottomBarNext")
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.clicked.connect(self.next_clicked)
        layout.addWidget(self._next_btn)

    def set_back_visible(self, visible: bool):
        self._back_btn.setVisible(visible)

    def set_back_enabled(self, enabled: bool):
        self._back_btn.setEnabled(enabled)

    def set_next_text(self, text: str):
        self._next_btn.setText(text)

    def set_next_enabled(self, enabled: bool):
        self._next_btn.setEnabled(enabled)

    def set_next_visible(self, visible: bool):
        self._next_btn.setVisible(visible)

    def set_cancel_text(self, text: str):
        self._cancel_btn.setText(text)

    def set_cancel_enabled(self, enabled: bool):
        self._cancel_btn.setEnabled(enabled)

    def set_cancel_visible(self, visible: bool):
        self._cancel_btn.setVisible(visible)


# ── Installer Window ───────────────────────────────────────────

class InstallerWindow(QWidget):
    """
    Main installer window — frameless with custom title bar.

    Layout:  _TitleBar → StepTopbar → ContentStack → BottomBar
    """

    finished = Signal()
    cancelled = Signal()
    cancel_install = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowMinMaxButtonsHint
        )
        self.setWindowTitle("Installer")
        self.setObjectName("InstallerWindow")
        self.setFixedSize(640, 480)


        # Set window icon (propagates to taskbar)
        self.setWindowIcon(IconManager.get_app_icon())

        self._pages: List[Tuple[str, QWidget]] = []
        self._current_index = 0
        self._install_step = -1
        self._is_installing = False
        self._is_finished = False

        # Root layout — vertical
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        self._titlebar = _TitleBar()
        self._titlebar.minimize_clicked.connect(self.showMinimized)
        self._titlebar.close_clicked.connect(self._on_cancel)
        root.addWidget(self._titlebar)

        # Separator below title bar
        title_sep = QFrame()
        title_sep.setObjectName("TitleBarSep")
        title_sep.setFrameShape(QFrame.HLine)
        title_sep.setFixedHeight(1)
        root.addWidget(title_sep)

        # Step topbar
        self._topbar = StepTopbar()
        root.addWidget(self._topbar)

        # Separator below topbar
        sep = QFrame()
        sep.setObjectName("TopbarSep")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # Content area (page stack)
        self._stack = QStackedWidget()
        self._stack.setObjectName("InstallerStack")
        root.addWidget(self._stack, 1)

        # Bottom separator
        bottom_sep = QFrame()
        bottom_sep.setObjectName("BottomBarSep")
        bottom_sep.setFrameShape(QFrame.HLine)
        bottom_sep.setFixedHeight(1)
        root.addWidget(bottom_sep)

        # Bottom bar
        self._bottom = BottomBar()
        self._bottom.back_clicked.connect(self._on_back)
        self._bottom.next_clicked.connect(self._on_next)
        self._bottom.cancel_clicked.connect(self._on_cancel)
        root.addWidget(self._bottom)

    # ── Page management ────────────────────────────────────────

    def add_page(self, title: str, widget: QWidget):
        self._pages.append((title, widget))
        self._stack.addWidget(widget)

    def set_install_step(self, index: int):
        """Mark which step index is the 'installing' step."""
        self._install_step = index

    def finalise(self):
        """Call after all pages are added to initialise topbar steps."""
        titles = [t for t, _ in self._pages]
        self._topbar.set_steps(titles)
        self._update_nav()

    def set_app_info(self, name: str, version: str):
        self._topbar.set_app_info(name, version)
        self._titlebar.set_title(f"{name} Installer")
        self.setWindowTitle(f"{name} — Setup")

    # ── Navigation ─────────────────────────────────────────────

    def navigate(self, index: int):
        if index < 0 or index >= len(self._pages):
            return
        self._current_index = index
        _, widget = self._pages[index]
        self._stack.setCurrentWidget(widget)
        self._topbar.set_current(index)
        self._update_nav()

    def _update_nav(self):
        idx = self._current_index
        total = len(self._pages)

        # Back button
        self._bottom.set_back_visible(idx > 0)
        self._bottom.set_back_enabled(not self._is_installing)

        # Cancel button
        if self._is_finished:
            self._bottom.set_cancel_visible(False)
        else:
            self._bottom.set_cancel_visible(True)
            self._bottom.set_cancel_text("Cancel")

        # Next/Install/Finish button
        self._bottom.set_next_visible(True)
        if self._is_finished:
            self._bottom.set_next_text("Finish")
            self._bottom.set_next_enabled(True)
        elif self._is_installing:
            self._bottom.set_next_text("Installing...")
            self._bottom.set_next_enabled(False)
            self._bottom.set_back_enabled(False)
        elif idx == self._install_step - 1:
            self._bottom.set_next_text("Install")
            self._bottom.set_next_enabled(True)
        elif idx >= total - 1:
            self._bottom.set_next_text("Finish")
            self._bottom.set_next_enabled(True)
        else:
            self._bottom.set_next_text("Next")
            self._bottom.set_next_enabled(True)

    def set_installing(self, installing: bool):
        self._is_installing = installing
        self._update_nav()

    def set_finished(self, finished: bool):
        self._is_finished = finished
        self._is_installing = False
        self._update_nav()

    # ── Handlers ───────────────────────────────────────────────

    def _on_back(self):
        if self._current_index > 0 and not self._is_installing:
            self.navigate(self._current_index - 1)

    def _on_next(self):
        if self._is_finished:
            self.finished.emit()
            self.close()
            return

        # Validate current page before advancing
        _, widget = self._pages[self._current_index]
        if hasattr(widget, "validate") and not widget.validate():
            return

        if self._current_index < len(self._pages) - 1:
            self.navigate(self._current_index + 1)

    def _on_cancel(self):
        if self._is_installing:
            self.cancel_install.emit()
            self._bottom.set_cancel_text("Cancelling...")
            self._bottom.set_cancel_enabled(False)
            return
        self.cancelled.emit()
        self.close()

    def closeEvent(self, event):
        if self._is_installing:
            event.ignore()
            return
        super().closeEvent(event)
