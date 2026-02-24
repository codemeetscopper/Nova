from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QPushButton,
    QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)


# ── Thread-safe signal bridge ────────────────────────────────────────────────

class _LogSignaller(QObject):
    new_record = Signal(int, str, str)   # levelno, levelname, formatted_message


class _GuiLogHandler(logging.Handler):
    """Routes log records to the GUI via Qt signals (thread-safe)."""

    def __init__(self, signaller: _LogSignaller):
        super().__init__()
        self._sig = signaller

    def emit(self, record: logging.LogRecord) -> None:
        try:
            formatted = self.format(record)
            self._sig.new_record.emit(record.levelno, record.levelname, formatted)
        except Exception:
            pass


# ── Log page ─────────────────────────────────────────────────────────────────

class LogPage(QWidget):
    """Scrollable, filterable log viewer wired to the root Python logger."""

    # Level → (display label, colour)
    _LEVELS: dict[int, tuple[str, str]] = {
        logging.DEBUG:    ("DEBUG",    "#888888"),
        logging.INFO:     ("INFO",     "#4CAF50"),
        logging.WARNING:  ("WARNING",  "#FF9800"),
        logging.ERROR:    ("ERROR",    "#F44336"),
        logging.CRITICAL: ("CRITICAL", "#9C27B0"),
    }

    def __init__(self, ctx=None, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx = ctx
        self.setObjectName("LogPage")

        # All records ever received — stored for re-filtering
        self._all_records: List[Tuple[int, str, str]] = []

        # ── Signal bridge ────────────────────────────────────────────────────
        self._signaller = _LogSignaller()
        self._signaller.new_record.connect(self._on_new_record)

        handler = _GuiLogHandler(self._signaller)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        ))
        logging.getLogger().addHandler(handler)

        # ── Restore persisted level ──────────────────────────────────────────
        saved_level = "DEBUG"
        if ctx is not None:
            try:
                saved_level = ctx.config.get_value("system.log_level", "DEBUG")
            except Exception:
                pass
        self._min_level: int = getattr(logging, saved_level, logging.DEBUG)

        # ── Layout ───────────────────────────────────────────────────────────
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(10)

        # Toolbar — no title (page header shows it)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addStretch()

        from PySide6.QtWidgets import QLabel
        level_lbl = QLabel("Level:")
        level_lbl.setObjectName("LogFilterLabel")
        toolbar.addWidget(level_lbl)

        self._level_combo = QComboBox()
        self._level_combo.setObjectName("LogLevelCombo")
        self._level_combo.setMinimumWidth(100)
        for name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            self._level_combo.addItem(name)

        # Set saved level without triggering the signal yet
        self._level_combo.blockSignals(True)
        idx = self._level_combo.findText(saved_level)
        if idx >= 0:
            self._level_combo.setCurrentIndex(idx)
        self._level_combo.blockSignals(False)

        self._level_combo.currentTextChanged.connect(self._on_level_changed)
        toolbar.addWidget(self._level_combo)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("LogClearButton")
        clear_btn.clicked.connect(self._on_clear)
        toolbar.addWidget(clear_btn)

        outer.addLayout(toolbar)

        # Text view
        self._view = QTextEdit()
        self._view.setObjectName("LogView")
        self._view.setReadOnly(True)
        self._view.setFont(QFont("Consolas, Courier New, monospace", 11))
        self._view.setLineWrapMode(QTextEdit.NoWrap)
        self._view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer.addWidget(self._view, 1)

        # auto-scroll flag
        self._auto_scroll = True
        self._view.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)

    # ── Public ───────────────────────────────────────────────────────────────

    def clear(self) -> None:
        self._all_records.clear()
        self._view.clear()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _render_record(self, levelno: int, formatted: str) -> None:
        _, color = self._LEVELS.get(levelno, ("", "#CCCCCC"))
        safe = (formatted
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
        html = f'<span style="color:{color}; white-space:pre;">{safe}</span>'
        cursor = self._view.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._view.setTextCursor(cursor)
        self._view.insertHtml(html + "<br>")

    def _rerender(self) -> None:
        """Rebuild the view from _all_records using the current filter level."""
        was_auto = self._auto_scroll
        self._view.clear()
        for levelno, _levelname, formatted in self._all_records:
            if levelno >= self._min_level:
                self._render_record(levelno, formatted)
        if was_auto:
            sb = self._view.verticalScrollBar()
            sb.setValue(sb.maximum())
            self._auto_scroll = True

    def _on_new_record(self, levelno: int, levelname: str, formatted: str) -> None:
        self._all_records.append((levelno, levelname, formatted))
        if levelno < self._min_level:
            return
        self._render_record(levelno, formatted)
        if self._auto_scroll:
            self._view.verticalScrollBar().setValue(
                self._view.verticalScrollBar().maximum()
            )

    def _on_level_changed(self, text: str) -> None:
        self._min_level = getattr(logging, text, logging.DEBUG)
        if self._ctx is not None:
            try:
                self._ctx.config.set_value("system.log_level", text)
            except Exception:
                pass
        self._rerender()

    def _on_clear(self) -> None:
        self._all_records.clear()
        self._view.clear()

    def _on_scroll_changed(self, value: int) -> None:
        sb = self._view.verticalScrollBar()
        self._auto_scroll = (value >= sb.maximum() - 4)
