"""Installation type page — admin (per-machine) vs user (per-user)."""
from __future__ import annotations

import ctypes
import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy,
    QVBoxLayout, QWidget,
)

from installer.core.icons import IconManager
from installer.core.style import StyleManager


def _is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


class _TypeCard(QFrame):
    """A selectable card for installation type."""

    clicked = Signal()

    def __init__(self, icon_name: str, title: str, description: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TypeCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._selected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        # Icon
        self._icon_label = QLabel()
        self._icon_label.setObjectName("TypeCardIcon")
        self._icon_label.setFixedSize(32, 32)
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_name = icon_name
        self._refresh_icon()
        layout.addWidget(self._icon_label, 0, Qt.AlignVCenter)

        # Text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("TypeCardTitle")
        text_layout.addWidget(self._title_label)

        self._desc_label = QLabel(description)
        self._desc_label.setObjectName("TypeCardDesc")
        self._desc_label.setWordWrap(True)
        text_layout.addWidget(self._desc_label)

        layout.addLayout(text_layout, 1)

        # Selection indicator
        self._check = QLabel()
        self._check.setObjectName("TypeCardCheck")
        self._check.setFixedSize(24, 24)
        self._check.setAlignment(Qt.AlignCenter)
        self._check.hide()
        layout.addWidget(self._check, 0, Qt.AlignVCenter)

    @property
    def selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool):
        self._selected = selected
        accent = StyleManager.get_colour("accent")
        bg2 = StyleManager.get_colour("bg2")

        if selected:
            self.setStyleSheet(
                f"#TypeCard {{ border: 2px solid {accent}; }}"
            )
            px = IconManager.get_pixmap("check_circle", accent, 20)
            if px and not px.isNull():
                self._check.setPixmap(px)
                self._check.setStyleSheet("background: transparent;")
            self._check.show()
        else:
            self.setStyleSheet(
                f"#TypeCard {{ border: 1px solid {bg2}; }}"
            )
            self._check.hide()

        self._refresh_icon()

    def _refresh_icon(self):
        accent = StyleManager.get_colour("accent")
        fg1 = StyleManager.get_colour("fg1")
        color = accent if self._selected else fg1
        px = IconManager.get_pixmap(self._icon_name, color, 24)
        if px and not px.isNull():
            self._icon_label.setPixmap(px)
            self._icon_label.setStyleSheet("background: transparent;")

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit()


class InstallTypePage(QWidget):
    type_changed = Signal(str)  # "admin" or "user"

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("InstallTypePage")
        self._install_type = "user"

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        title = QLabel("Installation Type")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        subtitle = QLabel("Choose how to install the application.")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(subtitle)

        root.addSpacing(4)

        # Admin card
        self._admin_card = _TypeCard(
            "admin",
            "Install for all users",
            "Requires administrator privileges. Installs to Program Files\n"
            "and is available to all users on this computer.",
        )
        self._admin_card.clicked.connect(lambda: self._select("admin"))
        root.addWidget(self._admin_card)

        # User card
        self._user_card = _TypeCard(
            "person",
            "Install for current user only",
            "No administrator privileges required. Installs to your\n"
            "user profile and is only available to you.",
        )
        self._user_card.clicked.connect(lambda: self._select("user"))
        root.addWidget(self._user_card)

        # Info label
        if _is_admin():
            info_text = "You are running as administrator. Both options are available."
        else:
            info_text = "You are not running as administrator. Per-user installation is recommended."
        self._info = QLabel(info_text)
        self._info.setObjectName("InstallTypeInfo")
        self._info.setWordWrap(True)
        root.addWidget(self._info)

        root.addStretch()

        # Default selection
        self._select("user")

    @property
    def install_type(self) -> str:
        return self._install_type

    def _select(self, type_: str):
        self._install_type = type_
        self._admin_card.set_selected(type_ == "admin")
        self._user_card.set_selected(type_ == "user")
        self.type_changed.emit(type_)
