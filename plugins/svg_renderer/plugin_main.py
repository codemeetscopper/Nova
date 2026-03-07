"""
SVG Renderer Plugin
====================
Worker side: no-op (keeps alive).
Host side:   SVG code editor on the left, live rendered preview on the right.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QFrame, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from nova.core.plugin_base import PluginBase


_DEFAULT_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0088CC"/>
      <stop offset="100%" stop-color="#00CCAA"/>
    </linearGradient>
  </defs>
  <rect rx="24" width="200" height="200" fill="url(#grad)"/>
  <circle cx="100" cy="80" r="30" fill="white" fill-opacity="0.9"/>
  <rect x="60" y="120" width="80" height="40" rx="8"
        fill="white" fill-opacity="0.7"/>
  <text x="100" y="146" text-anchor="middle"
        font-size="16" font-weight="bold" fill="#0088CC">
    SVG
  </text>
</svg>"""


_COMMON_SNIPPETS = {
    "Rectangle": '<rect x="10" y="10" width="80" height="60" rx="8" fill="#0088CC"/>',
    "Circle": '<circle cx="100" cy="100" r="50" fill="#00CC88"/>',
    "Ellipse": '<ellipse cx="100" cy="100" rx="80" ry="50" fill="#CC8800"/>',
    "Line": '<line x1="10" y1="10" x2="190" y2="190" stroke="#CC0044" stroke-width="3"/>',
    "Polyline": '<polyline points="20,80 60,20 100,80 140,20 180,80" fill="none" stroke="#0088CC" stroke-width="2"/>',
    "Polygon": '<polygon points="100,10 40,198 190,78 10,78 160,198" fill="#0088CC" fill-opacity="0.6" stroke="#0088CC" stroke-width="2"/>',
    "Path": '<path d="M10 80 C 40 10, 65 10, 95 80 S 150 150, 180 80" fill="none" stroke="#CC0088" stroke-width="3"/>',
    "Text": '<text x="100" y="100" text-anchor="middle" font-size="24" fill="#333">Hello SVG</text>',
    "Linear Gradient": (
        '<defs>\n'
        '  <linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="0%">\n'
        '    <stop offset="0%" stop-color="#0088CC"/>\n'
        '    <stop offset="100%" stop-color="#CC0088"/>\n'
        '  </linearGradient>\n'
        '</defs>\n'
        '<rect width="200" height="200" fill="url(#g1)"/>'
    ),
}


class Plugin(PluginBase):

    def __init__(self, bridge):
        super().__init__(bridge)
        self._editor: QPlainTextEdit | None = None
        self._preview_label: QLabel | None = None
        self._error_label: QLabel | None = None
        self._render_timer: QTimer | None = None
        self._render_size = 256
        self._bg_color = "#1e1e2e"

    # ── HOST side ─────────────────────────────────────────────

    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        frame = QFrame(parent)
        frame.setObjectName("SVGRendererFrame")

        splitter = QSplitter(Qt.Horizontal, frame)
        splitter.setHandleWidth(1)

        # ── Left: SVG editor ──────────────────────────────────
        editor_pane = QWidget()
        ev = QVBoxLayout(editor_pane)
        ev.setContentsMargins(0, 0, 0, 0)
        ev.setSpacing(4)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 0)
        toolbar.setSpacing(4)

        # Snippet insert
        snippet_cb = QComboBox()
        snippet_cb.addItem("Insert snippet...")
        snippet_cb.addItems(list(_COMMON_SNIPPETS.keys()))
        snippet_cb.currentTextChanged.connect(self._on_snippet)
        toolbar.addWidget(snippet_cb)

        toolbar.addStretch()

        # Render size
        size_lbl = QLabel("Size:")
        toolbar.addWidget(size_lbl)
        size_spin = QSpinBox()
        size_spin.setRange(32, 2048)
        size_spin.setSingleStep(64)
        size_spin.setValue(self._render_size)
        size_spin.valueChanged.connect(self._on_size_changed)
        toolbar.addWidget(size_spin)

        # Background color
        bg_btn = QPushButton("BG")
        bg_btn.setToolTip("Preview background color")
        bg_btn.setFixedWidth(40)
        bg_btn.clicked.connect(self._pick_bg_color)
        toolbar.addWidget(bg_btn)

        ev.addLayout(toolbar)

        self._editor = QPlainTextEdit()
        self._editor.setObjectName("SVGEditor")
        self._editor.setPlaceholderText("Paste SVG code here...")
        self._editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._editor.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px;"
        )
        self._editor.setPlainText(_DEFAULT_SVG)
        ev.addWidget(self._editor, 1)

        # Error label
        self._error_label = QLabel()
        self._error_label.setObjectName("SVGErrorLabel")
        self._error_label.setStyleSheet(
            "color: #ff6b6b; font-size: 11px; padding: 2px 4px;"
        )
        self._error_label.hide()
        ev.addWidget(self._error_label)

        splitter.addWidget(editor_pane)

        # ── Right: preview ────────────────────────────────────
        preview_pane = QWidget()
        pv = QVBoxLayout(preview_pane)
        pv.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignCenter)
        scroll.setFrameShape(QFrame.NoFrame)

        self._preview_label = QLabel()
        self._preview_label.setObjectName("SVGPreviewLabel")
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._preview_label.setMinimumSize(200, 200)
        scroll.setWidget(self._preview_label)

        pv.addWidget(scroll, 1)
        splitter.addWidget(preview_pane)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        root = QVBoxLayout(frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)

        # Debounced rendering
        self._render_timer = QTimer()
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(300)
        self._render_timer.timeout.connect(self._render_svg)
        self._editor.textChanged.connect(self._render_timer.start)

        # Initial render
        QTimer.singleShot(100, self._render_svg)

        return frame

    def _render_svg(self):
        if self._editor is None or self._preview_label is None:
            return

        svg_text = self._editor.toPlainText().strip()
        if not svg_text:
            self._preview_label.clear()
            self._error_label.hide()
            return

        svg_bytes = svg_text.encode("utf-8")
        renderer = QSvgRenderer(svg_bytes)

        if not renderer.isValid():
            self._error_label.setText("Invalid SVG — check syntax")
            self._error_label.show()
            return

        self._error_label.hide()
        size = self._render_size
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(self._bg_color))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter)
        painter.end()

        self._preview_label.setPixmap(pixmap)

    def _on_snippet(self, text: str):
        if text in _COMMON_SNIPPETS and self._editor:
            cursor = self._editor.textCursor()
            cursor.insertText("\n" + _COMMON_SNIPPETS[text] + "\n")
            self._editor.setTextCursor(cursor)
            # Reset combo
            cb = self._editor.parent().findChild(QComboBox)
            if cb:
                cb.setCurrentIndex(0)

    def _on_size_changed(self, value: int):
        self._render_size = value
        self._render_svg()

    def _pick_bg_color(self):
        color = QColorDialog.getColor(
            QColor(self._bg_color), None, "Preview Background"
        )
        if color.isValid():
            self._bg_color = color.name()
            self._render_svg()

    # ── WORKER side ───────────────────────────────────────────

    def start(self) -> None:
        super().start()
        while self.is_running:
            self.send_data("heartbeat", "alive")
            time.sleep(5)
