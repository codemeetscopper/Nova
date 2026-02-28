"""Progress page — shows installation progress with a progress bar and log."""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)

from installer.core.icons import IconManager
from installer.core.style import StyleManager

_log = logging.getLogger(__name__)


class ProgressPage(QWidget):
    """Shows a progress bar and scrolling log during installation."""

    install_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ProgressPage")
        self._log_expanded = False

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(8)

        self._title = QLabel("Installing...")
        self._title.setObjectName("PageTitle")
        root.addWidget(self._title)

        self._subtitle = QLabel("Please wait while the application is being installed.")
        self._subtitle.setObjectName("PageSubtitle")
        self._subtitle.setWordWrap(True)
        root.addWidget(self._subtitle)

        root.addSpacing(4)

        # Current operation label
        self._operation = QLabel("")
        self._operation.setObjectName("ProgressOperation")
        root.addWidget(self._operation)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setObjectName("InstallProgress")
        self._progress.setMinimum(0)
        self._progress.setMaximum(100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFixedHeight(8)
        self._progress.setFormat("")
        root.addWidget(self._progress)

        # Row: percentage left, expander toggle right — pinned under progress bar
        pct_row = QHBoxLayout()
        pct_row.setSpacing(0)

        self._pct_label = QLabel("0%")
        self._pct_label.setObjectName("ProgressPct")
        pct_row.addWidget(self._pct_label)

        pct_row.addStretch()

        self._log_toggle = QPushButton()
        self._log_toggle.setObjectName("LogExpanderButton")
        self._log_toggle.setFixedSize(24, 24)
        self._log_toggle.setCursor(Qt.PointingHandCursor)
        self._log_toggle.setToolTip("Show installation log")
        self._log_toggle.clicked.connect(self._toggle_log)
        self._update_chevron_icon()
        pct_row.addWidget(self._log_toggle)

        root.addLayout(pct_row)

        # Log area — hidden by default, fills remaining space when visible
        self._log = QTextEdit()
        self._log.setObjectName("ProgressLog")
        self._log.setReadOnly(True)
        self._log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._log.setVisible(False)
        root.addWidget(self._log, 1)

        # Spacer to keep progress info centered when log is hidden
        self._spacer = QWidget()
        self._spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self._spacer, 1)

    def _update_chevron_icon(self):
        fg2 = StyleManager.get_colour("fg2")
        icon_name = "chevron_up" if self._log_expanded else "chevron_down"
        px = IconManager.get_pixmap(icon_name, fg2, 16)
        if px and not px.isNull():
            self._log_toggle.setIcon(QIcon(px))
            self._log_toggle.setIconSize(QSize(16, 16))

    def _toggle_log(self):
        self._log_expanded = not self._log_expanded
        self._log.setVisible(self._log_expanded)
        self._spacer.setVisible(not self._log_expanded)
        self._log_toggle.setToolTip(
            "Hide installation log" if self._log_expanded else "Show installation log"
        )
        self._update_chevron_icon()

    def set_progress(self, value: int):
        self._progress.setValue(value)
        self._pct_label.setText(f"{value}%")

    def set_operation(self, text: str):
        self._operation.setText(text)

    def append_log(self, text: str):
        self._log.append(text)
        # Auto scroll
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_completed(self, success: bool):
        if success:
            self._title.setText("Installation Complete")
            self._subtitle.setText("The application has been installed successfully.")
            self._operation.setText("")
            self.set_progress(100)
        else:
            self._title.setText("Installation Failed")
            self._subtitle.setText("An error occurred during installation.")
            self._title.setStyleSheet(
                "color: #EF4444; font-size: 22px; font-weight: 300;"
            )

    def reset(self):
        self._title.setText("Installing...")
        self._subtitle.setText("Please wait while the application is being installed.")
        self._operation.setText("")
        self._progress.setValue(0)
        self._pct_label.setText("0%")
        self._log.clear()
        self._log_expanded = False
        self._log.setVisible(False)
        self._spacer.setVisible(True)
        self._update_chevron_icon()
