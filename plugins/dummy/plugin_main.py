"""
Dummy Plugin
============
A template plugin demonstrating settings and SVG icons.

Author  : Antigravity
Version : 1.0.0
"""
from __future__ import annotations

import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget
from nova.core.plugin_base import PluginBase, PluginSetting


class Plugin(PluginBase):
    """Main plugin class."""

    def __init__(self, bridge):
        super().__init__(bridge)
        self._label: QLabel | None = None
        self._layout: QVBoxLayout | None = None
        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh_ui)

    # ── HOST: Settings ────────────────────────────────────────────────────────

    def get_settings(self) -> list[PluginSetting]:
        return [
            PluginSetting(
                key="show_greeting",
                name="Show Greeting",
                type="bool",
                default=True,
                description="Toggle the greeting message."
            ),
            PluginSetting(
                key="greeting_text",
                name="Greeting Text",
                type="text",
                default="Hello from Dummy Plugin!",
                description="The text to display."
            ),
            PluginSetting(
                key="bg_color",
                name="Background Color",
                type="colorpicker",
                default="#222222",
                description="Background color for the widget."
            )
        ]

    # ── HOST: UI ──────────────────────────────────────────────────────────────

    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        frame = QFrame(parent)
        self._layout = QVBoxLayout(frame)
        self._layout.setAlignment(Qt.AlignCenter)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(self._label)

        # Stop the timer and clear refs when the widget is destroyed (e.g. hot-reload)
        def _on_destroyed():
            self._timer.stop()
            self._label = None
            self._layout = None

        frame.destroyed.connect(_on_destroyed)

        self._refresh_ui()
        self._timer.start(1000)
        return frame

    def _refresh_ui(self):
        if not self._label:
            return
        try:
            show = self.get_setting("show_greeting")
            if show is None:
                show = True
            if isinstance(show, str):
                show = (show.lower() == "true")

            if show:
                text = self.get_setting("greeting_text") or "Hello!"
                self._label.setText(str(text))
                self._label.setVisible(True)
            else:
                self._label.setVisible(False)

            bg = self.get_setting("bg_color") or "#222222"
            parent = self._label.parentWidget()
            if parent:
                parent.setStyleSheet(f"background-color: {bg}; border-radius: 8px;")
        except RuntimeError:
            # Widget was deleted (e.g. during hot-reload) — stop polling
            self._timer.stop()
            self._label = None

    def on_data(self, key: str, value) -> None:
        pass

    # ── WORKER: Logic ─────────────────────────────────────────────────────────

    def start(self) -> None:
        super().start()
        # No background work needed for this demo
        while self.is_running:
            time.sleep(1)
