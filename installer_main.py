"""
Nova Installer — Entry point.

Usage:
    python installer_main.py                      # Uses installer.json in same directory
    python installer_main.py path/to/installer.json
    NovaInstaller.exe                              # Frozen mode — uses bundled installer.json
"""
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

if __name__ == "__main__":
    # Resolve root depending on frozen vs dev mode
    if getattr(sys, "frozen", False):
        root = Path(sys._MEIPASS)
    else:
        root = Path(__file__).parent
        sys.path.insert(0, str(root))

    from installer.app import run

    # Determine config path
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    else:
        config_path = root / "installer.json"

    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path

    logging.info("Nova Installer starting with config: %s", config_path)

    try:
        run(config_path)
    except Exception as e:
        logging.critical("Unhandled exception: %s", e, exc_info=True)
        sys.exit(1)
