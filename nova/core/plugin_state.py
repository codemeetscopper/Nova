"""
Plugin State Manager — persists per-plugin user preferences and runtime counters.

State file: plugins/nova_state.json
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

_log = logging.getLogger(__name__)

_NOW = lambda: datetime.now().isoformat(timespec="seconds")


@dataclass
class PluginState:
    enabled: bool = True
    favorite: bool = False          # favorite = show in sidebar
    installed_at: str = field(default_factory=_NOW)
    run_count: int = 0
    last_run: str = ""
    crash_count: int = 0


class PluginStateManager:
    """
    Thread-safe, file-backed store for per-plugin state.

    Usage:
        sm = PluginStateManager(Path("plugins/nova_state.json"))
        sm.set_favorite("clock_widget", True)
        state = sm.get("clock_widget")   # PluginState
    """

    def __init__(self, state_file: Path):
        self._file = state_file
        self._states: Dict[str, PluginState] = {}
        self._load()

    # ──────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────

    def get(self, plugin_id: str) -> PluginState:
        if plugin_id not in self._states:
            self._states[plugin_id] = PluginState()
            self._save()
        return self._states[plugin_id]

    def set_favorite(self, plugin_id: str, value: bool) -> None:
        self.get(plugin_id).favorite = value
        self._save()

    def set_enabled(self, plugin_id: str, value: bool) -> None:
        self.get(plugin_id).enabled = value
        self._save()

    def record_run(self, plugin_id: str) -> None:
        s = self.get(plugin_id)
        s.run_count += 1
        s.last_run = _NOW()
        self._save()

    def record_crash(self, plugin_id: str) -> None:
        s = self.get(plugin_id)
        s.crash_count += 1
        self._save()

    def remove(self, plugin_id: str) -> None:
        """Remove state entry (e.g. when plugin is deleted)."""
        self._states.pop(plugin_id, None)
        self._save()

    def all_ids(self):
        return list(self._states.keys())

    # ──────────────────────────────────────────────────────
    #  Persistence
    # ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            raw = json.loads(self._file.read_text(encoding="utf-8"))
            valid_fields = PluginState.__dataclass_fields__
            for pid, sd in raw.items():
                filtered = {k: v for k, v in sd.items() if k in valid_fields}
                self._states[pid] = PluginState(**filtered)
        except Exception as exc:
            _log.warning("PluginStateManager: load failed: %s", exc)

    def _save(self) -> None:
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            data = {pid: asdict(s) for pid, s in self._states.items()}
            self._file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            _log.warning("PluginStateManager: save failed: %s", exc)
