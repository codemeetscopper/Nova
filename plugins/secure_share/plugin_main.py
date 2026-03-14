"""
Secure Share Plugin
===================
Encrypted file sharing over LAN with UDP auto-discovery and passphrase
protection (Fernet + PBKDF2).

Redesigned with a two-panel layout: Receive (left) and Send (right),
both always visible for quick, intuitive file sharing.

Dependencies: cryptography, PySide6
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional, Tuple

from PySide6.QtCore import (
    QCoreApplication, QEvent, QObject, QSize, Qt, Signal, QTimer,
)
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from nova.core.icons import IconManager
from nova.core.plugin_base import PluginBase
from nova.core.style import StyleManager

# ── Constants ─────────────────────────────────────────────────────
MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10 GB
MAX_CONCURRENT_TRANSFERS = 3
CHUNK_SIZE = 16 * 1024  # 16 KB
DISCOVERY_PORT = 37020
DISCOVERY_INTERVAL = 2.0
SALT = b"pyside6-file-share-salt"


# ══════════════════════════════════════════════════════════════════
#  Crypto + Network helpers (unchanged logic, cleaned up)
# ══════════════════════════════════════════════════════════════════

def _derive_key(passphrase: str) -> bytes:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=SALT,
        iterations=200_000, backend=default_backend(),
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def _recvall(sock: socket.socket, n: int, timeout: float = 5.0):
    buf = b""
    end = time.time() + timeout if timeout else None
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except socket.timeout:
            if end and time.time() > end:
                return None
            continue
        except Exception:
            return None
        if not chunk:
            return None
        buf += chunk
    return buf


def _send_encrypted_token(sock, fernet, obj: dict):
    raw = json.dumps(obj).encode("utf-8")
    token = fernet.encrypt(raw)
    sock.sendall(struct.pack("!I", len(token)))
    sock.sendall(token)


def _recv_encrypted_token(sock, fernet):
    data = _recvall(sock, 4)
    if not data:
        return None
    (length,) = struct.unpack("!I", data)
    if length <= 0:
        return None
    token = _recvall(sock, length)
    if token is None:
        return None
    raw = fernet.decrypt(token)
    return json.loads(raw.decode("utf-8"))


# ══════════════════════════════════════════════════════════════════
#  Discovery
# ══════════════════════════════════════════════════════════════════

class _DiscoveryBroadcaster(threading.Thread):
    def __init__(self, server_name: str, tcp_port: int,
                 stop_event: threading.Event):
        super().__init__(daemon=True)
        self.server_name = server_name
        self.tcp_port = tcp_port
        self.stop_event = stop_event

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception:
            pass
        msg = json.dumps({
            "name": self.server_name, "port": self.tcp_port,
        }).encode("utf-8")
        while not self.stop_event.is_set():
            try:
                sock.sendto(msg, ("255.255.255.255", DISCOVERY_PORT))
            except Exception:
                pass
            time.sleep(DISCOVERY_INTERVAL)
        sock.close()


class _DiscoveryListener(threading.Thread):
    def __init__(self, on_discovered, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.on_discovered = on_discovered
        self.stop_event = stop_event

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception:
            pass
        try:
            sock.bind(("", DISCOVERY_PORT))
        except Exception:
            try:
                sock.bind(("0.0.0.0", DISCOVERY_PORT))
            except Exception:
                sock.close()
                return
        sock.settimeout(1.0)
        while not self.stop_event.is_set():
            try:
                data, addr = sock.recvfrom(4096)
                info = json.loads(data.decode("utf-8"))
                info["host"] = addr[0]
                self.on_discovered(info)
            except socket.timeout:
                continue
            except Exception:
                continue
        sock.close()


# ══════════════════════════════════════════════════════════════════
#  File Server
# ══════════════════════════════════════════════════════════════════

class _FileServer(threading.Thread):
    def __init__(self, port: int, save_folder: str, passphrase: str,
                 stop_event: threading.Event, log_fn=None):
        super().__init__(daemon=True)
        self.port = port
        self.save_folder = Path(save_folder)
        self.passphrase = passphrase
        self.stop_event = stop_event
        self._log_fn = log_fn
        self._sema = threading.Semaphore(MAX_CONCURRENT_TRANSFERS)

    def _log(self, msg: str):
        if self._log_fn:
            try:
                self._log_fn(msg)
            except Exception:
                pass

    def run(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception:
            pass
        try:
            srv.bind(("", self.port))
            srv.listen(5)
        except Exception as e:
            self._log(f"Failed to bind: {e}")
            return

        bc_stop = threading.Event()
        bc = _DiscoveryBroadcaster(socket.gethostname(), self.port, bc_stop)
        bc.start()
        self._log(f"Listening on port {self.port}")

        try:
            while not self.stop_event.is_set():
                srv.settimeout(1.0)
                try:
                    client, addr = srv.accept()
                    self._log(f"Connection from {addr[0]}")
                    if not self._sema.acquire(blocking=False):
                        self._log("Too many transfers; rejecting.")
                        try:
                            client.sendall(b"ERR_BUSY")
                        except Exception:
                            pass
                        client.close()
                        continue
                    threading.Thread(
                        target=self._handle_wrapper,
                        args=(client, addr), daemon=True,
                    ).start()
                except socket.timeout:
                    continue
        finally:
            bc_stop.set()
            bc.join(timeout=1.0)
            srv.close()
            self._log("Server stopped")

    def _handle_wrapper(self, client, addr):
        try:
            self._handle_client(client, addr)
        finally:
            self._sema.release()

    def _handle_client(self, client: socket.socket, addr):
        from cryptography.fernet import Fernet, InvalidToken
        tmp_path = None
        try:
            client.settimeout(10.0)
            raw = _recvall(client, 4, 10.0)
            if not raw:
                client.close()
                return
            (hlen,) = struct.unpack("!I", raw)
            initial = _recvall(client, hlen, 10.0)
            if not initial:
                client.close()
                return
            obj = json.loads(initial.decode("utf-8"))
            if obj.get("mode") != "passphrase":
                client.close()
                return

            key = _derive_key(self.passphrase)
            fernet = Fernet(key)

            try:
                header = _recv_encrypted_token(client, fernet)
            except InvalidToken:
                self._log("Wrong passphrase or corrupted header.")
                client.close()
                return
            if not header:
                client.close()
                return

            filename = os.path.basename(header.get("filename", "received.bin"))
            filesize = int(header.get("size", 0))
            if filesize < 0 or filesize > MAX_FILE_SIZE:
                self._log(f"Invalid file size: {filesize}")
                client.close()
                return

            fd, tmp_path = tempfile.mkstemp(
                prefix=filename + ".", dir=str(self.save_folder),
            )
            os.close(fd)
            self._log(f"Receiving '{filename}' ({filesize:,} bytes)")

            received = 0
            last_sync = time.time()
            with open(tmp_path, "wb") as f:
                while True:
                    lenbytes = _recvall(client, 4, 10.0)
                    if not lenbytes:
                        break
                    (length,) = struct.unpack("!I", lenbytes)
                    if length == 0:
                        break
                    token = _recvall(client, length, 30.0)
                    if token is None:
                        break
                    try:
                        plain = fernet.decrypt(token)
                    except InvalidToken:
                        self._log("Invalid token — aborting.")
                        break
                    f.write(plain)
                    received += len(plain)
                    if time.time() - last_sync > 1.0:
                        try:
                            f.flush()
                            os.fsync(f.fileno())
                        except Exception:
                            pass
                        last_sync = time.time()
                    if received % (1024 * 1024) < CHUNK_SIZE:
                        self._log(f"  {received:,}/{filesize:,} bytes")
                    if received >= filesize:
                        break

            actual = os.path.getsize(tmp_path)
            if actual != filesize:
                self._log(f"Size mismatch: expected {filesize}, got {actual}")
                os.remove(tmp_path)
                tmp_path = None
                try:
                    client.sendall(b"ERR_SIZE_MISMATCH")
                except Exception:
                    pass
                client.close()
                return

            outpath = self.save_folder / filename
            os.replace(tmp_path, str(outpath))
            tmp_path = None
            self._log(f"Saved '{filename}' ({actual:,} bytes)")
            try:
                client.sendall(b"OK")
            except Exception:
                pass
        except Exception as e:
            self._log(f"Error from {addr}: {e}")
        finally:
            try:
                client.close()
            except Exception:
                pass
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass


# ══════════════════════════════════════════════════════════════════
#  File Client (signal-based)
# ══════════════════════════════════════════════════════════════════

class _FileClient(QObject):
    progress = Signal(int)
    status = Signal(str)

    def send_file(self, host: str, port: int, filepath: str,
                  passphrase: str):
        threading.Thread(
            target=self._send_thread,
            args=(host, port, filepath, passphrase), daemon=True,
        ).start()

    def _send_thread(self, host, port, filepath, passphrase):
        from cryptography.fernet import Fernet
        try:
            self.status.emit(f"Connecting to {host}:{port}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((host, port))
            sock.settimeout(None)
            self.status.emit("Connected — sending...")

            fpath = Path(filepath)
            filesize = fpath.stat().st_size
            if filesize > MAX_FILE_SIZE:
                self.status.emit("File too large (max 10 GB)")
                return

            initial = json.dumps({"mode": "passphrase"}).encode("utf-8")
            sock.sendall(struct.pack("!I", len(initial)))
            sock.sendall(initial)

            key = _derive_key(passphrase)
            fernet = Fernet(key)

            _send_encrypted_token(sock, fernet, {
                "filename": fpath.name, "size": filesize,
            })

            sent = 0
            last_pct = -1
            with open(fpath, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    token = fernet.encrypt(chunk)
                    sock.sendall(struct.pack("!I", len(token)))
                    sock.sendall(token)
                    sent += len(chunk)
                    pct = int(sent * 100 / filesize) if filesize else 100
                    if pct != last_pct:
                        self.progress.emit(pct)
                        last_pct = pct

            sock.sendall(struct.pack("!I", 0))  # EOF

            try:
                sock.settimeout(10.0)
                resp = sock.recv(64)
                if resp == b"OK":
                    self.status.emit("Transfer complete")
                    self.progress.emit(100)
                elif resp == b"ERR_BUSY":
                    self.status.emit("Server busy — try again later")
                elif resp == b"ERR_SIZE_MISMATCH":
                    self.status.emit("Server reported size mismatch")
                else:
                    self.status.emit("Unknown server response")
            except Exception:
                self.status.emit("No response from server")
            sock.close()
        except Exception as e:
            self.status.emit(f"Send failed: {e}")
            self.progress.emit(0)


# ══════════════════════════════════════════════════════════════════
#  Helper: post callable to main thread
# ══════════════════════════════════════════════════════════════════

class _FuncEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, fn):
        super().__init__(_FuncEvent.EVENT_TYPE)
        self.fn = fn


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ══════════════════════════════════════════════════════════════════
#  UI widgets
# ══════════════════════════════════════════════════════════════════

class _StatusDot(QLabel):
    """Tiny coloured dot for status indication."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self.setObjectName("SSStatusDot")
        self.set_color("#888")

    def set_color(self, color: str):
        self.setStyleSheet(
            f"background:{color};border-radius:4px;border:none;")


class _SectionHeader(QWidget):
    """Section header with icon, title, and optional right-side widget."""
    def __init__(self, icon_name: str, title: str, right: QWidget | None = None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("SSSectionHeader")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._icon = QLabel()
        self._icon.setFixedSize(20, 20)
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon_name = icon_name
        self._refresh_icon()
        lay.addWidget(self._icon)

        lbl = QLabel(title)
        lbl.setObjectName("SSSectionTitle")
        lay.addWidget(lbl, 1)

        if right:
            lay.addWidget(right)

    def _refresh_icon(self):
        accent = StyleManager.get_colour("accent")
        pm = IconManager.get_pixmap(self._icon_name, accent, 18)
        if pm:
            self._icon.setPixmap(pm)


class _InputRow(QWidget):
    """Label + input on one line."""
    def __init__(self, label: str, placeholder: str = "",
                 echo_mode=None, parent=None):
        super().__init__(parent)
        self.setObjectName("SSInputRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lbl = QLabel(label)
        lbl.setObjectName("SSInputLabel")
        lbl.setFixedWidth(80)
        lay.addWidget(lbl)

        self.input = QLineEdit()
        self.input.setPlaceholderText(placeholder)
        if echo_mode:
            self.input.setEchoMode(echo_mode)
        lay.addWidget(self.input, 1)

    def text(self) -> str:
        return self.input.text().strip()


class _LogPanel(QFrame):
    """Compact scrollable log with timestamp."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SSLogPanel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(0)
        self._list = QListWidget()
        self._list.setObjectName("SSLogList")
        lay.addWidget(self._list)

    def log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._list.addItem(f"[{ts}]  {msg}")
        self._list.scrollToBottom()

    def clear_log(self):
        self._list.clear()


# ══════════════════════════════════════════════════════════════════
#  Receive Panel (Server)
# ══════════════════════════════════════════════════════════════════

class _ReceivePanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SSPanel")
        self._server: _FileServer | None = None
        self._server_stop = threading.Event()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        # Header with status
        self._status_dot = _StatusDot()
        self._status_label = QLabel("Stopped")
        self._status_label.setObjectName("SSStatusLabel")
        status_w = QWidget()
        sl = QHBoxLayout(status_w)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(6)
        sl.addWidget(self._status_dot)
        sl.addWidget(self._status_label)

        lay.addWidget(_SectionHeader("backup", "Receive Files", status_w))

        # Separator
        sep = QFrame(); sep.setObjectName("SSSep"); sep.setFixedHeight(1)
        lay.addWidget(sep)

        # Config
        self._port_row = _InputRow("Port", "9009")
        self._port_row.input.setText("9009")
        lay.addWidget(self._port_row)

        self._pass_row = _InputRow("Passphrase", "Required for encryption",
                                    echo_mode=QLineEdit.Password)
        lay.addWidget(self._pass_row)

        # Save folder
        folder_w = QWidget()
        folder_w.setObjectName("SSInputRow")
        fl = QHBoxLayout(folder_w)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(10)
        flbl = QLabel("Save to")
        flbl.setObjectName("SSInputLabel")
        flbl.setFixedWidth(80)
        fl.addWidget(flbl)
        self._folder_label = QLabel(str(Path.home() / "Downloads"))
        self._folder_label.setObjectName("SSFolderPath")
        self._folder_label.setWordWrap(True)
        fl.addWidget(self._folder_label, 1)
        btn_browse = QPushButton("Browse")
        btn_browse.setObjectName("SSSmallBtn")
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.clicked.connect(self._choose_folder)
        fl.addWidget(btn_browse)
        lay.addWidget(folder_w)

        # Toggle button
        self._toggle_btn = QPushButton("Start Receiving")
        self._toggle_btn.setObjectName("SSPrimaryBtn")
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_server)
        lay.addWidget(self._toggle_btn)

        # Log
        self._log_panel = _LogPanel()
        lay.addWidget(self._log_panel, 1)

        self._save_folder = Path.home() / "Downloads"

    def _choose_folder(self):
        d = QFileDialog.getExistingDirectory(
            self, "Save folder", str(self._save_folder))
        if d:
            self._save_folder = Path(d)
            self._folder_label.setText(str(self._save_folder))

    def _log(self, msg: str):
        # Thread-safe: post to main thread
        QCoreApplication.postEvent(
            self, _FuncEvent(lambda: self._log_panel.log(msg)))

    def event(self, ev):
        if isinstance(ev, _FuncEvent):
            try:
                ev.fn()
            except Exception:
                pass
            return True
        return super().event(ev)

    def _toggle_server(self):
        if self._server and self._server.is_alive():
            self._server_stop.set()
            self._server.join(timeout=2.0)
            self._server = None
            self._toggle_btn.setText("Start Receiving")
            self._toggle_btn.setProperty("running", False)
            self._toggle_btn.style().unpolish(self._toggle_btn)
            self._toggle_btn.style().polish(self._toggle_btn)
            self._status_dot.set_color("#888")
            self._status_label.setText("Stopped")
            self._log_panel.log("Server stopped")
            self._server_stop = threading.Event()
            return

        try:
            port = int(self._port_row.text() or "9009")
        except ValueError:
            QMessageBox.warning(self, "Invalid port",
                                "Enter a valid port number.")
            return
        passphrase = self._pass_row.text()
        if not passphrase:
            QMessageBox.warning(self, "Passphrase required",
                                "Set a passphrase. Senders must use the same one.")
            return

        self._save_folder.mkdir(parents=True, exist_ok=True)
        self._server = _FileServer(
            port=port, save_folder=str(self._save_folder),
            passphrase=passphrase, stop_event=self._server_stop,
            log_fn=self._log,
        )
        self._server.start()
        self._toggle_btn.setText("Stop Receiving")
        self._toggle_btn.setProperty("running", True)
        self._toggle_btn.style().unpolish(self._toggle_btn)
        self._toggle_btn.style().polish(self._toggle_btn)
        self._status_dot.set_color("#22C55E")
        self._status_label.setText(f"Listening on :{port}")
        self._log_panel.log(f"Server started on port {port}")

    def cleanup(self):
        if self._server and self._server.is_alive():
            self._server_stop.set()
            self._server.join(timeout=2.0)


# ══════════════════════════════════════════════════════════════════
#  Send Panel (Client)
# ══════════════════════════════════════════════════════════════════

class _SendPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SSPanel")
        self._discovery_stop = threading.Event()
        self._discovered: dict[Tuple[str, int], dict] = {}
        self._discovered_lock = threading.Lock()
        self._filepath: Optional[str] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        # Header with status
        self._status_label = QLabel("")
        self._status_label.setObjectName("SSStatusLabel")
        lay.addWidget(_SectionHeader("open_in_new", "Send Files",
                                      self._status_label))

        sep = QFrame(); sep.setObjectName("SSSep"); sep.setFixedHeight(1)
        lay.addWidget(sep)

        # Server discovery
        disc_header = QWidget()
        dh = QHBoxLayout(disc_header)
        dh.setContentsMargins(0, 0, 0, 0)
        dh.setSpacing(8)
        dl = QLabel("Available Servers")
        dl.setObjectName("SSSubLabel")
        dh.addWidget(dl, 1)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.setObjectName("SSSmallBtn")
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.clicked.connect(self._refresh_servers)
        dh.addWidget(btn_refresh)
        lay.addWidget(disc_header)

        self._server_list = QListWidget()
        self._server_list.setObjectName("SSServerList")
        self._server_list.setMaximumHeight(90)
        self._server_list.itemClicked.connect(self._on_server_selected)
        lay.addWidget(self._server_list)

        # Manual address
        self._addr_row = _InputRow("Server", "IP:Port (e.g. 192.168.1.5:9009)")
        lay.addWidget(self._addr_row)

        # Passphrase
        self._pass_row = _InputRow("Passphrase", "Must match server passphrase",
                                    echo_mode=QLineEdit.Password)
        lay.addWidget(self._pass_row)

        # File selection
        file_w = QWidget()
        file_w.setObjectName("SSInputRow")
        file_lay = QHBoxLayout(file_w)
        file_lay.setContentsMargins(0, 0, 0, 0)
        file_lay.setSpacing(10)
        flbl = QLabel("File")
        flbl.setObjectName("SSInputLabel")
        flbl.setFixedWidth(80)
        file_lay.addWidget(flbl)
        self._file_label = QLabel("No file selected")
        self._file_label.setObjectName("SSFolderPath")
        self._file_label.setWordWrap(True)
        file_lay.addWidget(self._file_label, 1)
        btn_file = QPushButton("Choose")
        btn_file.setObjectName("SSSmallBtn")
        btn_file.setCursor(Qt.PointingHandCursor)
        btn_file.clicked.connect(self._choose_file)
        file_lay.addWidget(btn_file)
        lay.addWidget(file_w)

        # File info
        self._file_info = QLabel("")
        self._file_info.setObjectName("SSFileInfo")
        self._file_info.hide()
        lay.addWidget(self._file_info)

        # Send button + progress
        send_w = QWidget()
        sw = QVBoxLayout(send_w)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.setSpacing(8)

        self._send_btn = QPushButton("Send File")
        self._send_btn.setObjectName("SSPrimaryBtn")
        self._send_btn.setCursor(Qt.PointingHandCursor)
        self._send_btn.clicked.connect(self._send_file)
        sw.addWidget(self._send_btn)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setTextVisible(False)
        self._progress.setObjectName("SSProgress")
        self._progress.hide()
        sw.addWidget(self._progress)

        self._transfer_status = QLabel("")
        self._transfer_status.setObjectName("SSTransferStatus")
        self._transfer_status.setWordWrap(True)
        sw.addWidget(self._transfer_status)

        lay.addWidget(send_w)
        lay.addStretch()

        # Client
        self._client = _FileClient()
        self._client.progress.connect(self._on_progress)
        self._client.status.connect(self._on_status)

        # Discovery listener
        self._listener = _DiscoveryListener(
            self._on_discovered_udp, self._discovery_stop)
        self._listener.start()

        # Periodic UI refresh
        self._refresher_stop = threading.Event()
        threading.Thread(target=self._ui_refresh_loop, daemon=True).start()

    def event(self, ev):
        if isinstance(ev, _FuncEvent):
            try:
                ev.fn()
            except Exception:
                pass
            return True
        return super().event(ev)

    def _ui_refresh_loop(self):
        while not self._refresher_stop.is_set():
            QCoreApplication.postEvent(
                self, _FuncEvent(self._update_server_list))
            time.sleep(1.0)

    def _on_discovered_udp(self, info: dict):
        try:
            host = info["host"]
            port = int(info["port"])
        except Exception:
            return
        with self._discovered_lock:
            self._discovered[(host, port)] = info

    def _update_server_list(self):
        with self._discovered_lock:
            items = list(self._discovered.items())
        self._server_list.clear()
        for (host, port), info in items:
            name = info.get("name", "Unknown")
            item = QListWidgetItem(f"{name}  \u2014  {host}:{port}")
            self._server_list.addItem(item)

    def _refresh_servers(self):
        with self._discovered_lock:
            self._discovered.clear()
        self._server_list.clear()
        self._transfer_status.setText("Searching for servers...")
        QTimer.singleShot(3000, lambda: (
            self._transfer_status.setText("")
            if self._transfer_status.text() == "Searching for servers..."
            else None
        ))

    def _on_server_selected(self, item):
        text = item.text()
        try:
            hostport = text.split("\u2014")[-1].strip()
            self._addr_row.input.setText(hostport)
        except Exception:
            pass

    def _choose_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select file to send")
        if f:
            self._filepath = f
            p = Path(f)
            self._file_label.setText(p.name)
            size = p.stat().st_size
            self._file_info.setText(
                f"{_human_size(size)}  \u2022  {p.suffix or 'file'}")
            self._file_info.show()

    def _send_file(self):
        addr_text = self._addr_row.text()
        if not addr_text:
            QMessageBox.warning(self, "No server",
                                "Select or enter a server address.")
            return
        try:
            host, port_s = addr_text.split(":")
            host = host.strip()
            port = int(port_s.strip())
        except Exception:
            QMessageBox.warning(self, "Invalid address",
                                "Enter IP:Port format (e.g. 192.168.1.5:9009)")
            return
        if not self._filepath:
            QMessageBox.warning(self, "No file", "Choose a file to send.")
            return
        passphrase = self._pass_row.text()
        if not passphrase:
            QMessageBox.warning(self, "Passphrase required",
                                "Enter the passphrase the server is using.")
            return

        self._progress.setValue(0)
        self._progress.show()
        self._send_btn.setEnabled(False)
        self._client.send_file(host, port, self._filepath, passphrase)

    def _on_progress(self, pct: int):
        self._progress.setValue(pct)
        if pct >= 100:
            self._send_btn.setEnabled(True)

    def _on_status(self, msg: str):
        self._transfer_status.setText(msg)
        if "complete" in msg.lower() or "failed" in msg.lower() or \
           "busy" in msg.lower() or "mismatch" in msg.lower():
            self._send_btn.setEnabled(True)
            if "complete" in msg.lower():
                QTimer.singleShot(3000, lambda: self._progress.hide())

    def cleanup(self):
        self._discovery_stop.set()
        self._refresher_stop.set()


# ══════════════════════════════════════════════════════════════════
#  Plugin
# ══════════════════════════════════════════════════════════════════

class Plugin(PluginBase):

    def __init__(self, bridge):
        super().__init__(bridge)
        self._receive: _ReceivePanel | None = None
        self._send: _SendPanel | None = None

    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        frame = QFrame(parent)
        frame.setObjectName("SecureShareFrame")

        outer = QVBoxLayout(frame)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setObjectName("SSContent")
        v = QVBoxLayout(content)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(16)

        # Two-panel layout: Receive | Send
        panels = QWidget()
        panels.setObjectName("SSPanels")
        h = QHBoxLayout(panels)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)

        self._receive = _ReceivePanel()
        self._send = _SendPanel()

        h.addWidget(self._receive, 1)
        h.addWidget(self._send, 1)

        v.addWidget(panels, 1)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        return frame

    def on_data(self, key: str, value: Any) -> None:
        pass

    def start(self) -> None:
        super().start()
        while self.is_running:
            time.sleep(1)

    def stop(self) -> None:
        super().stop()
        if self._receive:
            self._receive.cleanup()
        if self._send:
            self._send.cleanup()
