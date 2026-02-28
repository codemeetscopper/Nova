"""License agreement page."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QLabel, QScrollArea,
    QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)


class LicensePage(QWidget):
    accepted_changed = Signal(bool)

    def __init__(self, license_file: str = "",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("LicensePage")
        self._accepted = True

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(10)

        # Title
        title = QLabel("License Agreement")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        subtitle = QLabel("Please review the license terms before proceeding.")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(subtitle)

        # License text area
        self._text = QTextEdit()
        self._text.setObjectName("LicenseText")
        self._text.setReadOnly(True)
        self._text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        if license_file:
            p = Path(license_file)
            if p.exists():
                self._text.setPlainText(p.read_text(encoding="utf-8"))
            else:
                self._text.setPlainText(f"License file not found: {license_file}")
        else:
            self._text.setPlainText(
                "MIT License\n\n"
                "Copyright (c) 2024\n\n"
                "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
                "of this software and associated documentation files (the \"Software\"), to deal\n"
                "in the Software without restriction, including without limitation the rights\n"
                "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
                "copies of the Software, and to permit persons to whom the Software is\n"
                "furnished to do so, subject to the following conditions:\n\n"
                "The above copyright notice and this permission notice shall be included in all\n"
                "copies or substantial portions of the Software.\n\n"
                "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n"
                "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
                "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT."
            )

        root.addWidget(self._text, 1)

        # Accept checkbox
        self._accept_cb = QCheckBox("I accept the terms of the license agreement")
        self._accept_cb.setObjectName("LicenseAcceptCheckbox")
        self._accept_cb.setCursor(Qt.PointingHandCursor)
        self._accept_cb.setChecked(True)
        self._accept_cb.toggled.connect(self._on_toggled)
        root.addWidget(self._accept_cb)

    def validate(self) -> bool:
        return self._accepted

    def _on_toggled(self, checked: bool):
        self._accepted = checked
        self.accepted_changed.emit(checked)
