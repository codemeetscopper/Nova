"""Installation path selection page — compact modern layout."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from installer.core.icons import IconManager
from installer.core.style import StyleManager


class PathPage(QWidget):
    path_changed = Signal(str)

    def __init__(self, app_name: str = "Application",
                 default_dir: str = "",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PathPage")
        self._app_name = app_name

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(8)

        title = QLabel("Installation Location")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        subtitle = QLabel(f"Choose where to install {app_name}.")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(subtitle)

        root.addSpacing(6)

        # Path input row — clean, no card wrapper
        path_label = QLabel("DESTINATION FOLDER")
        path_label.setObjectName("PathLabel")
        root.addWidget(path_label)

        row = QHBoxLayout()
        row.setSpacing(6)

        self._path_edit = QLineEdit()
        self._path_edit.setObjectName("PathEdit")
        self._path_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._path_edit.textChanged.connect(self._on_text_changed)
        row.addWidget(self._path_edit, 1)

        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("BrowseButton")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.clicked.connect(self._on_browse)
        row.addWidget(browse_btn)

        root.addLayout(row)

        # Disk space info
        self._space_label = QLabel()
        self._space_label.setObjectName("SpaceLabel")
        root.addWidget(self._space_label)

        # Non-empty directory warning
        self._warning_label = QLabel()
        self._warning_label.setObjectName("PathWarning")
        self._warning_label.setWordWrap(True)
        self._warning_label.hide()
        root.addWidget(self._warning_label)

        # Validation message
        self._error_label = QLabel()
        self._error_label.setObjectName("PathError")
        self._error_label.hide()
        root.addWidget(self._error_label)

        root.addStretch()

        # Set default path
        if default_dir:
            self._path_edit.setText(default_dir)
        else:
            self._set_default_path("user")

    @property
    def install_path(self) -> str:
        return self._path_edit.text()

    def set_install_type(self, type_: str):
        """Update default path based on admin/user selection."""
        self._set_default_path(type_)

    def validate(self) -> bool:
        path = self._path_edit.text().strip()
        if not path:
            self._show_error("Please specify an installation directory.")
            return False
        p = Path(path)
        # Check if parent exists or can be created
        try:
            parent = p.parent
            if not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)
                parent.rmdir()  # Clean up test
        except PermissionError:
            self._show_error("You don't have permission to install to this location.")
            return False
        except Exception as e:
            self._show_error(f"Invalid path: {e}")
            return False
        self._error_label.hide()
        return True

    def _set_default_path(self, type_: str):
        if type_ == "admin":
            base = os.environ.get("ProgramFiles", "C:\\Program Files")
        else:
            base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        self._path_edit.setText(str(Path(base) / self._app_name))

    def _on_browse(self):
        current = self._path_edit.text()
        chosen = QFileDialog.getExistingDirectory(
            self, "Select Installation Directory", current
        )
        if chosen:
            self._path_edit.setText(chosen)

    def _on_text_changed(self, text: str):
        self._update_space_info(text)
        self._check_nonempty(text)
        self.path_changed.emit(text)

    def _update_space_info(self, path: str):
        try:
            import shutil
            p = Path(path)
            while not p.exists() and p.parent != p:
                p = p.parent
            usage = shutil.disk_usage(str(p))
            free_gb = usage.free / (1024 ** 3)
            self._space_label.setText(f"Available disk space: {free_gb:.1f} GB")
            self._space_label.setStyleSheet(
                f"color: {StyleManager.get_colour('fg2')}; font-size: 11px;"
                " background: transparent;"
            )
        except Exception:
            self._space_label.setText("")

    def _check_nonempty(self, path: str):
        try:
            p = Path(path)
            if p.exists() and p.is_dir() and any(p.iterdir()):
                self._warning_label.setText(
                    "This folder is not empty. Existing contents will be "
                    "removed before installation."
                )
                self._warning_label.setStyleSheet(
                    "color: #F59E0B; font-size: 11px; background: transparent;"
                )
                self._warning_label.show()
            else:
                self._warning_label.hide()
        except Exception:
            self._warning_label.hide()

    def _show_error(self, msg: str):
        self._error_label.setText(msg)
        self._error_label.setStyleSheet(
            "color: #EF4444; font-size: 12px; background: transparent;"
        )
        self._error_label.show()
