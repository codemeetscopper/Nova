"""
System Monitor Plugin
=====================
Worker side: sends cpu/mem/disk values every 1.5 seconds.
Host side:   displays labelled progress bars.

Falls back to random values if psutil is not installed.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget,
)

from nova.core.plugin_base import PluginBase, PluginSetting


def _get_stats() -> dict:
    """Return cpu/mem/disk as percentages (0-100)."""
    try:
        import psutil
        return {
            "cpu": psutil.cpu_percent(interval=None),
            "mem": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage("/").percent,
        }
    except ImportError:
        import random
        return {
            "cpu": random.uniform(5, 85),
            "mem": random.uniform(30, 75),
            "disk": random.uniform(20, 90),
        }


class _StatBar(QWidget):
    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        lbl_row = QWidget()
        from PySide6.QtWidgets import QHBoxLayout
        h = QHBoxLayout(lbl_row)
        h.setContentsMargins(0, 0, 0, 0)
        name = QLabel(label)
        name.setObjectName("StatBarName")
        self._pct = QLabel("0 %")
        self._pct.setObjectName("StatBarPct")
        h.addWidget(name)
        h.addStretch()
        h.addWidget(self._pct)
        v.addWidget(lbl_row)

        self._bar = QProgressBar()
        self._bar.setObjectName("StatProgressBar")
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        v.addWidget(self._bar)

    def set_value(self, pct: float):
        val = int(pct)
        self._bar.setValue(val)
        self._pct.setText(f"{val} %")


class Plugin(PluginBase):

    def __init__(self, bridge):
        super().__init__(bridge)
        self._cpu_bar: _StatBar | None = None
        self._mem_bar: _StatBar | None = None
        self._disk_bar: _StatBar | None = None

    # ── HOST side ────────────────────────────────────────────
    def get_settings(self) -> list[PluginSetting]:
        from nova.core.plugin_base import PluginSetting
        return [
            PluginSetting(
                key="compact_mode",
                name="Compact Mode",
                type="bool",
                default=False,
                description="Use less spacing between bars."
            ),
            PluginSetting(
                key="show_disk",
                name="Show Disk Usage",
                type="bool",
                default=True,
                description="Toggle visibility of the Disk usage bar."
            )
        ]

    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        frame = QFrame(parent)
        frame.setObjectName("SysMonFrame")
        
        compact = self.get_setting("compact_mode")
        if compact is None: compact = False
        if not isinstance(compact, bool): compact = str(compact).lower() == "true"
        
        spacing = 8 if compact else 24
        margin = 16 if compact else 32
        
        v = QVBoxLayout(frame)
        v.setContentsMargins(margin, margin, margin, margin)
        v.setSpacing(spacing)

        title = QLabel("System Monitor")
        title.setObjectName("SysMonTitle")
        v.addWidget(title)

        self._cpu_bar = _StatBar("CPU")
        self._mem_bar = _StatBar("Memory")
        self._disk_bar = _StatBar("Disk")
        
        show_disk = self.get_setting("show_disk")
        if show_disk is None: show_disk = True
        if not isinstance(show_disk, bool): show_disk = str(show_disk).lower() == "true"
        self._disk_bar.setVisible(show_disk)

        v.addWidget(self._cpu_bar)
        v.addWidget(self._mem_bar)
        v.addWidget(self._disk_bar)
        v.addStretch()
        return frame

    def on_data(self, key: str, value) -> None:
        try:
            val = float(value)
        except (TypeError, ValueError):
            return
            
        # Re-check settings for dynamic updates
        compact = self.get_setting("compact_mode")
        if compact is None: compact = False
        if not isinstance(compact, bool): compact = str(compact).lower() == "true"
        
        # Adjust spacing dynamically if layout exists
        if self._cpu_bar and self._cpu_bar.parentWidget().layout():
            layout = self._cpu_bar.parentWidget().layout()
            target_spacing = 8 if compact else 24
            if layout.spacing() != target_spacing:
                layout.setSpacing(target_spacing)
                
        if key == "cpu" and self._cpu_bar:
            self._cpu_bar.set_value(val)
        elif key == "mem" and self._mem_bar:
            self._mem_bar.set_value(val)
        elif key == "disk" and self._disk_bar:
            # Check visibility
            show_disk = self.get_setting("show_disk")
            if show_disk is None: show_disk = True
            if not isinstance(show_disk, bool): show_disk = str(show_disk).lower() == "true"
            self._disk_bar.setVisible(show_disk)
            
            self._disk_bar.set_value(val)

    # ── WORKER side ──────────────────────────────────────────
    def start(self) -> None:
        super().start()
        while self.is_running:
            stats = _get_stats()
            self.send_data("cpu", stats["cpu"])
            self.send_data("mem", stats["mem"])
            self.send_data("disk", stats["disk"])
            time.sleep(1.5)
