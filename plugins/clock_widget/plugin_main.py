"""
Clock Widget Plugin
===================
Worker side: sends HH:MM:SS every second.
Host side:   displays a large clock label.
"""
from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

# nova.core is importable because worker_host puts the project root on sys.path
from nova.core.plugin_base import PluginBase


class Plugin(PluginBase):

    def __init__(self, bridge):
        super().__init__(bridge)
        self._label: QLabel | None = None

    # ── HOST side ────────────────────────────────────────────
    def get_settings(self) -> list[PluginSetting]:
        from nova.core.plugin_base import PluginSetting
        return [
            PluginSetting(
                key="show_seconds",
                name="Show Seconds",
                type="bool",
                default=True,
                description="Toggle display of seconds."
            ),
            PluginSetting(
                key="color",
                name="Clock Color",
                type="colorpicker",
                default="#333333", # Dark gray default
                description="Text color of the clock."
            )
        ]

    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        frame = QFrame(parent)
        frame.setObjectName("ClockFrame")
        v = QVBoxLayout(frame)
        v.setAlignment(Qt.AlignCenter)

        # Apply settings immediately
        color = self.get_setting("color") or "#333333"

        self._label = QLabel("--:--:--")
        self._label.setObjectName("ClockLabel")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet(f"font-size: 72px; font-weight: 200; letter-spacing: 4px; color: {color};")
        v.addWidget(self._label)

        subtitle = QLabel("Live Clock via IPC")
        subtitle.setObjectName("ClockSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 12px; opacity: 0.6;")
        v.addWidget(subtitle)

        return frame

    def on_data(self, key: str, value) -> None:
        if key == "time" and self._label is not None:
            # Check settings on every update (in a real app, maybe cache this or use signals)
            show_seconds = self.get_setting("show_seconds")
            if show_seconds is None: show_seconds = True
            
            # Value is HH:MM:SS. If show_seconds is false, strip last 3 chars
            text = str(value)
            try:
                if not isinstance(show_seconds, bool):
                    show_seconds = str(show_seconds).lower() == "true"
                
                if not show_seconds and len(text) >= 8:
                    text = text[:5]
            except Exception:
                pass
                
            self._label.setText(text)
            
            # Also update color dynamically if user changes it while running
            color = self.get_setting("color") or "#333333"
            self._label.setStyleSheet(f"font-size: 72px; font-weight: 200; letter-spacing: 4px; color: {color};")

    # ── WORKER side ──────────────────────────────────────────
    def start(self) -> None:
        super().start()
        while self.is_running:
            self.send_data("time", datetime.now().strftime("%H:%M:%S"))
            time.sleep(1)
