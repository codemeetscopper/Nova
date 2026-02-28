"""Maintenance page — shown when application is already installed."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy,
    QVBoxLayout, QWidget,
)

from installer.core.icons import IconManager
from installer.core.style import StyleManager


class _ActionCard(QFrame):
    """A selectable card for maintenance actions."""

    clicked = Signal()

    def __init__(self, icon_name: str, title: str, description: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TypeCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(62)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._selected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        # Icon
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(28, 28)
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_name = icon_name
        self._refresh_icon()
        layout.addWidget(self._icon_label, 0, Qt.AlignVCenter)

        # Text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("TypeCardTitle")
        text_layout.addWidget(self._title_label)

        self._desc_label = QLabel(description)
        self._desc_label.setObjectName("TypeCardDesc")
        self._desc_label.setWordWrap(True)
        text_layout.addWidget(self._desc_label)

        layout.addLayout(text_layout, 1)

        # Check mark
        self._check = QLabel()
        self._check.setFixedSize(20, 20)
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
            px = IconManager.get_pixmap("check_circle", accent, 16)
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
        px = IconManager.get_pixmap(self._icon_name, color, 22)
        if px and not px.isNull():
            self._icon_label.setPixmap(px)
            self._icon_label.setStyleSheet("background: transparent;")

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit()


class MaintenancePage(QWidget):
    """Shown when app is already installed — Modify, Repair, or Uninstall."""

    action_changed = Signal(str)  # "modify", "repair", "uninstall"

    def __init__(self, app_name: str = "Application",
                 install_path: str = "",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("InstallTypePage")
        self._action = "repair"

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        title = QLabel(f"{app_name} is already installed")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Choose what you would like to do with the existing installation."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        if install_path:
            path_label = QLabel(f"Installed at: {install_path}")
            path_label.setObjectName("InstallTypeInfo")
            path_label.setWordWrap(True)
            root.addWidget(path_label)

        root.addSpacing(4)

        # Modify card
        self._modify_card = _ActionCard(
            "tune",
            "Modify",
            "Change installed components and shortcut options.",
        )
        self._modify_card.clicked.connect(lambda: self._select("modify"))
        root.addWidget(self._modify_card)

        # Repair card
        self._repair_card = _ActionCard(
            "build",
            "Repair",
            "Re-install the application to fix corrupted or missing files.",
        )
        self._repair_card.clicked.connect(lambda: self._select("repair"))
        root.addWidget(self._repair_card)

        # Update card
        self._update_card = _ActionCard(
            "update",
            "Update",
            "Re-build and install the latest version of the application.",
        )
        self._update_card.clicked.connect(lambda: self._select("update"))
        root.addWidget(self._update_card)

        # Uninstall card
        self._uninstall_card = _ActionCard(
            "delete",
            "Uninstall",
            "Remove the application, shortcuts, and registry entries.",
        )
        self._uninstall_card.clicked.connect(lambda: self._select("uninstall"))
        root.addWidget(self._uninstall_card)

        root.addStretch()

        # Default selection
        self._select("repair")

    @property
    def selected_action(self) -> str:
        return self._action

    def _select(self, action: str):
        self._action = action
        self._modify_card.set_selected(action == "modify")
        self._repair_card.set_selected(action == "repair")
        self._update_card.set_selected(action == "update")
        self._uninstall_card.set_selected(action == "uninstall")
        self.action_changed.emit(action)
