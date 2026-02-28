from __future__ import annotations

import importlib.util
import logging
import shutil
import sys
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QObject, Signal, QProcess, QTimer
from PySide6.QtWidgets import QWidget

from nova.core.plugin_base import PluginBase, PluginManifest
from nova.core.plugin_bridge import MainBridge
from nova.core.plugin_spec import validate_manifest
from nova.core.plugin_state import PluginStateManager
from nova.core.paths import get_app_root, get_state_path
from nova import __version__ as NOVA_VERSION

_log = logging.getLogger(__name__)

_MAX_RESTARTS = 3


def _parse_version(ver: str) -> tuple:
    """Parse a semver string like '1.2.3' into a comparable tuple (1, 2, 3)."""
    parts = ver.strip().split(".")
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    while len(result) < 3:
        result.append(0)
    return tuple(result[:3])


@dataclass
class _PluginRecord:
    manifest: PluginManifest
    plugin: Optional[PluginBase] = None
    bridge: Optional[MainBridge] = None
    process: Optional[QProcess] = None
    socket_name: str = ""
    restart_count: int = 0
    active: bool = False


class PluginManager(QObject):
    """
    Manages plugin discovery, lifecycle, IPC, state, and file operations.

    Each plugin runs in a subprocess (QProcess) communicating via QLocalSocket.
    Plugin state (favorites, run counts, etc.) is persisted to plugins/nova_state.json.
    """

    plugin_loaded = Signal(str)             # plugin_id
    plugin_started = Signal(str)            # plugin_id
    plugin_stopped = Signal(str)            # plugin_id
    plugin_crashed = Signal(str, str)       # plugin_id, error_message
    plugin_favorite_changed = Signal(str, bool)  # plugin_id, is_favorite
    plugin_deleted = Signal(str)            # plugin_id
    plugin_imported = Signal(str)           # plugin_id

    def __init__(self, ctx: Any, plugins_dir: Path, parent: QObject | None = None):
        super().__init__(parent)
        self._ctx = ctx
        self._config = ctx.config
        self._plugins_dir = plugins_dir
        self._records: Dict[str, _PluginRecord] = {}
        # Track intentional stops so we don't mistake them for crashes.
        # On Windows, QProcess::terminate() causes CrashExit status.
        self._intentional_stops: Set[str] = set()
        self._project_root = get_app_root()
        # Persistent state store
        self._state = PluginStateManager(get_state_path())

    # ──────────────────────────────────────────────────────────
    #  Discovery
    # ──────────────────────────────────────────────────────────

    def discover(self) -> List[PluginManifest]:
        """Scan plugins_dir for plugin.json files and return manifests."""
        manifests: List[PluginManifest] = []
        if not self._plugins_dir.exists():
            _log.warning("PluginManager: plugins directory not found: %s", self._plugins_dir)
            return manifests
        for json_file in sorted(self._plugins_dir.rglob("plugin.json")):
            try:
                m = PluginManifest.from_file(json_file)
                manifests.append(m)
                _log.debug("PluginManager: discovered plugin '%s'", m.id)
            except Exception as exc:
                _log.warning("PluginManager: failed to load manifest %s: %s", json_file, exc)
        return manifests

    # ──────────────────────────────────────────────────────────
    #  Loading
    # ──────────────────────────────────────────────────────────

    def load(self, plugin_id: str) -> bool:
        """Import the plugin class and create a PluginRecord. Does not start subprocess."""
        if plugin_id in self._records:
            return True

        # Find manifest
        manifest: Optional[PluginManifest] = None
        for m in self.discover():
            if m.id == plugin_id:
                manifest = m
                break
        if manifest is None:
            _log.error("PluginManager: manifest not found for '%s'", plugin_id)
            return False

        # Check version compatibility
        if manifest.min_nova_version:
            required = _parse_version(manifest.min_nova_version)
            current = _parse_version(NOVA_VERSION)
            if current < required:
                _log.error(
                    "PluginManager: plugin '%s' requires Nova %s but current is %s",
                    plugin_id, manifest.min_nova_version, NOVA_VERSION,
                )
                return False

        # Dynamically import the plugin class
        plugin_dir = self._plugins_dir / plugin_id
        module_name, class_name = manifest.entry.rsplit(".", 1)
        module_file = plugin_dir / f"{module_name}.py"
        if not module_file.exists():
            _log.error("PluginManager: entry file not found: %s", module_file)
            return False

        try:
            spec = importlib.util.spec_from_file_location(
                f"nova_plugin_{plugin_id}.{module_name}", module_file
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            plugin_class = getattr(mod, class_name)
        except Exception as exc:
            _log.error("PluginManager: failed to import plugin '%s': %s", plugin_id, exc)
            return False

        record = _PluginRecord(manifest=manifest)
        record.socket_name = f"nova_{plugin_id}_{uuid.uuid4().hex[:8]}"
        self._records[plugin_id] = record

        bridge = MainBridge(record.socket_name, self)

        try:
            plugin_inst = plugin_class(bridge)
            plugin_inst.manifest = manifest
            plugin_inst.config = self._config
        except Exception as exc:
            _log.error("PluginManager: failed to instantiate plugin '%s': %s", plugin_id, exc)
            bridge.close()
            bridge.deleteLater()
            del self._records[plugin_id]
            return False

        bridge.data_received.connect(
            lambda key, value, pid=plugin_id: self._on_data_received(pid, key, value)
        )
        bridge.worker_ready.connect(
            lambda pid=plugin_id: _log.debug("PluginManager: worker ready for '%s'", pid)
        )
        bridge.worker_gone.connect(
            lambda pid=plugin_id: self._on_bridge_worker_gone(pid)
        )

        record.plugin = plugin_inst
        record.bridge = bridge
        self.plugin_loaded.emit(plugin_id)
        _log.info("PluginManager: loaded plugin '%s'", plugin_id)
        return True

    # ──────────────────────────────────────────────────────────
    #  Starting / Stopping
    # ──────────────────────────────────────────────────────────

    def start(self, plugin_id: str) -> bool:
        """Spawn the worker subprocess for the given plugin."""
        record = self._records.get(plugin_id)
        if record is None:
            _log.error("PluginManager: cannot start unloaded plugin '%s'", plugin_id)
            return False
        if record.active:
            return True

        # Reset crash counter on a fresh manual start
        record.restart_count = 0

        process = QProcess(self)
        process.setWorkingDirectory(str(self._project_root))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(
            lambda pid=plugin_id, p=process: self._log_process_output(pid, p)
        )
        process.finished.connect(
            lambda code, status, pid=plugin_id: self._on_process_finished(pid, code, status)
        )

        if getattr(sys, "frozen", False):
            # Frozen (PyInstaller): reuse the exe with --worker flag
            args = [
                "--worker",
                plugin_id,
                str(self._plugins_dir),
                record.socket_name,
            ]
        else:
            args = [
                "-m", "nova.core.worker_host",
                plugin_id,
                str(self._plugins_dir),
                record.socket_name,
            ]
        process.start(sys.executable, args)
        if not process.waitForStarted(3000):
            _log.error("PluginManager: failed to start process for '%s'", plugin_id)
            process.deleteLater()
            return False

        record.process = process
        record.active = True
        self._state.record_run(plugin_id)
        self.plugin_started.emit(plugin_id)
        _log.info("PluginManager: started plugin '%s' (PID %s)", plugin_id, process.processId())
        return True

    def stop(self, plugin_id: str):
        """Send stop command and terminate the worker subprocess (non-blocking)."""
        record = self._records.get(plugin_id)
        if record is None or not record.active:
            return

        # Mark as intentional BEFORE changing active flag so _on_process_finished sees it.
        self._intentional_stops.add(plugin_id)
        record.active = False

        if record.bridge:
            try:
                record.bridge.send_command("stop")
            except Exception:
                pass

        if record.process and record.process.state() != QProcess.NotRunning:
            record.process.terminate()
            # Schedule a kill if the process ignores terminate (non-blocking).
            # Guard against the C++ object being deleted before the timer fires
            # (e.g. when delete_plugin() is called shortly after stop()).
            proc = record.process
            def _safe_kill(p=proc):
                try:
                    if p.state() != QProcess.NotRunning:
                        p.kill()
                except RuntimeError:
                    pass  # C++ QProcess already deleted
            QTimer.singleShot(2000, _safe_kill)

        self.plugin_stopped.emit(plugin_id)

    def stop_all(self):
        """Stop all running plugins synchronously (called on app exit)."""
        for plugin_id in list(self._records.keys()):
            record = self._records.get(plugin_id)
            if record is None or not record.active:
                continue

            self._intentional_stops.add(plugin_id)
            record.active = False

            if record.bridge:
                try:
                    record.bridge.send_command("stop")
                except Exception:
                    pass

            if record.process and record.process.state() != QProcess.NotRunning:
                record.process.terminate()
                if not record.process.waitForFinished(2500):
                    record.process.kill()
                    record.process.waitForFinished(1000)

        _log.debug("PluginManager: all plugins stopped")

    # ──────────────────────────────────────────────────────────
    #  Widget creation
    # ──────────────────────────────────────────────────────────

    def create_widget(self, plugin_id: str, parent: QWidget | None = None) -> Optional[QWidget]:
        record = self._records.get(plugin_id)
        if record and record.plugin:
            try:
                return record.plugin.create_widget(parent)
            except Exception as exc:
                _log.error("PluginManager: create_widget failed for '%s': %s", plugin_id, exc)
        return None

    # ──────────────────────────────────────────────────────────
    #  State / Favorites
    # ──────────────────────────────────────────────────────────

    def is_favorite(self, plugin_id: str) -> bool:
        return self._state.get(plugin_id).favorite

    def set_favorite(self, plugin_id: str, value: bool) -> None:
        self._state.set_favorite(plugin_id, value)
        self.plugin_favorite_changed.emit(plugin_id, value)

    def is_enabled(self, plugin_id: str) -> bool:
        return self._state.get(plugin_id).enabled

    def set_enabled(self, plugin_id: str, value: bool) -> None:
        self._state.set_enabled(plugin_id, value)

    def get_state(self, plugin_id: str):
        return self._state.get(plugin_id)

    # ──────────────────────────────────────────────────────────
    #  Import / Export / Delete / Reload
    # ──────────────────────────────────────────────────────────

    def import_plugin(self, zip_path: Path) -> Tuple[bool, str]:
        """
        Import a plugin from a .zip archive.

        The zip must contain a top-level directory named after the plugin id:
            my_plugin/
              plugin.json
              plugin_main.py

        Returns (success, plugin_id_or_error_message).
        """
        try:
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()

                # Locate plugin.json inside the archive
                json_entries = [n for n in names if n.endswith("plugin.json")]
                if not json_entries:
                    return False, "No plugin.json found in archive"

                json_arc = json_entries[0]
                parts = Path(json_arc).parts
                if len(parts) < 2:
                    return False, "plugin.json must be inside a plugin sub-directory"

                archive_dir = parts[0]
                target_dir = self._plugins_dir / archive_dir

                if target_dir.exists():
                    return False, (
                        f"A plugin directory named '{archive_dir}' already exists. "
                        "Remove or rename it before importing."
                    )

                # Extract everything
                self._plugins_dir.mkdir(parents=True, exist_ok=True)
                zf.extractall(self._plugins_dir)

        except zipfile.BadZipFile:
            return False, "File is not a valid ZIP archive"
        except Exception as exc:
            return False, f"Extraction failed: {exc}"

        # Validate the manifest
        manifest_file = target_dir / "plugin.json"
        is_valid, errors = validate_manifest(manifest_file)
        if not is_valid:
            shutil.rmtree(target_dir, ignore_errors=True)
            return False, "Invalid plugin: " + "; ".join(errors)

        try:
            manifest = PluginManifest.from_file(manifest_file)
        except Exception as exc:
            shutil.rmtree(target_dir, ignore_errors=True)
            return False, f"Cannot parse manifest: {exc}"

        # If the plugin id differs from the extracted dir name, rename the dir
        if manifest.id != archive_dir:
            new_dir = self._plugins_dir / manifest.id
            if new_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
                return False, f"Plugin '{manifest.id}' already exists"
            target_dir.rename(new_dir)

        _log.info("PluginManager: imported plugin '%s' from %s", manifest.id, zip_path)
        self.plugin_imported.emit(manifest.id)
        return True, manifest.id

    def export_plugin(self, plugin_id: str, output_dir: Path) -> Tuple[bool, str]:
        """
        Export a plugin to a .zip archive.

        Returns (success, output_path_or_error_message).
        """
        plugin_dir = self._plugins_dir / plugin_id
        if not plugin_dir.exists():
            return False, f"Plugin directory not found: {plugin_dir}"

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{plugin_id}.zip"

        try:
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in sorted(plugin_dir.rglob("*")):
                    if file_path.is_file():
                        arcname = file_path.relative_to(self._plugins_dir)
                        zf.write(file_path, arcname)
            _log.info("PluginManager: exported '%s' to %s", plugin_id, output_path)
            return True, str(output_path)
        except Exception as exc:
            return False, f"Export failed: {exc}"

    def delete_plugin(self, plugin_id: str) -> Tuple[bool, str]:
        """
        Stop, unload, and permanently delete a plugin and its files.

        Returns (success, error_message).
        """
        # Stop if running
        if self.is_active(plugin_id):
            self.stop(plugin_id)
            # Give terminate a moment before proceeding
            record = self._records.get(plugin_id)
            if record and record.process:
                record.process.waitForFinished(1500)

        # Remove record and clean up Qt objects
        record = self._records.pop(plugin_id, None)
        if record:
            if record.bridge:
                try:
                    record.bridge.close()
                except Exception:
                    pass
                record.bridge.deleteLater()
            if record.process:
                # Disconnect finished signal so no more callbacks fire after deletion,
                # then let Qt's parent-child ownership clean up the C++ object.
                # Do NOT call deleteLater() here — the pending 2-second kill timer from
                # stop() still holds a Python reference to this process, and deleteLater()
                # would delete the C++ object before the timer fires, causing a crash.
                try:
                    record.process.finished.disconnect()
                except RuntimeError:
                    pass

        # Remove persisted state
        self._state.remove(plugin_id)

        # Delete the plugin directory
        plugin_dir = self._plugins_dir / plugin_id
        if plugin_dir.exists():
            try:
                shutil.rmtree(plugin_dir)
            except Exception as exc:
                return False, f"Failed to remove plugin files: {exc}"

        _log.info("PluginManager: deleted plugin '%s'", plugin_id)
        self.plugin_deleted.emit(plugin_id)
        return True, ""

    def reload_plugin(self, plugin_id: str) -> bool:
        """
        Stop (if running), unload, reload, and optionally restart a plugin.
        """
        was_active = self.is_active(plugin_id)

        if was_active:
            self.stop(plugin_id)
            record = self._records.get(plugin_id)
            if record and record.process:
                # Wait longer than the 2000 ms kill timer in stop() so we're
                # certain the old process is dead before spawning a new one.
                record.process.waitForFinished(3000)

        # Drop the old record — disconnect all signals first so stale
        # callbacks from the dying process/bridge don't touch the new record.
        record = self._records.pop(plugin_id, None)
        if record:
            if record.process:
                try:
                    record.process.finished.disconnect()
                except RuntimeError:
                    pass
            if record.bridge:
                try:
                    record.bridge.data_received.disconnect()
                    record.bridge.worker_ready.disconnect()
                    record.bridge.worker_gone.disconnect()
                except RuntimeError:
                    pass
                try:
                    record.bridge.close()
                except Exception:
                    pass
                record.bridge.deleteLater()

        # Generate a fresh socket name on reload
        if not self.load(plugin_id):
            return False

        if was_active:
            return self.start(plugin_id)
        return True

    # ──────────────────────────────────────────────────────────
    #  Queries
    # ──────────────────────────────────────────────────────────

    def is_active(self, plugin_id: str) -> bool:
        rec = self._records.get(plugin_id)
        return rec is not None and rec.active

    def is_loaded(self, plugin_id: str) -> bool:
        return plugin_id in self._records

    def manifests(self) -> List[PluginManifest]:
        return [r.manifest for r in self._records.values()]

    def loaded_count(self) -> int:
        return len(self._records)

    def active_count(self) -> int:
        return sum(1 for r in self._records.values() if r.active)

    # ──────────────────────────────────────────────────────────
    #  Internal callbacks
    # ──────────────────────────────────────────────────────────

    def _on_data_received(self, plugin_id: str, key: str, value: Any):
        record = self._records.get(plugin_id)
        if record and record.plugin:
            try:
                record.plugin.on_data(key, value)
            except Exception as exc:
                _log.warning("PluginManager: on_data error for '%s': %s", plugin_id, exc)

    def _on_bridge_worker_gone(self, plugin_id: str):
        """Bridge signals disconnect — only warn if it was unexpected."""
        record = self._records.get(plugin_id)
        if record and record.active and plugin_id not in self._intentional_stops:
            _log.warning("PluginManager: worker IPC dropped unexpectedly for '%s'", plugin_id)

    def _on_process_finished(self, plugin_id: str, exit_code: int, exit_status: QProcess.ExitStatus):
        # Guard against RuntimeError if self (PluginManager QObject) is being
        # torn down during Python exit while a pending finished signal still fires.
        try:
            self._handle_process_finished(plugin_id, exit_code, exit_status)
        except RuntimeError as exc:
            _log.debug("PluginManager: _on_process_finished skipped (teardown): %s", exc)

    def _handle_process_finished(self, plugin_id: str, exit_code: int, exit_status: QProcess.ExitStatus):
        record = self._records.get(plugin_id)
        if record is None:
            return

        # Consume the intentional-stop flag if present
        intentional = plugin_id in self._intentional_stops
        self._intentional_stops.discard(plugin_id)

        was_active = record.active
        record.active = False

        if intentional:
            # User explicitly stopped the plugin — never restart
            _log.debug("PluginManager: '%s' stopped intentionally (exit %d)", plugin_id, exit_code)
            return  # plugin_stopped already emitted by stop()

        # Unexpected exit: crash if exit_status is CrashExit or non-zero code
        if was_active and (exit_status == QProcess.CrashExit or exit_code not in (0,)):
            record.restart_count += 1
            self._state.record_crash(plugin_id)
            msg = (
                f"Plugin '{plugin_id}' crashed "
                f"(exit_code={exit_code}, attempt {record.restart_count}/{_MAX_RESTARTS})"
            )
            _log.error("PluginManager: %s", msg)
            self.plugin_crashed.emit(plugin_id, msg)

            if record.restart_count <= _MAX_RESTARTS:
                _log.info("PluginManager: scheduling restart for '%s' in 2s", plugin_id)
                QTimer.singleShot(2000, lambda: self.start(plugin_id))
            else:
                _log.error("PluginManager: '%s' exceeded max restarts — giving up", plugin_id)
        else:
            self.plugin_stopped.emit(plugin_id)

    def _log_process_output(self, plugin_id: str, process: QProcess):
        try:
            data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        except RuntimeError:
            return  # C++ QProcess already deleted (e.g. during stop_all teardown)
        for line in data.splitlines():
            if line.strip():
                _log.debug("[plugin:%s] %s", plugin_id, line)
