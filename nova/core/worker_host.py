"""
Nova plugin worker host — subprocess bootstrap.

Entry point:
    python -m nova.core.worker_host <plugin_id> <plugins_dir> <socket_name>

Lifecycle:
  1. QCoreApplication starts
  2. Plugin class loaded dynamically
  3. WorkerBridge connects to host QLocalServer
  4. plugin.start() runs in a QThread
  5. When thread finishes (plugin.stop() called), QCoreApplication.quit() fires
  6. Process exits cleanly
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.DEBUG,
    format="[worker] %(levelname)s %(name)s: %(message)s",
)
_log = logging.getLogger(__name__)


def main() -> None:
    if len(sys.argv) < 4:
        _log.error("Usage: worker_host <plugin_id> <plugins_dir> <socket_name>")
        sys.exit(1)

    plugin_id = sys.argv[1]
    plugins_dir = Path(sys.argv[2])
    socket_name = sys.argv[3]

    from PySide6.QtCore import QCoreApplication, QThread, QTimer

    app = QCoreApplication(sys.argv[:1])

    # Ensure project root is on sys.path so nova.core is importable
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from nova.core.plugin_base import PluginManifest
    from nova.core.plugin_bridge import WorkerBridge

    # ── Load manifest ─────────────────────────────────────────
    plugin_dir = plugins_dir / plugin_id
    manifest_file = plugin_dir / "plugin.json"
    if not manifest_file.exists():
        _log.error("Manifest not found: %s", manifest_file)
        sys.exit(2)

    try:
        manifest = PluginManifest.from_file(manifest_file)
    except Exception as exc:
        _log.error("Failed to parse manifest: %s", exc)
        sys.exit(3)

    # ── Import plugin class ────────────────────────────────────
    module_name, class_name = manifest.entry.rsplit(".", 1)
    module_file = plugin_dir / f"{module_name}.py"
    if not module_file.exists():
        _log.error("Entry file not found: %s", module_file)
        sys.exit(4)

    try:
        spec = importlib.util.spec_from_file_location(
            f"nova_worker_{plugin_id}.{module_name}", module_file
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        plugin_class = getattr(mod, class_name)
    except Exception as exc:
        _log.error("Failed to import plugin class '%s': %s", class_name, exc)
        sys.exit(5)

    # ── Create bridge + plugin ─────────────────────────────────
    bridge = WorkerBridge(socket_name)
    plugin = plugin_class(bridge)
    plugin.manifest = manifest
    bridge.set_plugin(plugin)

    # ── Run plugin.start() in a QThread ───────────────────────
    class _PluginThread(QThread):
        def run(self) -> None:
            try:
                plugin.start()
            except Exception as exc:
                _log.error("plugin.start() raised: %s", exc)
            finally:
                # Plugin finished — exit event loop whether stopped normally
                # or due to an exception.
                _log.debug("Worker: plugin thread finished, quitting event loop")
                QCoreApplication.quit()

    thread = _PluginThread()

    # Give the bridge 250 ms to connect before starting the plugin
    QTimer.singleShot(250, thread.start)

    # Safety net: if the thread is still alive 5 s after stop() was called,
    # force-quit. This prevents zombie workers.
    def _force_quit_if_stopped():
        if not plugin.is_running:
            _log.warning("Worker: force-quitting (plugin didn't finish in time)")
            QCoreApplication.quit()

    # ── Qt event loop ──────────────────────────────────────────
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
