"""
Installer configuration — reads an installer.json manifest that describes
what application to install and how.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)


@dataclass
class AppManifest:
    """Describes the application to be installed."""
    name: str = "My Application"
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    url: str = ""
    icon_path: str = ""
    license_file: str = ""
    accent_color: str = "#0088CC"

    # Installation content
    source_dir: str = "."
    include_patterns: List[str] = field(default_factory=lambda: ["**/*"])
    exclude_patterns: List[str] = field(default_factory=lambda: [
        "__pycache__", "*.pyc", ".git", ".venv", "node_modules",
    ])

    # Default install paths
    default_install_dir: str = ""  # Auto-resolved if empty
    registry_key: str = ""         # e.g. "MyApp" for HKLM/HKCU uninstall

    # Optional components
    components: List[Dict[str, Any]] = field(default_factory=list)

    # Python-specific
    python_required: bool = False
    create_venv: bool = False
    requirements_file: str = ""
    entry_script: str = ""         # e.g. "main.py"

    # PyInstaller build settings
    use_pyinstaller: bool = False
    pyinstaller_onefile: bool = True
    pyinstaller_console: bool = False
    pyinstaller_icon: str = ""     # .ico file for the built exe
    pyinstaller_extra_args: List[str] = field(default_factory=list)
    pyinstaller_hidden_imports: List[str] = field(default_factory=list)
    pyinstaller_data_files: List[str] = field(default_factory=list)  # "src;dest" pairs
    pyinstaller_resource_dirs: List[str] = field(default_factory=list)  # dirs to copy alongside build

    # Post-install
    run_after_install: str = ""    # Script to run after install


def discover_plugins(source_dir: Path) -> List[Dict[str, Any]]:
    """Scan the plugins directory for plugin.json manifests.

    Returns a list of dicts with keys: id, name, description, icon, default.
    """
    plugins_dir = source_dir / "plugins"
    if not plugins_dir.exists():
        return []

    result: List[Dict[str, Any]] = []
    for pj in sorted(plugins_dir.glob("*/plugin.json")):
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
            result.append({
                "id": data.get("id", pj.parent.name),
                "name": data.get("name", pj.parent.name),
                "description": data.get("description", ""),
                "icon": "extension",
                "default": True,
            })
        except Exception:
            _log.warning("Failed to read plugin manifest: %s", pj)
    return result


@dataclass
class InstallerConfig:
    """Full installer configuration loaded from installer.json."""
    manifest: AppManifest
    raw: Dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "InstallerConfig":
        if not path.exists():
            _log.warning("installer.json not found at %s, using defaults", path)
            return cls(manifest=AppManifest(), raw={})

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        app_data = data.get("app", {})
        components = data.get("components", [])
        python_cfg = data.get("python", {})
        install_cfg = data.get("install", {})
        pyinst_cfg = data.get("pyinstaller", {})

        manifest = AppManifest(
            name=app_data.get("name", "My Application"),
            version=app_data.get("version", "1.0.0"),
            author=app_data.get("author", ""),
            description=app_data.get("description", ""),
            url=app_data.get("url", ""),
            icon_path=app_data.get("icon", ""),
            license_file=app_data.get("license_file", ""),
            accent_color=app_data.get("accent_color", "#0088CC"),
            source_dir=install_cfg.get("source_dir", "."),
            include_patterns=install_cfg.get("include", ["**/*"]),
            exclude_patterns=install_cfg.get("exclude", [
                "__pycache__", "*.pyc", ".git", ".venv", "node_modules",
            ]),
            default_install_dir=install_cfg.get("default_dir", ""),
            registry_key=install_cfg.get("registry_key", ""),
            components=components,
            python_required=python_cfg.get("required", False),
            create_venv=python_cfg.get("create_venv", False),
            requirements_file=python_cfg.get("requirements", ""),
            entry_script=python_cfg.get("entry_script", ""),
            use_pyinstaller=pyinst_cfg.get("enabled", False),
            pyinstaller_onefile=pyinst_cfg.get("onefile", True),
            pyinstaller_console=pyinst_cfg.get("console", False),
            pyinstaller_icon=pyinst_cfg.get("icon", ""),
            pyinstaller_extra_args=pyinst_cfg.get("extra_args", []),
            pyinstaller_hidden_imports=pyinst_cfg.get("hidden_imports", []),
            pyinstaller_data_files=pyinst_cfg.get("data_files", []),
            pyinstaller_resource_dirs=pyinst_cfg.get("resource_dirs", []),
            run_after_install=install_cfg.get("run_after_install", ""),
        )

        return cls(manifest=manifest, raw=data)
