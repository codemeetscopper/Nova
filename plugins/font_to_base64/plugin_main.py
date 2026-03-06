"""
Font to Base64 Plugin
=====================
Host side: UI for converting font files to base64 strings.
           Supports drag-and-drop, multi-file selection, and zip extraction.
Worker side: idle (conversion is triggered on demand).

Threading: A QThread subclass runs in the HOST process for batch conversion.
The thread is parented to a widget and cleaned up via the ``finished`` signal
to avoid the "QThread: Destroyed while thread is still running" crash.
"""
from __future__ import annotations

import base64
import os
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Qt, Signal, Slot
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from nova.core.plugin_base import PluginBase

FONT_EXTENSIONS = {".ttf", ".otf", ".woff", ".woff2", ".eot"}

MIME_MAP = {
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".eot": "application/vnd.ms-fontobject",
}

BATCH_SIZE = 50          # fonts per UI update
PROGRESS_INTERVAL = 20   # emit progress every N fonts


def _encode_font(filepath: str) -> str:
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _data_uri(filepath: str, raw_b64: str) -> str:
    ext = Path(filepath).suffix.lower()
    mime = MIME_MAP.get(ext, "application/octet-stream")
    return f"data:{mime};base64,{raw_b64}"


def _extract_fonts_from_zip(zip_path: str) -> list[str]:
    extracted: list[str] = []
    tmp_dir = tempfile.mkdtemp(prefix="font_b64_")
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if Path(name).suffix.lower() in FONT_EXTENSIONS:
                zf.extract(name, tmp_dir)
                extracted.append(os.path.join(tmp_dir, name))
    return extracted


class _FontEntry:
    __slots__ = ("name", "raw_b64", "data_uri")

    def __init__(self, name: str, raw_b64: str, data_uri: str):
        self.name = name
        self.raw_b64 = raw_b64
        self.data_uri = data_uri


# ─────────────────────────────────────────────────────────────
#  QThread subclass — runs in the HOST process
# ─────────────────────────────────────────────────────────────

class _ConvertThread(QThread):
    """
    Resolves font paths (including zip extraction) and encodes to base64.

    Results are emitted in batches to avoid flooding the main-thread event
    loop.  ``requestInterruption()`` is checked between files so the thread
    can be cancelled cleanly.
    """

    batch_ready = Signal(list)   # list of (name, raw_b64, data_uri) tuples
    skipped = Signal(str)
    progress = Signal(int, int)  # current, total

    def __init__(self, paths: list[str], parent: QThread | None = None):
        super().__init__(parent)
        self._paths = paths

    def run(self) -> None:
        # ── Phase 1: resolve font file paths ──
        font_files: list[str] = []
        for p in self._paths:
            if self.isInterruptionRequested():
                return
            ext = Path(p).suffix.lower()
            if ext == ".zip":
                try:
                    extracted = _extract_fonts_from_zip(p)
                except zipfile.BadZipFile:
                    self.skipped.emit(Path(p).name)
                    continue
                if not extracted:
                    self.skipped.emit(f"{Path(p).name} (no fonts inside)")
                    continue
                font_files.extend(extracted)
            elif ext in FONT_EXTENSIONS:
                font_files.append(p)
            else:
                self.skipped.emit(Path(p).name)

        # ── Phase 2: encode ──
        total = len(font_files)
        batch: list[tuple[str, str, str]] = []
        for i, fp in enumerate(font_files, 1):
            if self.isInterruptionRequested():
                return
            raw_b64 = _encode_font(fp)
            uri = _data_uri(fp, raw_b64)
            batch.append((Path(fp).name, raw_b64, uri))

            if len(batch) >= BATCH_SIZE:
                self.batch_ready.emit(batch)
                batch = []

            if i % PROGRESS_INTERVAL == 0 or i == total:
                self.progress.emit(i, total)

        if batch:
            self.batch_ready.emit(batch)


# ─────────────────────────────────────────────────────────────
#  Drop-aware frame
# ─────────────────────────────────────────────────────────────

class _DropFrame(QFrame):
    """QFrame that accepts drag-and-drop of font/zip files."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._plugin: Plugin | None = None
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if paths and self._plugin is not None:
            self._plugin._process_paths(paths)


# ─────────────────────────────────────────────────────────────
#  Plugin
# ─────────────────────────────────────────────────────────────

class Plugin(PluginBase):

    def __init__(self, bridge):
        super().__init__(bridge)
        self._entries: list[_FontEntry] = []
        self._thread: _ConvertThread | None = None
        self._skipped: list[str] = []
        self._added_count: int = 0
        # widget refs
        self._list: QListWidget | None = None
        self._preview: QTextEdit | None = None
        self._progress: QProgressBar | None = None
        self._status: QLabel | None = None
        self._btn_add: QPushButton | None = None
        self._btn_clear: QPushButton | None = None

    # ── HOST side ────────────────────────────────────────────

    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        frame = _DropFrame(parent)
        frame._plugin = self
        frame.setObjectName("FontToBase64Frame")
        v = QVBoxLayout(frame)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(12)

        # Hint
        hint = QLabel("Drag & drop font / zip files here, or use the button below.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #888; padding: 2px;")
        v.addWidget(hint)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._btn_add = QPushButton("Add Font Files...")
        self._btn_add.setCursor(Qt.PointingHandCursor)
        self._btn_add.clicked.connect(self._on_add_files)
        toolbar.addWidget(self._btn_add)

        self._btn_clear = QPushButton("Clear All")
        self._btn_clear.setCursor(Qt.PointingHandCursor)
        self._btn_clear.clicked.connect(self._on_clear)
        toolbar.addWidget(self._btn_clear)

        toolbar.addStretch()
        v.addLayout(toolbar)

        # Splitter: file list | preview
        splitter = QSplitter(Qt.Horizontal)

        # Left: file list + copy buttons
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(QLabel("Converted fonts:"))

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.ExtendedSelection)
        self._list.currentRowChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self._list, 1)

        copy_row = QHBoxLayout()
        copy_row.setSpacing(6)

        btn_copy_sel = QPushButton("Copy Selected (raw)")
        btn_copy_sel.setCursor(Qt.PointingHandCursor)
        btn_copy_sel.clicked.connect(lambda: self._copy_selected(uri=False))
        copy_row.addWidget(btn_copy_sel)

        btn_copy_sel_uri = QPushButton("Copy Selected (data URI)")
        btn_copy_sel_uri.setCursor(Qt.PointingHandCursor)
        btn_copy_sel_uri.clicked.connect(lambda: self._copy_selected(uri=True))
        copy_row.addWidget(btn_copy_sel_uri)
        left_layout.addLayout(copy_row)

        btn_copy_all = QPushButton("Copy All (raw)")
        btn_copy_all.setCursor(Qt.PointingHandCursor)
        btn_copy_all.clicked.connect(lambda: self._copy_all(uri=False))
        left_layout.addWidget(btn_copy_all)

        btn_copy_all_uri = QPushButton("Copy All (data URIs)")
        btn_copy_all_uri.setCursor(Qt.PointingHandCursor)
        btn_copy_all_uri.clicked.connect(lambda: self._copy_all(uri=True))
        left_layout.addWidget(btn_copy_all_uri)

        splitter.addWidget(left)

        # Right: preview
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Base64 preview:"))

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setLineWrapMode(QTextEdit.WidgetWidth)
        right_layout.addWidget(self._preview, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        v.addWidget(splitter, 1)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        self._progress.setFormat("Converting... %v / %m")
        self._progress.hide()
        v.addWidget(self._progress)

        # Status label
        self._status = QLabel("")
        self._status.setStyleSheet("color: #6a6;")
        v.addWidget(self._status)

        return frame

    def on_data(self, key: str, value: Any) -> None:
        pass

    # ── Slots ────────────────────────────────────────────────

    def _on_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self._list,
            "Select font or zip files",
            "",
            "Font & Zip files (*.ttf *.otf *.woff *.woff2 *.eot *.zip);;All files (*)",
        )
        if paths:
            self._process_paths(paths)

    def _on_clear(self):
        self._cancel_thread()
        self._entries.clear()
        if self._list:
            self._list.clear()
        if self._preview:
            self._preview.clear()
        if self._status:
            self._status.setText("")

    def _on_selection_changed(self, row: int):
        if 0 <= row < len(self._entries):
            entry = self._entries[row]
            if self._preview:
                self._preview.setPlainText(entry.data_uri)
        elif self._preview:
            self._preview.clear()

    # ── Thread lifecycle ─────────────────────────────────────

    def _process_paths(self, paths: list[str]):
        self._cancel_thread()
        self._skipped.clear()
        self._added_count = 0

        if self._status:
            self._status.setText("Starting conversion...")
        if self._progress:
            self._progress.setValue(0)
            self._progress.show()
        self._set_busy(True)

        # Parent the thread to the list widget so Qt ownership keeps it alive.
        thread = _ConvertThread(paths, parent=self._list)
        thread.batch_ready.connect(self._on_batch_ready)
        thread.skipped.connect(self._on_skipped)
        thread.progress.connect(self._on_progress)
        # IMPORTANT: connect to ``finished`` (not a worker signal) so cleanup
        # runs only after the OS thread has actually stopped.
        thread.finished.connect(self._on_thread_finished)

        self._thread = thread
        thread.start()

    def _cancel_thread(self):
        """Request interruption and wait for the thread to finish."""
        if self._thread is not None and self._thread.isRunning():
            self._thread.requestInterruption()
            self._thread.wait(5000)
        self._thread = None
        if self._progress:
            self._progress.hide()

    def _set_busy(self, busy: bool):
        if self._btn_add:
            self._btn_add.setEnabled(not busy)
        if self._btn_clear:
            self._btn_clear.setEnabled(not busy)

    # ── Thread callbacks (run in main thread via queued connection) ──

    @Slot(list)
    def _on_batch_ready(self, batch: list[tuple[str, str, str]]):
        if not self._list:
            return
        # Block signals during bulk insert to avoid per-item repaints.
        self._list.blockSignals(True)
        for name, raw_b64, data_uri in batch:
            entry = _FontEntry(name, raw_b64, data_uri)
            self._entries.append(entry)
            self._list.addItem(QListWidgetItem(entry.name))
            self._added_count += 1
        self._list.blockSignals(False)

    @Slot(str)
    def _on_skipped(self, reason: str):
        self._skipped.append(reason)

    @Slot(int, int)
    def _on_progress(self, current: int, total: int):
        if self._progress:
            self._progress.setMaximum(total)
            self._progress.setValue(current)

    @Slot()
    def _on_thread_finished(self):
        """Called after the OS thread has stopped — safe to drop references."""
        if self._progress:
            self._progress.hide()
        self._set_busy(False)

        # Select the last item once (triggers one preview update).
        if self._list and self._entries:
            self._list.setCurrentRow(len(self._entries) - 1)

        parts: list[str] = []
        if self._added_count:
            parts.append(f"{self._added_count} font(s) converted")
        if self._skipped:
            parts.append(f"Skipped: {', '.join(self._skipped)}")
        if self._status:
            self._status.setText("  |  ".join(parts))

        self._thread = None

    # ── Copy helpers ─────────────────────────────────────────

    def _copy_selected(self, *, uri: bool):
        if not self._list:
            return
        rows = sorted({idx.row() for idx in self._list.selectedIndexes()})
        if not rows:
            if self._status:
                self._status.setText("Nothing selected.")
            return
        texts = []
        for r in rows:
            e = self._entries[r]
            texts.append(e.data_uri if uri else e.raw_b64)
        QApplication.clipboard().setText("\n\n".join(texts))
        label = "data URI" if uri else "raw base64"
        if self._status:
            self._status.setText(f"Copied {label} for {len(rows)} font(s) to clipboard.")

    def _copy_all(self, *, uri: bool):
        if not self._entries:
            if self._status:
                self._status.setText("No fonts loaded.")
            return
        texts = [e.data_uri if uri else e.raw_b64 for e in self._entries]
        QApplication.clipboard().setText("\n\n".join(texts))
        label = "data URIs" if uri else "raw base64"
        if self._status:
            self._status.setText(f"Copied {label} for all {len(self._entries)} font(s) to clipboard.")

    # ── WORKER side ──────────────────────────────────────────

    def start(self) -> None:
        super().start()
        while self.is_running:
            time.sleep(1)
