from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  MainBridge  —  lives in the HOST process (wraps QLocalServer)
# ─────────────────────────────────────────────────────────────

class MainBridge(QObject):
    """
    Host-side IPC bridge.

    Starts a QLocalServer and waits for the worker subprocess to connect.
    Emits signals when data arrives or the worker disconnects.
    """

    data_received = Signal(str, object)   # key, value
    worker_ready = Signal()
    worker_gone = Signal()

    def __init__(self, socket_name: str, parent: QObject | None = None):
        super().__init__(parent)
        self._socket_name = socket_name
        self._server = QLocalServer(self)
        self._conn: QLocalSocket | None = None
        self._buf = b""

        self._server.newConnection.connect(self._on_new_connection)
        QLocalServer.removeServer(socket_name)
        if not self._server.listen(socket_name):
            _log.error("MainBridge: failed to listen on '%s': %s",
                       socket_name, self._server.errorString())

    # ------------------------------------------------------------------
    def _on_new_connection(self):
        self._conn = self._server.nextPendingConnection()
        if self._conn is None:
            return
        self._conn.readyRead.connect(self._on_ready_read)
        self._conn.disconnected.connect(self._on_disconnected)
        _log.debug("MainBridge: worker connected on '%s'", self._socket_name)
        self.worker_ready.emit()

    def _on_ready_read(self):
        if self._conn is None:
            return
        self._buf += bytes(self._conn.readAll())
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                _log.warning("MainBridge: bad JSON: %r", line)
                continue
            self._dispatch(msg)

    def _dispatch(self, msg: dict):
        t = msg.get("type")
        if t == "data":
            self.data_received.emit(msg.get("key", ""), msg.get("value"))
        elif t == "event":
            if msg.get("name") == "ready":
                self.worker_ready.emit()
        else:
            _log.debug("MainBridge: unknown msg type '%s'", t)

    def _on_disconnected(self):
        _log.debug("MainBridge: worker disconnected")
        self.worker_gone.emit()
        if self._conn:
            self._conn.deleteLater()
            self._conn = None

    # ------------------------------------------------------------------
    def send_command(self, cmd: str, data: dict | None = None):
        """Send a JSON command to the worker subprocess."""
        if self._conn is None or self._conn.state() != QLocalSocket.ConnectedState:
            _log.debug("MainBridge: no connected worker to send command '%s'", cmd)
            return
        payload = json.dumps({"type": "command", "cmd": cmd, "data": data or {}}) + "\n"
        self._conn.write(payload.encode("utf-8"))
        self._conn.flush()

    def close(self):
        if self._conn:
            try:
                self._conn.disconnectFromServer()
            except Exception:
                pass
        self._server.close()
        QLocalServer.removeServer(self._socket_name)


# ─────────────────────────────────────────────────────────────
#  WorkerBridge  —  lives in the WORKER subprocess
# ─────────────────────────────────────────────────────────────

class WorkerBridge(QObject):
    """
    Worker-side IPC bridge.

    Connects to the host's QLocalServer. Provides send_data() for the plugin.
    On receiving a 'stop' command: calls plugin.stop() then schedules a clean
    QCoreApplication.quit() so the subprocess exits gracefully.
    """

    command_received = Signal(str, object)  # cmd, data

    def __init__(self, socket_name: str, parent: QObject | None = None):
        super().__init__(parent)
        self._socket_name = socket_name
        self._plugin = None
        self._buf = b""
        self._shutting_down = False

        self._socket = QLocalSocket(self)
        self._socket.readyRead.connect(self._on_ready_read)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.errorOccurred.connect(self._on_error)

        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(300)
        self._retry_timer.timeout.connect(self._try_connect)
        self._retry_timer.start()

    def set_plugin(self, plugin) -> None:
        self._plugin = plugin

    # ------------------------------------------------------------------
    def send_data(self, key: str, value: Any) -> None:
        payload = json.dumps({"type": "data", "key": key, "value": value}) + "\n"
        self._write(payload.encode("utf-8"))

    def send_event(self, name: str, data: dict | None = None) -> None:
        payload = json.dumps({"type": "event", "name": name, "data": data or {}}) + "\n"
        self._write(payload.encode("utf-8"))

    def _write(self, raw: bytes) -> None:
        if self._socket.state() != QLocalSocket.ConnectedState:
            _log.debug("WorkerBridge: not yet connected, dropping message")
            return
        self._socket.write(raw)
        self._socket.flush()

    # ------------------------------------------------------------------
    def _try_connect(self) -> None:
        if self._shutting_down:
            self._retry_timer.stop()
            return
        state = self._socket.state()
        if state == QLocalSocket.ConnectedState:
            self._retry_timer.stop()
            return
        if state != QLocalSocket.UnconnectedState:
            self._socket.abort()
        self._socket.connectToServer(self._socket_name)
        if self._socket.state() == QLocalSocket.ConnectedState:
            self._retry_timer.stop()
            _log.debug("WorkerBridge: connected to '%s'", self._socket_name)
            self.send_event("ready", {})

    def _on_error(self, err) -> None:
        from PySide6.QtNetwork import QLocalSocket as _S
        if err == _S.LocalSocketError.ServerNotFoundError:
            _log.debug("WorkerBridge: server not yet available, retrying…")
        else:
            _log.warning("WorkerBridge socket error: %s", err)

    def _on_ready_read(self) -> None:
        self._buf += bytes(self._socket.readAll())
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "command":
                cmd = msg.get("cmd", "")
                self.command_received.emit(cmd, msg.get("data", {}))
                if cmd == "stop":
                    self._handle_stop()

    def _handle_stop(self) -> None:
        """Graceful stop: tell plugin to stop, then quit the event loop."""
        if self._shutting_down:
            return
        self._shutting_down = True
        self._retry_timer.stop()

        if self._plugin is not None:
            try:
                self._plugin.stop()
            except Exception as exc:
                _log.warning("WorkerBridge: plugin.stop() raised: %s", exc)

        # Give the plugin thread a moment to notice the stop flag, then quit.
        from PySide6.QtCore import QCoreApplication
        QTimer.singleShot(400, QCoreApplication.quit)

    def _on_disconnected(self) -> None:
        _log.debug("WorkerBridge: host disconnected")
        self._handle_stop()
