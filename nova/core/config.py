from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional

_log = logging.getLogger(__name__)

@dataclass
class SettingItem:
    name: str
    shortname: str
    value: Any
    values: Any
    description: str
    type: str
    accessibility: str
    group: str
    icon: str

class ConfigManager:
    """
    Manages application configuration, loading/saving from a JSON file.
    Replaces qtpop.configuration.parser.ConfigurationManager
    """
    def __init__(self, config_path: Path):
        self._path = config_path
        self._data: Dict[str, Any] = {"user": {}, "static": {}}
        self.load()

    def load(self):
        if not self._path.exists():
            _log.warning(f"Config file not found at {self._path}, creating default.")
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self.save()
            return

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                # Structure expectation: {"configuration": {"user": {...}, "static": {...}}}
                if "configuration" in raw_data:
                    self._data = raw_data["configuration"]
                else:
                    self._data = raw_data # Fallback/Legacy support if needed
        except Exception as e:
            _log.error(f"Failed to load config: {e}")

    def save(self):
        try:
            # Wrap in "configuration" key to match typical qtpop structure if we want compatibility
            output = {"configuration": self._data}
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2)
        except Exception as e:
            _log.error(f"Failed to save config: {e}")

    def get_value(self, key: str, default=None) -> Any:
        """Return the raw value for *key* (not the whole SettingItem dict)."""
        user_settings = self._data.get("user", {})
        if key in user_settings:
            val = user_settings[key]
            if isinstance(val, dict) and "value" in val:
                return val["value"]   # return raw value, not SettingItem
            return val

        static_settings = self._data.get("static", {})
        if key in static_settings:
            return static_settings[key]

        if default is not None:
            return default

        raise KeyError(f"Setting '{key}' not found")

    def get_setting(self, key: str) -> Optional[SettingItem]:
        """Return a SettingItem for *key* (user settings only), or None."""
        user = self._data.get("user", {})
        val = user.get(key)
        if isinstance(val, dict) and "value" in val:
            try:
                return SettingItem(**val)
            except Exception:
                return None
        return None

    def get_all_user_settings(self) -> Dict[str, SettingItem]:
        """Return all user settings that can be parsed as SettingItem objects."""
        out: Dict[str, SettingItem] = {}
        for k, v in self._data.get("user", {}).items():
            if isinstance(v, dict) and "value" in v:
                try:
                    out[k] = SettingItem(**v)
                except Exception:
                    pass
        return out

    def set_value(self, key: str, value: Any):
        # We only set user settings
        user_settings = self._data.setdefault("user", {})
        
        if key in user_settings:
            current = user_settings[key]
            if isinstance(current, dict):
                current["value"] = value
            elif isinstance(current, SettingItem):
                current.value = value
                # validation/serialization happens on save normally, but here we just store objects
                # Actually, JSON serialization needs dicts.
                user_settings[key] = asdict(current)
            else:
                user_settings[key] = value
        else:
            # If creating new simple value
            user_settings[key] = value
            
        self.save()

    def add_user_setting(self, key: str, item: SettingItem):
        self._data.setdefault("user", {})[key] = asdict(item)
        self.save()
