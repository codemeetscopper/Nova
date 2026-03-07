from __future__ import annotations

import importlib.util
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QWidget


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    description: str
    author: str
    icon: str = "extension"
    entry: str = "plugin_main.Plugin"
    thread_isolated: bool = True
    min_nova_version: str = ""
    category: str = "General"

    @classmethod
    def from_file(cls, path: Path) -> "PluginManifest":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            id=data["id"],
            name=data["name"],
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            icon=data.get("icon", "extension"),
            entry=data.get("entry", "plugin_main.Plugin"),
            thread_isolated=data.get("thread_isolated", True),
            min_nova_version=data.get("min_nova_version", ""),
            category=data.get("category", "General"),
        )


@dataclass
class PluginSetting:
    key: str
    name: str
    type: str  # "text", "bool", "colorpicker", "dropdown", "filebrowse", "folderbrowse"
    default: Any
    description: str = ""
    values: list[Any] = field(default_factory=list)  # for dropdown


class PluginBase(ABC):
    """
    Base class for all Nova plugins.

    In the HOST process: create_widget() and on_data() are called.
    In the WORKER subprocess: start() and stop() are called.
    """

    def __init__(self, bridge: Any):
        self._bridge = bridge
        self._running = False
        self.manifest: PluginManifest | None = None

    @abstractmethod
    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        """Called in the MAIN (host) process to build the plugin's UI widget."""

    def on_data(self, key: str, value: Any) -> None:
        """Called in the MAIN process when the worker sends data via IPC."""

    def get_settings(self) -> list[PluginSetting]:
        """Return a list of PluginSetting for this plugin's configurable options."""
        return []

    def get_setting(self, key: str) -> Any:
        """Get the current value of a setting (HOST process only)."""
        if hasattr(self, "config") and self.config:
            full_key = f"plugins.{self.manifest.id}.{key}" if self.manifest else key
            try:
                return self.config.get_value(full_key)
            except KeyError:
                return None
            except Exception:
                return None
        return None

    def on_command(self, cmd: str, data: Any) -> None:
        """Called in the WORKER subprocess when the host sends a custom command."""

    def send_command(self, cmd: str, data: Any = None) -> None:
        """Host side: send a command to the worker subprocess via IPC."""
        if self._bridge is not None and hasattr(self._bridge, "send_command"):
            self._bridge.send_command(cmd, data)

    def on_theme_changed(self, style_manager) -> None:
        """
        Called in the MAIN process when the application theme/accent changes.
        Override to re-apply dynamic colours to plugin widgets.
        The style_manager argument is the nova.core.style.StyleManager class.
        """

    def start(self) -> None:
        """Called in the WORKER subprocess to begin plugin logic."""
        self._running = True

    def stop(self) -> None:
        """Called in the WORKER subprocess to halt plugin logic."""
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def send_data(self, key: str, value: Any) -> None:
        """Convenience: worker side sends data to the host."""
        if self._bridge is not None:
            self._bridge.send_data(key, value)
