"""
PDF Merger Plugin
=================
Host side: UI with table for adding PDFs, page selection, and merge button.
Worker side: idle (no background work needed — merging is triggered on demand).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from nova.core.plugin_base import PluginBase


class Plugin(PluginBase):

    def __init__(self, bridge):
        super().__init__(bridge)
        self._table: QTableWidget | None = None

    # ── HOST side ────────────────────────────────────────────

    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        frame = QFrame(parent)
        frame.setObjectName("PdfMergerFrame")
        v = QVBoxLayout(frame)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        btn_add = QPushButton("Add PDFs")
        btn_add.setObjectName("PdfMergerAdd")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self._load_pdfs)
        toolbar.addWidget(btn_add)

        btn_clear = QPushButton("Clear List")
        btn_clear.setObjectName("PdfMergerClear")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self._clear_list)
        toolbar.addWidget(btn_clear)

        toolbar.addStretch()

        btn_merge = QPushButton("Merge")
        btn_merge.setObjectName("PdfMergerMerge")
        btn_merge.setCursor(Qt.PointingHandCursor)
        btn_merge.clicked.connect(self._merge_pdfs)
        toolbar.addWidget(btn_merge)

        v.addLayout(toolbar)

        # Table
        self._table = QTableWidget(0, 3)
        self._table.setObjectName("PdfMergerTable")
        self._table.setHorizontalHeaderLabels(
            ["PDF File", "Pages (e.g. 1-3,5)", ""]
        )
        self._table.horizontalHeader().setStretchLastSection(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(1, 200)
        self._table.setColumnWidth(2, 80)
        v.addWidget(self._table)

        return frame

    def _load_pdfs(self):
        files, _ = QFileDialog.getOpenFileNames(
            self._table, "Select PDF Files", "", "PDF Files (*.pdf)"
        )
        if not files:
            return

        try:
            from pypdf import PdfReader
        except ImportError:
            QMessageBox.critical(
                self._table, "Missing Dependency",
                "The 'pypdf' package is required.\n"
                "Install it with: pip install pypdf",
            )
            return

        for file in files:
            reader = PdfReader(file)
            row = self._table.rowCount()
            self._table.insertRow(row)

            item = QTableWidgetItem(file)
            item.setFlags(Qt.ItemIsEnabled)
            self._table.setItem(row, 0, item)

            page_input = QLineEdit()
            page_input.setPlaceholderText(
                f"1-{len(reader.pages)} or leave empty = all"
            )
            self._table.setCellWidget(row, 1, page_input)

            btn_remove = QPushButton("Remove")
            btn_remove.setCursor(Qt.PointingHandCursor)
            btn_remove.clicked.connect(
                lambda _, r=row: self._remove_row(r)
            )
            self._table.setCellWidget(row, 2, btn_remove)

    def _remove_row(self, row: int):
        if self._table and row < self._table.rowCount():
            self._table.removeRow(row)

    def _clear_list(self):
        if self._table:
            self._table.setRowCount(0)

    @staticmethod
    def _parse_pages(text: str, max_pages: int) -> list[int]:
        """Convert page range string into sorted list of page numbers."""
        if not text.strip():
            return list(range(1, max_pages + 1))
        pages: set[int] = set()
        for part in text.split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-", 1)
                pages.update(range(int(start), int(end) + 1))
            else:
                pages.add(int(part))
        return [p for p in sorted(pages) if 1 <= p <= max_pages]

    def _merge_pdfs(self):
        if not self._table or self._table.rowCount() == 0:
            QMessageBox.warning(
                self._table, "Warning", "No PDF files added."
            )
            return

        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            QMessageBox.critical(
                self._table, "Missing Dependency",
                "The 'pypdf' package is required.\n"
                "Install it with: pip install pypdf",
            )
            return

        writer = PdfWriter()
        for row in range(self._table.rowCount()):
            file = self._table.item(row, 0).text()
            page_input = self._table.cellWidget(row, 1).text()
            reader = PdfReader(file)
            try:
                selected = self._parse_pages(page_input, len(reader.pages))
                for p in selected:
                    writer.add_page(reader.pages[p - 1])
            except Exception as e:
                QMessageBox.critical(
                    self._table, "Error",
                    f"Invalid page selection in {Path(file).name}: {e}",
                )
                return

        save_path, _ = QFileDialog.getSaveFileName(
            self._table, "Save Merged PDF", "merged.pdf",
            "PDF Files (*.pdf)",
        )
        if save_path:
            with open(save_path, "wb") as f:
                writer.write(f)
            QMessageBox.information(
                self._table, "Success",
                f"Merged PDF saved at:\n{save_path}",
            )

    def on_data(self, key: str, value: Any) -> None:
        pass

    # ── WORKER side ──────────────────────────────────────────

    def start(self) -> None:
        super().start()
        # No background work — merging is user-triggered in the host process.
        # Keep the worker alive so the plugin stays in "running" state.
        import time
        while self.is_running:
            time.sleep(1)
