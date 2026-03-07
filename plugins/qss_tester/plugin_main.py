"""
QSS Tester Plugin
==================
Worker side: no-op (keeps alive).
Host side:   QSS editor on the left, live preview of default Qt controls on the right.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QProgressBar, QPushButton, QRadioButton, QScrollArea,
    QSizePolicy, QSlider, QSpinBox, QSplitter, QTabWidget,
    QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from nova.core.plugin_base import PluginBase


_DEFAULT_QSS = """\
/* Try editing this QSS — the preview updates live! */

QPushButton {
    background: #0088CC;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
}
QPushButton:hover {
    background: #006DAA;
}
QPushButton:pressed {
    background: #005588;
}

QLineEdit, QSpinBox, QComboBox {
    background: #1e1e2e;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
}

QSlider::groove:horizontal {
    height: 4px;
    background: #45475a;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 14px; height: 14px;
    margin: -5px 0;
    background: #0088CC;
    border-radius: 7px;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 16px; height: 16px;
}

QProgressBar {
    background: #313244;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: white;
}
QProgressBar::chunk {
    background: #0088CC;
    border-radius: 4px;
}

QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
}

QTabWidget::pane {
    border: 1px solid #45475a;
    border-radius: 4px;
}
QTabBar::tab {
    background: #1e1e2e;
    color: #cdd6f4;
    padding: 6px 16px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #0088CC;
    color: white;
}
"""


class Plugin(PluginBase):

    def __init__(self, bridge):
        super().__init__(bridge)
        self._editor: QTextEdit | None = None
        self._preview_root: QWidget | None = None
        self._apply_timer: QTimer | None = None

    # ── HOST side ─────────────────────────────────────────────

    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        frame = QFrame(parent)
        frame.setObjectName("QSSTesterFrame")

        splitter = QSplitter(Qt.Horizontal, frame)
        splitter.setHandleWidth(1)

        # ── Left: QSS editor ──────────────────────────────────
        editor_pane = QWidget()
        ev = QVBoxLayout(editor_pane)
        ev.setContentsMargins(0, 0, 0, 0)
        ev.setSpacing(4)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 0)
        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("QSSTesterApply")
        apply_btn.clicked.connect(self._apply_qss)
        reset_btn = QPushButton("Reset")
        reset_btn.setObjectName("QSSTesterReset")
        reset_btn.clicked.connect(self._reset_qss)
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("QSSTesterClear")
        clear_btn.clicked.connect(self._clear_qss)
        toolbar.addWidget(apply_btn)
        toolbar.addWidget(reset_btn)
        toolbar.addWidget(clear_btn)
        toolbar.addStretch()
        ev.addLayout(toolbar)

        self._editor = QTextEdit()
        self._editor.setObjectName("QSSTesterEditor")
        self._editor.setPlaceholderText("Enter QSS stylesheet here...")
        self._editor.setAcceptRichText(False)
        self._editor.setLineWrapMode(QTextEdit.NoWrap)
        self._editor.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px;"
        )
        self._editor.setPlainText(_DEFAULT_QSS)
        ev.addWidget(self._editor, 1)

        # Debounced live preview
        self._apply_timer = QTimer()
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(400)
        self._apply_timer.timeout.connect(self._apply_qss)
        self._editor.textChanged.connect(self._apply_timer.start)

        splitter.addWidget(editor_pane)

        # ── Right: preview controls ───────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        self._preview_root = QWidget()
        self._preview_root.setObjectName("QSSTesterPreview")
        pv = QVBoxLayout(self._preview_root)
        pv.setContentsMargins(12, 12, 12, 12)
        pv.setSpacing(12)

        self._build_preview_controls(pv)

        scroll.setWidget(self._preview_root)
        splitter.addWidget(scroll)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        root = QVBoxLayout(frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)

        # Apply default QSS
        QTimer.singleShot(100, self._apply_qss)

        return frame

    def _build_preview_controls(self, layout: QVBoxLayout):
        # Buttons
        g1 = QGroupBox("Buttons")
        g1v = QVBoxLayout(g1)
        row1 = QHBoxLayout()
        for text in ("Primary", "Secondary", "Disabled"):
            btn = QPushButton(text)
            if text == "Disabled":
                btn.setEnabled(False)
            row1.addWidget(btn)
        g1v.addLayout(row1)
        row2 = QHBoxLayout()
        tb = QToolButton()
        tb.setText("Tool")
        row2.addWidget(tb)
        flat = QPushButton("Flat")
        flat.setFlat(True)
        row2.addWidget(flat)
        row2.addStretch()
        g1v.addLayout(row2)
        layout.addWidget(g1)

        # Inputs
        g2 = QGroupBox("Inputs")
        g2v = QVBoxLayout(g2)
        le = QLineEdit()
        le.setPlaceholderText("QLineEdit placeholder...")
        g2v.addWidget(le)
        h = QHBoxLayout()
        sp = QSpinBox()
        sp.setRange(0, 100)
        sp.setValue(42)
        h.addWidget(sp)
        cb = QComboBox()
        cb.addItems(["Option A", "Option B", "Option C"])
        h.addWidget(cb)
        g2v.addLayout(h)
        layout.addWidget(g2)

        # Checkboxes and radios
        g3 = QGroupBox("Toggles")
        g3v = QVBoxLayout(g3)
        ch = QHBoxLayout()
        c1 = QCheckBox("Checked")
        c1.setChecked(True)
        c2 = QCheckBox("Unchecked")
        c3 = QCheckBox("Disabled")
        c3.setEnabled(False)
        ch.addWidget(c1)
        ch.addWidget(c2)
        ch.addWidget(c3)
        g3v.addLayout(ch)
        rh = QHBoxLayout()
        r1 = QRadioButton("Radio A")
        r1.setChecked(True)
        r2 = QRadioButton("Radio B")
        rh.addWidget(r1)
        rh.addWidget(r2)
        g3v.addLayout(rh)
        layout.addWidget(g3)

        # Sliders and progress
        g4 = QGroupBox("Sliders & Progress")
        g4v = QVBoxLayout(g4)
        sl = QSlider(Qt.Horizontal)
        sl.setRange(0, 100)
        sl.setValue(65)
        g4v.addWidget(sl)
        pb = QProgressBar()
        pb.setRange(0, 100)
        pb.setValue(65)
        g4v.addWidget(pb)
        layout.addWidget(g4)

        # Tabs
        g5 = QGroupBox("Tabs")
        g5v = QVBoxLayout(g5)
        tabs = QTabWidget()
        t1 = QLabel("Content of Tab 1")
        t1.setAlignment(Qt.AlignCenter)
        t1.setMinimumHeight(40)
        tabs.addTab(t1, "Tab 1")
        t2 = QLabel("Content of Tab 2")
        t2.setAlignment(Qt.AlignCenter)
        tabs.addTab(t2, "Tab 2")
        t3 = QLabel("Content of Tab 3")
        t3.setAlignment(Qt.AlignCenter)
        tabs.addTab(t3, "Tab 3")
        g5v.addWidget(tabs)
        layout.addWidget(g5)

        # Text
        g6 = QGroupBox("Text")
        g6v = QVBoxLayout(g6)
        te = QTextEdit()
        te.setPlaceholderText("QTextEdit — multiline input...")
        te.setMaximumHeight(80)
        g6v.addWidget(te)
        layout.addWidget(g6)

        layout.addStretch()

    def _apply_qss(self):
        if self._editor is None or self._preview_root is None:
            return
        qss = self._editor.toPlainText()
        self._preview_root.setStyleSheet(qss)

    def _reset_qss(self):
        if self._editor:
            self._editor.setPlainText(_DEFAULT_QSS)

    def _clear_qss(self):
        if self._editor:
            self._editor.clear()
        if self._preview_root:
            self._preview_root.setStyleSheet("")

    # ── WORKER side ───────────────────────────────────────────

    def start(self) -> None:
        super().start()
        while self.is_running:
            self.send_data("heartbeat", "alive")
            time.sleep(5)
