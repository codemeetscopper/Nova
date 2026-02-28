"""
Centralized path resolution for Nova data files.

All persistent and temporary files (config, plugin state, temp icons)
are stored under the user's Documents directory in a 'nova' folder.
"""
from __future__ import annotations

import sys
from pathlib import Path


def get_app_root() -> Path:
    """Return the application root directory.

    In frozen (PyInstaller) mode, returns the directory containing the exe.
    In development mode, returns the project root (parent of nova/ package).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent


def get_data_dir() -> Path:
    """Return ``~/Documents/nova/``, creating it if necessary."""
    data_dir = Path.home() / "Documents" / "nova"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_config_path() -> Path:
    """Return the path to the main config file."""
    return get_data_dir() / "config.json"


def get_state_path() -> Path:
    """Return the path to the plugin state file."""
    return get_data_dir() / "nova_state.json"


def get_temp_dir() -> Path:
    """Return the path to the temporary files directory (e.g. QSS icons)."""
    tmp = get_data_dir() / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp
