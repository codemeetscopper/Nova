"""
Step sidebar — vertical step indicator for the installer wizard.

Shows numbered circles with step titles. States:
  - completed: accent checkmark circle
  - active:    accent filled circle with white number
  - upcoming:  dim outlined circle
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy,
    QVBoxLayout, QWidget,
)

SIDEBAR_WIDTH = 220

_STEP_HEIGHT = 40
_CIRCLE_SIZE = 26
_CONNECTOR_WIDTH = 2


def _accent() -> str:
    try:
        from installer.core.style import StyleManager
        return StyleManager.get_colour("accent")
    except Exception:
        return "#0088CC"


def _bg1() -> str:
    try:
        from installer.core.style import StyleManager
        return StyleManager.get_colour("bg1")
    except Exception:
        return "#1D1D1D"


def _bg2() -> str:
    try:
        from installer.core.style import StyleManager
        return StyleManager.get_colour("bg2")
    except Exception:
        return "#262626"


def _fg() -> str:
    try:
        from installer.core.style import StyleManager
        return StyleManager.get_colour("fg")
    except Exception:
        return "#FFFFFF"


def _fg1() -> str:
    try:
        from installer.core.style import StyleManager
        return StyleManager.get_colour("fg1")
    except Exception:
        return "#D9D9D9"


def _fg2() -> str:
    try:
        from installer.core.style import StyleManager
        return StyleManager.get_colour("fg2")
    except Exception:
        return "#B3B3B3"


class StepItem(QWidget):
    """A single step row: circle + title + optional subtitle."""

    def __init__(self, index: int, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._index = index
        self._title_text = title
        self._state = "upcoming"  # upcoming | active | completed
        self.setObjectName("StepItem")
        self.setFixedHeight(_STEP_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(10)

        # Circle indicator
        self._circle = QLabel()
        self._circle.setObjectName("StepCircle")
        self._circle.setFixedSize(_CIRCLE_SIZE, _CIRCLE_SIZE)
        self._circle.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._circle, 0, Qt.AlignVCenter)

        # Title
        self._title = QLabel(title)
        self._title.setObjectName("StepTitle")
        self._title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        layout.addWidget(self._title, 1, Qt.AlignVCenter)

        self._apply_style()

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str):
        if self._state == state:
            return
        self._state = state
        self._apply_style()

    def _apply_style(self):
        accent = _accent()
        fg = _fg()
        fg1 = _fg1()
        fg2 = _fg2()
        bg2 = _bg2()

        if self._state == "completed":
            # Accent circle with checkmark
            self._circle.setText("")
            try:
                from installer.core.icons import IconManager
                px = IconManager.get_pixmap("check", "#FFFFFF", 16)
                if px and not px.isNull():
                    self._circle.setPixmap(px)
                else:
                    self._circle.setText("\u2713")
            except Exception:
                self._circle.setText("\u2713")
            self._circle.setStyleSheet(
                f"background-color: {accent}; color: white;"
                f" border-radius: {_CIRCLE_SIZE // 2}px;"
                f" font-size: 11px; font-weight: 700; border: none;"
            )
            self._title.setStyleSheet(
                f"color: {fg1}; font-size: 12px; font-weight: 400;"
                " background: transparent;"
            )

        elif self._state == "active":
            self._circle.setPixmap(QPixmap())  # clear pixmap
            self._circle.setText(str(self._index + 1))
            self._circle.setStyleSheet(
                f"background-color: {accent}; color: white;"
                f" border-radius: {_CIRCLE_SIZE // 2}px;"
                f" font-size: 11px; font-weight: 700; border: none;"
            )
            self._title.setStyleSheet(
                f"color: {fg}; font-size: 12px; font-weight: 600;"
                " background: transparent;"
            )

        else:  # upcoming
            self._circle.setPixmap(QPixmap())
            self._circle.setText(str(self._index + 1))
            self._circle.setStyleSheet(
                f"background-color: transparent; color: {fg2};"
                f" border-radius: {_CIRCLE_SIZE // 2}px;"
                f" font-size: 11px; font-weight: 500;"
                f" border: 1.5px solid {bg2};"
            )
            self._title.setStyleSheet(
                f"color: {fg2}; font-size: 12px; font-weight: 400;"
                " background: transparent;"
            )


class StepConnector(QWidget):
    """Thin vertical line between steps."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("StepConnector")
        self.setFixedHeight(4)
        self._apply_style()

    def set_completed(self, completed: bool):
        self._completed = completed
        self._apply_style()

    def _apply_style(self):
        completed = getattr(self, "_completed", False)
        color = _accent() if completed else _bg2()
        left_margin = 16 + (_CIRCLE_SIZE // 2) - 1
        self.setStyleSheet(
            f"margin-left: {left_margin}px;"
            f" border-left: {_CONNECTOR_WIDTH}px solid {color};"
            " background: transparent;"
        )


class StepSidebar(QFrame):
    """
    Vertical step indicator sidebar for the installer wizard.

    Layout:
      Logo/Title
      Steps with connectors
      Stretch
      Version info
    """

    def __init__(self, app_name: str = "Nova Installer",
                 app_version: str = "1.0.0",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("StepSidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._steps: List[StepItem] = []
        self._connectors: List[StepConnector] = []
        self._current = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──────────────────────────────────────────
        header = QWidget()
        header.setObjectName("StepSidebarHeader")
        header.setFixedHeight(60)
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(16, 14, 12, 6)
        h_layout.setSpacing(2)

        # Logo icon + app name
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self._logo_icon = QLabel()
        self._logo_icon.setObjectName("StepSidebarLogo")
        self._logo_icon.setFixedSize(20, 20)
        self._logo_icon.setAlignment(Qt.AlignCenter)
        self._refresh_logo()
        top_row.addWidget(self._logo_icon, 0, Qt.AlignVCenter)

        self._app_name = QLabel(app_name)
        self._app_name.setObjectName("StepSidebarAppName")
        top_row.addWidget(self._app_name, 1, Qt.AlignVCenter)

        h_layout.addLayout(top_row)

        self._version_label = QLabel(f"v{app_version}")
        self._version_label.setObjectName("StepSidebarVersion")
        h_layout.addWidget(self._version_label)

        root.addWidget(header)

        # ── Separator ───────────────────────────────────────
        sep = QFrame()
        sep.setObjectName("StepSidebarSep")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # ── Steps container ──────────────────────────────────
        self._steps_container = QWidget()
        self._steps_container.setObjectName("StepSidebarSteps")
        self._steps_layout = QVBoxLayout(self._steps_container)
        self._steps_layout.setContentsMargins(0, 10, 0, 10)
        self._steps_layout.setSpacing(0)
        root.addWidget(self._steps_container)

        root.addStretch()

        # ── Footer ──────────────────────────────────────────
        footer = QLabel("Nova Installer")
        footer.setObjectName("StepSidebarFooter")
        footer.setAlignment(Qt.AlignCenter)
        footer.setFixedHeight(28)
        root.addWidget(footer)

    def set_steps(self, titles: List[str]):
        """Initialize the step list."""
        # Clear existing
        while self._steps_layout.count():
            child = self._steps_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._steps.clear()
        self._connectors.clear()

        for i, title in enumerate(titles):
            if i > 0:
                conn = StepConnector()
                self._steps_layout.addWidget(conn)
                self._connectors.append(conn)

            step = StepItem(i, title)
            self._steps_layout.addWidget(step)
            self._steps.append(step)

        if self._steps:
            self._steps[0].set_state("active")
        self._current = 0

    def set_current(self, index: int):
        """Update step states based on current index."""
        self._current = index
        for i, step in enumerate(self._steps):
            if i < index:
                step.set_state("completed")
            elif i == index:
                step.set_state("active")
            else:
                step.set_state("upcoming")

        for i, conn in enumerate(self._connectors):
            conn.set_completed(i < index)

    def set_app_info(self, name: str, version: str):
        self._app_name.setText(name)
        self._version_label.setText(f"v{version}")

    def _refresh_logo(self):
        try:
            from installer.core.icons import IconManager
            accent = _accent()
            px = IconManager.get_pixmap("logo", accent, 20)
            if px and not px.isNull():
                self._logo_icon.setPixmap(px)
                self._logo_icon.setStyleSheet("background: transparent;")
                return
        except Exception:
            pass
        self._logo_icon.setText("\u2B22")
