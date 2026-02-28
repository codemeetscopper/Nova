"""
PDF Merger Plugin
=================
Host side: UI with table for adding PDFs, page selection, reordering, and merge.
Worker side: idle (no background work needed — merging is triggered on demand).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
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

        # Title
        title = QLabel("PDF Merger")
        title.setObjectName("SysMonTitle")
        v.addWidget(title)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        btn_add = QPushButton("Add PDFs")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self._load_pdfs)
        toolbar.addWidget(btn_add)

        btn_clear = QPushButton("Clear")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self._clear_list)
        toolbar.addWidget(btn_clear)

        toolbar.addSpacing(4)

        btn_up = QPushButton("Move Up")
        btn_up.setCursor(Qt.PointingHandCursor)
        btn_up.clicked.connect(self._move_up)
        toolbar.addWidget(btn_up)

        btn_down = QPushButton("Move Down")
        btn_down.setCursor(Qt.PointingHandCursor)
        btn_down.clicked.connect(self._move_down)
        toolbar.addWidget(btn_down)

        toolbar.addStretch()

        btn_merge = QPushButton("Merge PDFs")
        btn_merge.setObjectName("PdfMergerMerge")
        btn_merge.setCursor(Qt.PointingHandCursor)
        btn_merge.clicked.connect(self._merge_pdfs)
        toolbar.addWidget(btn_merge)

        v.addLayout(toolbar)

        # Table
        self._table = QTableWidget(0, 3)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setHorizontalHeaderLabels(
            ["PDF File", "Pages (e.g. 1-3,5)", ""]
        )
        self._table.horizontalHeader().setStretchLastSection(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(1, 200)
        self._table.setColumnWidth(2, 80)
        self._table.verticalHeader().setVisible(False)
        v.addWidget(self._table)

        scroll.setWidget(content)
        outer.addWidget(scroll)

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
            self._add_row(file, f"1-{len(reader.pages)} or leave empty = all")

    def _add_row(self, filepath: str, placeholder: str, pages_text: str = ""):
        row = self._table.rowCount()
        self._table.insertRow(row)

        item = QTableWidgetItem(Path(filepath).name)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        item.setToolTip(filepath)
        item.setData(Qt.UserRole, filepath)
        self._table.setItem(row, 0, item)

        page_input = QLineEdit()
        page_input.setPlaceholderText(placeholder)
        if pages_text:
            page_input.setText(pages_text)
        self._table.setCellWidget(row, 1, page_input)

        btn_remove = QPushButton("Remove")
        btn_remove.setCursor(Qt.PointingHandCursor)
        btn_remove.clicked.connect(lambda: self._remove_current(btn_remove))
        self._table.setCellWidget(row, 2, btn_remove)

    def _remove_current(self, btn: QPushButton):
        if not self._table:
            return
        for r in range(self._table.rowCount()):
            if self._table.cellWidget(r, 2) is btn:
                self._table.removeRow(r)
                return

    def _clear_list(self):
        if self._table:
            self._table.setRowCount(0)

    def _swap_rows(self, row_a: int, row_b: int):
        if not self._table:
            return

        # Read data from both rows
        item_a = self._table.item(row_a, 0)
        item_b = self._table.item(row_b, 0)
        name_a, tip_a, data_a = item_a.text(), item_a.toolTip(), item_a.data(Qt.UserRole)
        name_b, tip_b, data_b = item_b.text(), item_b.toolTip(), item_b.data(Qt.UserRole)

        widget_a = self._table.cellWidget(row_a, 1)
        widget_b = self._table.cellWidget(row_b, 1)
        text_a = widget_a.text() if widget_a else ""
        text_b = widget_b.text() if widget_b else ""
        ph_a = widget_a.placeholderText() if widget_a else ""
        ph_b = widget_b.placeholderText() if widget_b else ""

        # Swap file path items
        item_a.setText(name_b)
        item_a.setToolTip(tip_b)
        item_a.setData(Qt.UserRole, data_b)
        item_b.setText(name_a)
        item_b.setToolTip(tip_a)
        item_b.setData(Qt.UserRole, data_a)

        # Recreate page input widgets with swapped data
        new_a = QLineEdit()
        new_a.setPlaceholderText(ph_b)
        if text_b:
            new_a.setText(text_b)
        self._table.setCellWidget(row_a, 1, new_a)

        new_b = QLineEdit()
        new_b.setPlaceholderText(ph_a)
        if text_a:
            new_b.setText(text_a)
        self._table.setCellWidget(row_b, 1, new_b)

    def _move_up(self):
        if not self._table:
            return
        row = self._table.currentRow()
        if row <= 0:
            return
        self._swap_rows(row, row - 1)
        self._table.selectRow(row - 1)

    def _move_down(self):
        if not self._table:
            return
        row = self._table.currentRow()
        if row < 0 or row >= self._table.rowCount() - 1:
            return
        self._swap_rows(row, row + 1)
        self._table.selectRow(row + 1)

    @staticmethod
    def _parse_pages(text: str, max_pages: int) -> list[int]:
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
            file = self._table.item(row, 0).data(Qt.UserRole)
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
        import time
        while self.is_running:
            time.sleep(1)
