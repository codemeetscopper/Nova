"""Progress page — shows installation progress with a progress bar and log."""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QProgressBar, QSizePolicy,
    QTextEdit, QVBoxLayout, QWidget,
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

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

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

        # Percentage label
        self._pct_label = QLabel("0%")
        self._pct_label.setObjectName("ProgressPct")
        self._pct_label.setAlignment(Qt.AlignRight)
        root.addWidget(self._pct_label)

        # Log area
        log_title = QLabel("INSTALLATION LOG")
        log_title.setObjectName("SectionLabel")
        root.addWidget(log_title)

        self._log = QTextEdit()
        self._log.setObjectName("ProgressLog")
        self._log.setReadOnly(True)
        self._log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self._log, 1)

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
                f"color: #EF4444; font-size: 22px; font-weight: 300;"
            )

    def reset(self):
        self._title.setText("Installing...")
        self._subtitle.setText("Please wait while the application is being installed.")
        self._operation.setText("")
        self._progress.setValue(0)
        self._pct_label.setText("0%")
        self._log.clear()
