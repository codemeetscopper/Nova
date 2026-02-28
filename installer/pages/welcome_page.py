"""Welcome page — first page of the installer wizard."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from installer.core.icons import IconManager
from installer.core.style import StyleManager


class WelcomePage(QWidget):
    install_now = Signal()
    customize = Signal()

    def __init__(self, app_name: str = "Application",
                 app_version: str = "1.0.0",
                 description: str = "",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("WelcomePage")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(0)

        # Top spacer
        outer.addStretch(1)

        # Card
        card = QFrame()
        card.setObjectName("WelcomeCard")
        card.setFrameShape(QFrame.StyledPanel)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        v = QVBoxLayout(card)
        v.setContentsMargins(32, 24, 32, 24)
        v.setSpacing(8)

        # Icon
        icon_label = QLabel()
        icon_label.setObjectName("WelcomeIcon")
        icon_label.setFixedSize(48, 48)
        icon_label.setAlignment(Qt.AlignCenter)
        accent = StyleManager.get_colour("accent")
        px = IconManager.get_pixmap("installer", accent, 40)
        if px and not px.isNull():
            icon_label.setPixmap(px)
            icon_label.setStyleSheet("background: transparent;")
        v.addWidget(icon_label, 0, Qt.AlignCenter)

        # App name
        name = QLabel(app_name)
        name.setObjectName("WelcomeAppName")
        name.setAlignment(Qt.AlignCenter)
        v.addWidget(name)

        # Version
        ver = QLabel(f"Version {app_version}")
        ver.setObjectName("WelcomeVersion")
        ver.setAlignment(Qt.AlignCenter)
        v.addWidget(ver)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("WelcomeSep")
        v.addWidget(sep)

        v.addSpacing(4)

        # Description
        if description:
            html_desc = description.replace("\n", "<br>")
            desc = QLabel(html_desc)
            desc.setTextFormat(Qt.RichText)
        else:
            desc = QLabel(
                f"This wizard will guide you through the installation of "
                f"{app_name} on your computer."
            )
            desc.setTextFormat(Qt.RichText)
        desc.setObjectName("WelcomeDescription")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        v.addWidget(desc)

        v.addSpacing(16)

        # Action buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.setContentsMargins(0, 0, 0, 0)

        btn_row.addStretch()

        self._btn_install_now = QPushButton("Install Now")
        self._btn_install_now.setObjectName("InstallNowButton")
        self._btn_install_now.setCursor(Qt.PointingHandCursor)
        self._btn_install_now.setFixedHeight(36)
        self._btn_install_now.setMinimumWidth(140)
        self._btn_install_now.clicked.connect(self.install_now)
        btn_row.addWidget(self._btn_install_now)

        self._btn_customize = QPushButton("Customize Installation")
        self._btn_customize.setObjectName("CustomizeButton")
        self._btn_customize.setCursor(Qt.PointingHandCursor)
        self._btn_customize.setFixedHeight(36)
        self._btn_customize.setMinimumWidth(160)
        self._btn_customize.clicked.connect(self.customize)
        btn_row.addWidget(self._btn_customize)

        btn_row.addStretch()

        v.addLayout(btn_row)

        outer.addWidget(card)

        # Bottom spacer
        outer.addStretch(1)
