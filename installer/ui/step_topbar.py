"""
Step topbar — animated horizontal progress stepper for the installer wizard.

Each step is a painted circle with an icon/checkmark inside and a label below.
Connectors between steps animate left-to-right when a step completes.

States:
  - completed: accent-filled circle with white checkmark, accent label
  - active:    accent-bordered circle with accent icon, bold accent label
  - upcoming:  gray-bordered circle with gray icon, dim label
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import (
    Property, QEasingCurve, QPropertyAnimation, QRectF, Qt,
)
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy,
    QVBoxLayout, QWidget,
)

# Step icons mapped by title
_STEP_ICONS = {
    "Welcome": "home",
    "License": "gavel",
    "Install Type": "layers",
    "Location": "folder",
    "Options": "settings",
    "Installing": "downloading",
    "Processing": "downloading",
    "Complete": "celebration",
    "Maintenance": "build",
}

_CIRCLE_SIZE = 28
_ICON_SIZE = 14
_CHECK_SIZE = 12


def _get_colour(key: str) -> str:
    try:
        from installer.core.style import StyleManager
        return StyleManager.get_colour(key)
    except Exception:
        defaults = {
            "accent": "#0088CC", "bg2": "#E0E0E0",
            "fg": "#1A1A1A", "fg2": "#999999",
        }
        return defaults.get(key, "#888888")


def _get_pixmap(name: str, color: str, size: int) -> Optional[QPixmap]:
    try:
        from installer.core.icons import IconManager
        return IconManager.get_pixmap(name, color, size)
    except Exception:
        return None


# ── Step Circle ────────────────────────────────────────────────

class _StepCircle(QWidget):
    """
    A single step indicator: painted circle with icon + label below.
    """

    def __init__(self, index: int, title: str, icon_name: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._index = index
        self._title_text = title
        self._icon_name = icon_name
        self._state = "upcoming"  # upcoming | active | completed

        self.setObjectName("StepCircle")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        # Reserve space for the painted circle
        self._circle_widget = QWidget()
        self._circle_widget.setFixedSize(_CIRCLE_SIZE, _CIRCLE_SIZE)
        self._circle_widget.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._circle_widget.setStyleSheet("background: transparent;")
        layout.addWidget(self._circle_widget, 0, Qt.AlignCenter)

        # Label
        self._label = QLabel(title)
        self._label.setObjectName("StepLabel")
        self._label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._label, 0, Qt.AlignCenter)

        self._update_style()

    def set_state(self, state: str):
        if self._state == state:
            return
        self._state = state
        self._update_style()
        self.update()

    def _update_style(self):
        accent = _get_colour("accent")
        fg2 = _get_colour("fg2")

        if self._state == "completed":
            self._label.setStyleSheet(
                f"color: {accent}; font-size: 10px; font-weight: 500;"
                " background: transparent;"
            )
        elif self._state == "active":
            self._label.setStyleSheet(
                f"color: {accent}; font-size: 10px; font-weight: 700;"
                " background: transparent;"
            )
        else:
            self._label.setStyleSheet(
                f"color: {fg2}; font-size: 10px; font-weight: 400;"
                " background: transparent;"
            )

    def paintEvent(self, event):
        super().paintEvent(event)

        cw = self._circle_widget
        rect = QRectF(cw.x(), cw.y(), _CIRCLE_SIZE, _CIRCLE_SIZE)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        accent = QColor(_get_colour("accent"))
        bg2 = QColor(_get_colour("bg2"))
        fg2 = QColor(_get_colour("fg2"))

        cx = rect.center().x()
        cy = rect.center().y()
        radius = _CIRCLE_SIZE / 2 - 1

        if self._state == "completed":
            # Filled accent circle
            painter.setPen(Qt.NoPen)
            painter.setBrush(accent)
            painter.drawEllipse(rect.center(), radius, radius)
            # White checkmark
            px = _get_pixmap("check", "#FFFFFF", _CHECK_SIZE)
            if px and not px.isNull():
                painter.drawPixmap(
                    int(cx - _CHECK_SIZE / 2),
                    int(cy - _CHECK_SIZE / 2),
                    px,
                )

        elif self._state == "active":
            # Accent border circle
            painter.setPen(QPen(accent, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(rect.center(), radius, radius)
            # Accent icon
            px = _get_pixmap(self._icon_name, accent.name(), _ICON_SIZE)
            if px and not px.isNull():
                painter.drawPixmap(
                    int(cx - _ICON_SIZE / 2),
                    int(cy - _ICON_SIZE / 2),
                    px,
                )

        else:
            # Gray border circle
            painter.setPen(QPen(bg2, 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(rect.center(), radius, radius)
            # Gray icon
            px = _get_pixmap(self._icon_name, fg2.name(), _ICON_SIZE)
            if px and not px.isNull():
                painter.drawPixmap(
                    int(cx - _ICON_SIZE / 2),
                    int(cy - _ICON_SIZE / 2),
                    px,
                )

        painter.end()


# ── Animated Connector ─────────────────────────────────────────

class _AnimatedConnector(QWidget):
    """
    Horizontal line between steps. Animates fill from 0% to 100%
    when the preceding step is completed.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("StepConnector")
        self.setFixedHeight(2)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._progress = 0.0
        self._anim: Optional[QPropertyAnimation] = None

    def _get_progress(self) -> float:
        return self._progress

    def _set_progress(self, val: float):
        self._progress = val
        self.update()

    progress = Property(float, _get_progress, _set_progress)

    def animate_to(self, target: float, duration: int = 300):
        if self._anim is not None:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b"progress")
        self._anim.setDuration(duration)
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

    def set_progress_immediate(self, val: float):
        self._progress = val
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        accent = QColor(_get_colour("accent"))
        bg2 = QColor(_get_colour("bg2"))

        # Background track
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg2)
        painter.drawRoundedRect(0, 0, w, h, 1, 1)

        # Filled portion
        if self._progress > 0:
            fill_w = int(w * self._progress)
            painter.setBrush(accent)
            painter.drawRoundedRect(0, 0, fill_w, h, 1, 1)

        painter.end()


# ── Step Topbar ────────────────────────────────────────────────

class StepTopbar(QFrame):
    """Horizontal step indicator bar with animated connectors."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("StepTopbar")
        self.setFixedHeight(64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._steps: List[_StepCircle] = []
        self._connectors: List[_AnimatedConnector] = []
        self._current = 0

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(24, 6, 24, 2)
        self._layout.setSpacing(0)

    def set_steps(self, titles: List[str]):
        # Clear existing
        while self._layout.count():
            child = self._layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._steps.clear()
        self._connectors.clear()

        for i, title in enumerate(titles):
            if i > 0:
                conn = _AnimatedConnector()
                self._layout.addWidget(conn, 1, Qt.AlignVCenter)
                self._connectors.append(conn)

            icon_name = _STEP_ICONS.get(title, "info")
            step = _StepCircle(i, title, icon_name)
            self._layout.addWidget(step, 0, Qt.AlignCenter)
            self._steps.append(step)

        if self._steps:
            self._steps[0].set_state("active")
        self._current = 0

    def set_current(self, index: int):
        self._current = index

        # Update circle states
        for i, step in enumerate(self._steps):
            if i < index:
                step.set_state("completed")
            elif i == index:
                step.set_state("active")
            else:
                step.set_state("upcoming")

        # Update connector animations
        for i, conn in enumerate(self._connectors):
            if i < index - 1:
                # Already completed — snap to full
                conn.set_progress_immediate(1.0)
            elif i == index - 1:
                # Leading to current step — animate
                conn.animate_to(1.0, 300)
            else:
                # Upcoming — snap to empty
                conn.set_progress_immediate(0.0)

    def set_app_info(self, name: str, version: str):
        pass
