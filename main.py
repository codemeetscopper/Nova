import logging
import sys
from pathlib import Path

# ── Worker mode (PyInstaller frozen) ──────────────────────────────
# When launched as: Nova.exe --worker <plugin_id> <plugins_dir> <socket_name>
# we skip the GUI and run the plugin worker host directly.
if "--worker" in sys.argv:
    idx = sys.argv.index("--worker")
    sys.argv = [sys.argv[0]] + sys.argv[idx + 1:]
    from nova.core.worker_host import main as _worker_main
    _worker_main()
    sys.exit(0)

import nova.app
from nova import __version__
from nova.core.context import NovaContext
from nova.core.config import ConfigManager
from nova.core.paths import get_config_path, get_app_root
from nova.core.style import StyleManager
from nova.core.icons import IconManager

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

if __name__ == "__main__":
    root_dir = get_app_root()

    # Initialize Core Managers
    print("Initializing Nova Core Managers...")

    # Migrate old config location to Documents/nova/ if needed
    config_path = get_config_path()
    old_config = root_dir / "config" / "config.json"
    if old_config.exists() and not config_path.exists():
        import shutil
        config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_config, config_path)
        logging.info("Migrated config from %s to %s", old_config, config_path)

    # Migrate old state file
    from nova.core.paths import get_state_path
    state_path = get_state_path()
    old_state = root_dir / "plugins" / "nova_state.json"
    if old_state.exists() and not state_path.exists():
        import shutil
        state_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_state, state_path)
        logging.info("Migrated plugin state from %s to %s", old_state, state_path)

    config = ConfigManager(config_path)
    # Ensure the static section always reflects the current app version
    config._data.setdefault("static", {})["version"] = __version__

    style = StyleManager()
    accent = config.get_value("appearance.accent", "#0088CC")
    theme  = config.get_value("appearance.theme",  "dark")
    style.initialise(accent_hex=accent, theme=theme)

    icons = IconManager()  # inline-only; no path argument needed

    # Create Context
    ctx = NovaContext(config, style, icons)

    logging.info("Nova initialized successfully.")

    try:
        nova.app.run(ctx)
    except Exception as e:
        logging.critical("Unhandled exception: %s", e, exc_info=True)
        sys.exit(1)
