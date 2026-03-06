"""
Secure Share Plugin
===================
Encrypted file sharing over LAN with UDP auto-discovery and passphrase
protection (Fernet + PBKDF2).

Host side: tabbed UI (Receive / Send) for receiving and sending files.
Worker side: idle (networking runs in daemon threads on the host).

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

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from nova.core.plugin_base import PluginBase

# ── Constants ─────────────────────────────────────────────────────
MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10 GB
MAX_CONCURRENT_TRANSFERS = 3
CHUNK_SIZE = 16 * 1024  # 16 KB
DISCOVERY_PORT = 37020
DISCOVERY_INTERVAL = 2.0
SALT = b"pyside6-file-share-salt"


# ── Crypto ────────────────────────────────────────────────────────
def _derive_key(passphrase: str) -> bytes:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=SALT,
        iterations=200_000, backend=default_backend(),
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


# ── Network helpers ───────────────────────────────────────────────
def _recvall(sock: socket.socket, n: int, timeout: float = 5.0) -> Optional[bytes]:
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


def _send_encrypted_token(sock: socket.socket, fernet, obj: dict):
    raw = json.dumps(obj).encode("utf-8")
    token = fernet.encrypt(raw)
    sock.sendall(struct.pack("!I", len(token)))
    sock.sendall(token)


def _recv_encrypted_token(sock: socket.socket, fernet):
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


# ── Discovery ─────────────────────────────────────────────────────
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


# ── File Server ───────────────────────────────────────────────────
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


# ── File Client (signal-based) ────────────────────────────────────
class _FileClient(QObject):
    progress = Signal(int)
    status = Signal(str)

    def send_file(self, host: str, port: int, filepath: str,
                  passphrase: str):
        threading.Thread(
            target=self._send_thread,
            args=(host, port, filepath, passphrase), daemon=True,
        ).start()

    def _send_thread(self, host: str, port: int, filepath: str,
                     passphrase: str):
        from cryptography.fernet import Fernet
        try:
            self.status.emit(f"Connecting to {host}:{port}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((host, port))
            sock.settimeout(None)
            self.status.emit("Connected")

            fpath = Path(filepath)
            filesize = fpath.stat().st_size
            if filesize > MAX_FILE_SIZE:
                self.status.emit("File too large")
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


# ── Helper: post callable to main thread ──────────────────────────
class _FuncEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, fn):
        super().__init__(_FuncEvent.EVENT_TYPE)
        self.fn = fn


# ── Server Tab ────────────────────────────────────────────────────
class _ServerTab(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._server: _FileServer | None = None
        self._server_stop = threading.Event()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(8)
        self._port_input = QLineEdit("9009")
        form.addRow("Port:", self._port_input)

        folder_row = QHBoxLayout()
        self._folder_label = QLabel(str(Path.home() / "Downloads"))
        self._folder_label.setWordWrap(True)
        self._folder_label.setStyleSheet("background: transparent;")
        btn_folder = QPushButton("Browse")
        btn_folder.setCursor(Qt.PointingHandCursor)
        btn_folder.clicked.connect(self._choose_folder)
        folder_row.addWidget(self._folder_label, 1)
        folder_row.addWidget(btn_folder)
        form.addRow("Save to:", folder_row)

        self._pass_input = QLineEdit()
        self._pass_input.setEchoMode(QLineEdit.Password)
        self._pass_input.setPlaceholderText("Required — clients must use same passphrase")
        form.addRow("Passphrase:", self._pass_input)

        layout.addLayout(form)

        self._toggle_btn = QPushButton("Start Server")
        self._toggle_btn.setObjectName("ServerToggle")
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_server)
        layout.addWidget(self._toggle_btn)

        self._log_list = QListWidget()
        layout.addWidget(self._log_list, 1)

        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._save_folder = Path.home() / "Downloads"

    def _choose_folder(self):
        d = QFileDialog.getExistingDirectory(
            self, "Save folder", str(self._save_folder),
        )
        if d:
            self._save_folder = Path(d)
            self._folder_label.setText(str(self._save_folder))

    def _log(self, msg: str):
        self._log_list.addItem(msg)
        self._log_list.scrollToBottom()

    def _toggle_server(self):
        if self._server and self._server.is_alive():
            self._server_stop.set()
            self._server.join(timeout=2.0)
            self._server = None
            self._toggle_btn.setText("Start Server")
            self._toggle_btn.setProperty("running", False)
            self._toggle_btn.style().unpolish(self._toggle_btn)
            self._toggle_btn.style().polish(self._toggle_btn)
            self._log("Server stopping...")
            self._server_stop = threading.Event()
            return

        try:
            port = int(self._port_input.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid port", "Enter a valid port number.")
            return
        passphrase = self._pass_input.text().strip()
        if not passphrase:
            QMessageBox.warning(
                self, "Passphrase required",
                "Set a passphrase. Clients must use the same one.",
            )
            return

        self._save_folder.mkdir(parents=True, exist_ok=True)
        self._server = _FileServer(
            port=port,
            save_folder=str(self._save_folder),
            passphrase=passphrase,
            stop_event=self._server_stop,
            log_fn=self._log,
        )
        self._server.start()
        self._toggle_btn.setText("Stop Server")
        self._toggle_btn.setProperty("running", True)
        self._toggle_btn.style().unpolish(self._toggle_btn)
        self._toggle_btn.style().polish(self._toggle_btn)
        self._log("Server started")

    def cleanup(self):
        if self._server and self._server.is_alive():
            self._server_stop.set()
            self._server.join(timeout=2.0)


# ── Client Tab ────────────────────────────────────────────────────
class _ClientTab(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._discovery_stop = threading.Event()
        self._discovered: dict[Tuple[str, int], dict] = {}
        self._discovered_lock = threading.Lock()
        self._selected_target: Optional[Tuple[str, int]] = None
        self._filepath: Optional[str] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Discovery
        disc_box = QGroupBox("Discovered Servers")
        disc_layout = QVBoxLayout()
        disc_layout.setSpacing(8)
        self._server_list = QListWidget()
        self._server_list.setMaximumHeight(100)
        self._server_list.itemClicked.connect(self._on_server_selected)
        disc_layout.addWidget(self._server_list)
        btn_refresh = QPushButton("Search Servers")
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.clicked.connect(self._refresh_servers)
        disc_layout.addWidget(btn_refresh)
        disc_box.setLayout(disc_layout)
        layout.addWidget(disc_box)

        # Manual connect
        manual_box = QGroupBox("Manual Connect")
        manual_layout = QHBoxLayout()
        manual_layout.setSpacing(8)
        self._manual_input = QLineEdit()
        self._manual_input.setPlaceholderText("IP:Port (e.g. 192.168.1.5:9009)")
        btn_manual = QPushButton("Add")
        btn_manual.setCursor(Qt.PointingHandCursor)
        btn_manual.clicked.connect(self._use_manual)
        manual_layout.addWidget(self._manual_input, 1)
        manual_layout.addWidget(btn_manual)
        manual_box.setLayout(manual_layout)
        layout.addWidget(manual_box)

        # File selection
        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self._file_label = QLabel("No file selected")
        self._file_label.setStyleSheet("background: transparent; color: palette(text);")
        btn_file = QPushButton("Choose File")
        btn_file.setCursor(Qt.PointingHandCursor)
        btn_file.clicked.connect(self._choose_file)
        file_row.addWidget(self._file_label, 1)
        file_row.addWidget(btn_file)
        layout.addLayout(file_row)

        # Passphrase
        pass_form = QFormLayout()
        pass_form.setSpacing(8)
        self._pass_input = QLineEdit()
        self._pass_input.setEchoMode(QLineEdit.Password)
        self._pass_input.setPlaceholderText("Must match server passphrase")
        pass_form.addRow("Passphrase:", self._pass_input)
        layout.addLayout(pass_form)

        # Send
        send_row = QHBoxLayout()
        send_row.setSpacing(8)
        btn_send = QPushButton("Send File")
        btn_send.setObjectName("SendButton")
        btn_send.setCursor(Qt.PointingHandCursor)
        btn_send.clicked.connect(self._send_file)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setTextVisible(False)
        send_row.addWidget(btn_send)
        send_row.addWidget(self._progress, 1)
        layout.addLayout(send_row)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            "background: transparent; font-size: 11px;"
        )
        layout.addWidget(self._status_label)

        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Client
        self._client = _FileClient()
        self._client.progress.connect(self._progress.setValue)
        self._client.status.connect(self._status_label.setText)

        # Discovery listener
        self._listener = _DiscoveryListener(
            self._on_discovered_udp, self._discovery_stop,
        )
        self._listener.start()

        # Periodic UI refresh
        self._refresher_stop = threading.Event()
        threading.Thread(
            target=self._ui_refresh_loop, daemon=True,
        ).start()

    def _ui_refresh_loop(self):
        while not self._refresher_stop.is_set():
            QCoreApplication.postEvent(
                self, _FuncEvent(self._update_server_list),
            )
            time.sleep(1.0)

    def event(self, event):
        if isinstance(event, _FuncEvent):
            try:
                event.fn()
            except Exception:
                pass
            return True
        return super().event(event)

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
            name = info.get("name", "?")
            self._server_list.addItem(f"{name}  —  {host}:{port}")

    def _refresh_servers(self):
        with self._discovered_lock:
            self._discovered.clear()
        self._server_list.clear()
        self._status_label.setText("Searching... (wait a few seconds)")

        def clear():
            self._status_label.setText("")
        threading.Timer(
            3.5, lambda: QCoreApplication.postEvent(self, _FuncEvent(clear)),
        ).start()

    def _use_manual(self):
        text = self._manual_input.text().strip()
        if not text:
            return
        try:
            host, port_s = text.split(":")
            port = int(port_s)
        except Exception:
            QMessageBox.warning(
                self, "Invalid format", "Enter IP:Port (e.g. 192.168.1.5:9009)",
            )
            return
        with self._discovered_lock:
            self._discovered[(host, port)] = {
                "name": "Manual", "host": host, "port": port,
            }
        self._selected_target = (host, port)
        self._update_server_list()

    def _on_server_selected(self, item):
        text = item.text()
        try:
            hostport = text.split("—")[-1].strip()
            host, port_s = hostport.split(":")
            self._selected_target = (host.strip(), int(port_s))
            self._manual_input.setText(f"{host.strip()}:{port_s.strip()}")
        except Exception:
            pass

    def _choose_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select file to send")
        if f:
            self._filepath = f
            self._file_label.setText(Path(f).name)

    def _send_file(self):
        target = self._selected_target
        manual = self._manual_input.text().strip()
        if manual:
            try:
                host, port_s = manual.split(":")
                target = (host.strip(), int(port_s))
            except Exception:
                QMessageBox.warning(
                    self, "Invalid address", "Enter IP:Port format.",
                )
                return
        if not target:
            QMessageBox.warning(
                self, "No server", "Select a server or enter an address.",
            )
            return
        if not self._filepath:
            QMessageBox.warning(self, "No file", "Choose a file to send.")
            return
        passphrase = self._pass_input.text().strip()
        if not passphrase:
            QMessageBox.warning(
                self, "Passphrase required",
                "Enter the passphrase the server is using.",
            )
            return

        host, port = target
        self._status_label.setText(f"Sending to {host}:{port}...")
        self._progress.setValue(0)
        self._client.send_file(host, port, self._filepath, passphrase)

    def cleanup(self):
        self._discovery_stop.set()
        self._refresher_stop.set()


# ── Plugin ────────────────────────────────────────────────────────
class Plugin(PluginBase):

    def __init__(self, bridge):
        super().__init__(bridge)
        self._server_tab: _ServerTab | None = None
        self._client_tab: _ClientTab | None = None

    # ── HOST side ────────────────────────────────────────────

    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        frame = QFrame(parent)
        frame.setObjectName("SecureShareFrame")
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(12)

        tabs = QTabWidget()
        tabs.setObjectName("SecureShareTabs")

        self._server_tab = _ServerTab()
        self._client_tab = _ClientTab()

        tabs.addTab(self._server_tab, "Receive")
        tabs.addTab(self._client_tab, "Send")

        v.addWidget(tabs, 1)

        scroll.setWidget(content)
        outer.addWidget(scroll)

        return frame

    def on_data(self, key: str, value: Any) -> None:
        pass

    # ── WORKER side ──────────────────────────────────────────

    def start(self) -> None:
        super().start()
        import time
        while self.is_running:
            time.sleep(1)

    def stop(self) -> None:
        super().stop()
        if self._server_tab:
            self._server_tab.cleanup()
        if self._client_tab:
            self._client_tab.cleanup()
