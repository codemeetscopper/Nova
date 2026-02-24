from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)


class StatCard(QFrame):
    """A stat card with a large value and an uppercase label."""

    def __init__(self, title: str, value: str = "0", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)

        self._value_label = QLabel(value)
        self._value_label.setObjectName("StatValue")
        self._value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self._title_label = QLabel(title.upper())
        self._title_label.setObjectName("StatTitle")
        self._title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        layout.addWidget(self._value_label)
        layout.addWidget(self._title_label)

    def set_value(self, value: str):
        self._value_label.setText(value)


class HomePage(QWidget):
    """Home page with at-a-glance stat cards."""

    def __init__(self, ctx, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx = ctx
        self.setObjectName("HomePage")

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        container.setObjectName("HomeContainer")
        root = QVBoxLayout(container)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(24)

        # ── Greeting ─────────────────────────────────────────
        greeting = QLabel("Welcome to Nova")
        greeting.setObjectName("HomeGreeting")
        root.addWidget(greeting)

        subtitle = QLabel("Futuristic plugin-driven application platform")
        subtitle.setObjectName("HomeSubtitle")
        root.addWidget(subtitle)

        # ── Stat cards ────────────────────────────────────────
        cards_row = QWidget()
        cards_layout = QHBoxLayout(cards_row)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(16)

        self._card_loaded = StatCard("Plugins Loaded", "0")
        self._card_active = StatCard("Plugins Active", "0")
        self._card_status = StatCard("Status", "Idle")

        cards_layout.addWidget(self._card_loaded)
        cards_layout.addWidget(self._card_active)
        cards_layout.addWidget(self._card_status)
        root.addWidget(cards_row)

        # ── Description ──────────────────────────────────────
        desc = QLabel(
            "Nova provides a sandboxed, process-isolated plugin runtime.\n"
            "Each plugin runs in its own subprocess and communicates\n"
            "with the host via high-speed local socket IPC."
        )
        desc.setObjectName("HomeDescription")
        desc.setWordWrap(True)
        root.addWidget(desc)

        root.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def update_stats(self, loaded: int, active: int):
        self._card_loaded.set_value(str(loaded))
        self._card_active.set_value(str(active))
        if active > 0:
            status = "Running"
        elif loaded > 0:
            status = "Ready"
        else:
            status = "Idle"
        self._card_status.set_value(status)
