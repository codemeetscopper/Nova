"""Finish page — shown after installation completes."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QLabel, QSizePolicy,
    QVBoxLayout, QWidget,
)

from installer.core.icons import IconManager
from installer.core.style import StyleManager


class FinishPage(QWidget):
    def __init__(self, app_name: str = "Application",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._app_name = app_name
        self.setObjectName("FinishPage")

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)
        outer.setContentsMargins(24, 24, 24, 24)

        card = QFrame()
        card.setObjectName("FinishCard")
        card.setFrameShape(QFrame.StyledPanel)
        card.setMaximumWidth(480)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        v = QVBoxLayout(card)
        v.setContentsMargins(28, 28, 28, 28)
        v.setSpacing(12)
        v.setAlignment(Qt.AlignCenter)

        # Success icon
        self._icon_label = QLabel()
        self._icon_label.setObjectName("FinishIcon")
        self._icon_label.setFixedSize(48, 48)
        self._icon_label.setAlignment(Qt.AlignCenter)
        v.addWidget(self._icon_label, 0, Qt.AlignCenter)

        # Title
        self._title = QLabel("Installation Complete!")
        self._title.setObjectName("FinishTitle")
        self._title.setAlignment(Qt.AlignCenter)
        v.addWidget(self._title)

        # Description
        self._desc = QLabel(
            f"{app_name} has been successfully installed on your computer."
        )
        self._desc.setObjectName("FinishDescription")
        self._desc.setAlignment(Qt.AlignCenter)
        self._desc.setWordWrap(True)
        v.addWidget(self._desc)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("FinishSep")
        v.addWidget(sep)

        # Launch checkbox
        self._launch_cb = QCheckBox(f"Launch {app_name} after closing")
        self._launch_cb.setObjectName("LaunchCheckbox")
        self._launch_cb.setChecked(True)
        self._launch_cb.setCursor(Qt.PointingHandCursor)
        v.addWidget(self._launch_cb, 0, Qt.AlignCenter)

        outer.addWidget(card)

        self._refresh_icon(True)

    @property
    def launch_after(self) -> bool:
        return self._launch_cb.isChecked()

    def set_error_detail(self, error: str):
        """Store error detail to show on the finish page."""
        self._error_detail = error

    def set_success(self, success: bool):
        self._refresh_icon(success)
        if success:
            self._title.setText("Installation Complete!")
            self._desc.setText(
                f"{self._app_name} has been successfully installed on your computer."
            )
            self._launch_cb.setVisible(True)
        else:
            self._title.setText("Installation Failed")
            self._title.setStyleSheet(
                "color: #EF4444; font-size: 22px; font-weight: 600;"
                " background: transparent;"
            )
            detail = getattr(self, "_error_detail", "")
            if detail:
                self._desc.setText(f"Error: {detail}")
            else:
                self._desc.setText(
                    "Something went wrong during installation.\n"
                    "Please check the installation log for details."
                )
            self._launch_cb.setVisible(False)

    def set_uninstall_success(self, app_name: str):
        """Show uninstall success state."""
        self._refresh_icon(True)
        self._title.setText("Uninstall Complete")
        accent = StyleManager.get_colour("accent")
        self._title.setStyleSheet(
            f"color: {accent}; font-size: 18px; font-weight: 600;"
            " background: transparent;"
        )
        self._desc.setText(
            f"{app_name} has been successfully removed from your computer."
        )
        self._launch_cb.setVisible(False)

    def _refresh_icon(self, success: bool):
        if success:
            icon_name = "check_circle"
            color = "#22C55E"
        else:
            icon_name = "error"
            color = "#EF4444"
        px = IconManager.get_pixmap(icon_name, color, 40)
        if px and not px.isNull():
            self._icon_label.setPixmap(px)
            self._icon_label.setStyleSheet("background: transparent;")
