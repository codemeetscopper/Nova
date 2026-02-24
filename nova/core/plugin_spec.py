"""
Nova Plugin Specification — validation, constants, and template generator.

Every Nova plugin MUST contain:
  plugin_id/
  ├── plugin.json      (manifest — all required fields present)
  └── plugin_main.py   (contains a class matching the 'entry' field)

plugin.json required fields:
  id, name, version, description, author, entry

plugin.json optional fields:
  icon, min_nova_version, permissions, keywords, homepage, spec_version
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Tuple

# ── Spec constants ───────────────────────────────────────────────────────────
NOVA_PLUGIN_SPEC_VERSION = "1.0"

REQUIRED_FIELDS: List[str] = ["id", "name", "version", "description", "author", "entry"]
OPTIONAL_FIELDS: List[str] = [
    "icon", "min_nova_version", "permissions", "keywords", "homepage", "spec_version",
]

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+")
_ENTRY_RE = re.compile(r"^[a-zA-Z_]\w*\.[a-zA-Z_]\w*$")

# ── Validation ───────────────────────────────────────────────────────────────

def validate_manifest(path: Path) -> Tuple[bool, List[str]]:
    """
    Validate a plugin.json file.

    Returns:
        (is_valid: bool, errors: list[str])
    """
    errors: List[str] = []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, [f"Invalid JSON: {exc}"]
    except OSError as exc:
        return False, [f"Cannot read file: {exc}"]

    if not isinstance(data, dict):
        return False, ["plugin.json root must be a JSON object"]

    # Required fields
    for f in REQUIRED_FIELDS:
        if f not in data:
            errors.append(f"Missing required field: '{f}'")
        elif not str(data.get(f, "")).strip():
            errors.append(f"Field '{f}' must not be empty")

    # id format
    pid = str(data.get("id", ""))
    if pid and not _ID_RE.match(pid):
        errors.append(
            "Field 'id' must be lowercase letters/digits/underscores, start with a letter, max 64 chars"
        )

    # version format
    ver = str(data.get("version", ""))
    if ver and not _SEMVER_RE.match(ver):
        errors.append("Field 'version' should follow semver (e.g. '1.0.0')")

    # entry format
    entry = str(data.get("entry", ""))
    if entry and not _ENTRY_RE.match(entry):
        errors.append("Field 'entry' must be 'module_name.ClassName' (e.g. 'plugin_main.Plugin')")

    # entry file exists (if we can determine plugin dir)
    if not errors and entry:
        module_name = entry.split(".")[0]
        plugin_dir = path.parent
        entry_file = plugin_dir / f"{module_name}.py"
        if not entry_file.exists():
            errors.append(f"Entry file '{module_name}.py' not found in plugin directory")

    return len(errors) == 0, errors


# ── Template ─────────────────────────────────────────────────────────────────

_MANIFEST_TEMPLATE = {
    "spec_version": NOVA_PLUGIN_SPEC_VERSION,
    "id": "{plugin_id}",
    "name": "{name}",
    "version": "0.1.0",
    "description": "{description}",
    "author": "{author}",
    "icon": "extension",
    "entry": "plugin_main.Plugin",
    "min_nova_version": "1.0.0",
    "permissions": ["ipc"],
    "keywords": [],
    "homepage": "",
}

_PLUGIN_PY_TEMPLATE = '''\
"""
{name} Plugin
{bar}
{description}

Author  : {author}
Version : 0.1.0

Nova Plugin API
===============
  create_widget(parent)  — HOST process: return a QWidget to show in the UI
  on_data(key, value)    — HOST process: called when worker sends data via IPC
  start()                — WORKER subprocess: run your logic here (blocking loop OK)
  stop()                 — WORKER subprocess: set self._running=False to exit loop
  send_data(key, value)  — WORKER subprocess: push data to the host UI
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from nova.core.plugin_base import PluginBase


class Plugin(PluginBase):
    """Main plugin class — instantiated once per process context."""

    def __init__(self, bridge):
        super().__init__(bridge)
        self._label: QLabel | None = None

    # ── HOST: UI ──────────────────────────────────────────────────────────────

    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        """Return the widget shown when the user opens this plugin's page."""
        frame = QFrame(parent)
        v = QVBoxLayout(frame)
        v.setAlignment(Qt.AlignCenter)

        self._label = QLabel("Waiting for data…")
        self._label.setAlignment(Qt.AlignCenter)
        v.addWidget(self._label)
        return frame

    def on_data(self, key: str, value) -> None:
        """Called in the HOST whenever the worker sends a data packet."""
        if key == "message" and self._label is not None:
            self._label.setText(str(value))

    # ── WORKER: Logic ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Main worker loop — runs in a separate subprocess."""
        super().start()
        counter = 0
        while self.is_running:
            self.send_data("message", f"Tick #{{counter}}")
            counter += 1
            time.sleep(2)
'''

_README_TEMPLATE = """\
# {name}

{description}

## Author

{author}

## Installation

Drop the `{plugin_id}/` directory into Nova's `plugins/` folder, then restart
Nova or use **Plugins → Import Plugin** to load a `.zip` archive.

## Plugin structure

```
{plugin_id}/
├── plugin.json     Manifest (required)
├── plugin_main.py  Plugin entry class (required)
├── README.md       This file (optional)
└── resources/      Static assets (optional)
```

## Permissions

| Permission | Description |
|------------|-------------|
| `ipc`      | Communicate with the Nova host via local socket |
"""


def create_plugin_template(
    plugin_id: str,
    name: str,
    author: str,
    description: str,
    output_dir: Path,
) -> Path:
    """
    Generate a complete starter plugin directory.

    Args:
        plugin_id:   Lowercase slug (e.g. "my_plugin")
        name:        Human-readable name
        author:      Author name
        description: One-line description
        output_dir:  Parent directory (typically plugins/)

    Returns:
        Path to the created plugin directory.
    """
    plugin_dir = output_dir / plugin_id
    plugin_dir.mkdir(parents=True, exist_ok=True)

    # plugin.json
    manifest = {
        k: v.format(
            plugin_id=plugin_id,
            name=name,
            author=author,
            description=description,
        ) if isinstance(v, str) else v
        for k, v in _MANIFEST_TEMPLATE.items()
    }
    (plugin_dir / "plugin.json").write_text(
        json.dumps(manifest, indent=4), encoding="utf-8"
    )

    # plugin_main.py
    bar = "=" * (len(name) + 7)
    py_content = _PLUGIN_PY_TEMPLATE.format(
        name=name, bar=bar, description=description, author=author
    )
    (plugin_dir / "plugin_main.py").write_text(py_content, encoding="utf-8")

    # README.md
    readme = _README_TEMPLATE.format(
        name=name, plugin_id=plugin_id, description=description, author=author
    )
    (plugin_dir / "README.md").write_text(readme, encoding="utf-8")

    # resources/ placeholder
    resources = plugin_dir / "resources"
    resources.mkdir(exist_ok=True)
    (resources / ".gitkeep").write_text("", encoding="utf-8")

    return plugin_dir
