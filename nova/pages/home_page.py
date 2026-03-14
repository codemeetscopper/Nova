from __future__ import annotations

import math
import platform
import time

from PySide6.QtCore import QPointF, QRectF, Qt, Signal, QTimer, QSize
from PySide6.QtGui import (
    QColor, QLinearGradient, QPainter, QPainterPath, QPen, QBrush,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from nova.core.icons import IconManager
from nova.core.style import StyleManager

_LAUNCH_TIME = time.monotonic()

# ── Fixed palette for geometric shapes (colourful, not accent-only) ───────
_SHAPE_COLORS = [
    "#6366F1",  # indigo
    "#EC4899",  # pink
    "#14B8A6",  # teal
    "#F59E0B",  # amber
    "#3B82F6",  # blue
    "#22C55E",  # green
    "#EF4444",  # red
    "#8B5CF6",  # purple
    "#06B6D4",  # cyan
    "#F97316",  # orange
]


# =========================================================================
#  Painted viewport — all background graphics render here
# =========================================================================

class _PaintedViewport(QWidget):
    """Custom viewport for QScrollArea that paints geometric background."""

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if w < 10 or h < 10:
            p.end()
            return

        # Fill with bg colour first
        bg = QColor(StyleManager.get_colour("bg"))
        p.fillRect(0, 0, w, h, bg)

        accent = QColor(StyleManager.get_colour("accent"))
        self._draw_gradient_glow(p, w, h, accent)
        self._draw_dot_grid(p, w, h, accent)
        self._draw_colourful_shapes(p, w, h)
        self._draw_node_network(p, w, h, accent)
        self._draw_arc_rings(p, w, h, accent)
        self._draw_wave_curves(p, w, h, accent)

        p.end()

    # -- Gradient glow (accent tinted, very subtle) -------------------------

    @staticmethod
    def _draw_gradient_glow(p: QPainter, w: int, h: int, accent: QColor):
        # Top-right radial glow
        c = QColor(accent)
        c.setAlpha(20)
        rg = QRadialGradient(QPointF(w * 0.85, h * 0.05), max(w, h) * 0.6)
        rg.setColorAt(0.0, c)
        c0 = QColor(c); c0.setAlpha(0)
        rg.setColorAt(1.0, c0)
        p.fillRect(QRectF(0, 0, w, h), QBrush(rg))

        # Bottom-left radial glow
        c2 = QColor(accent); c2.setAlpha(12)
        rg2 = QRadialGradient(QPointF(w * 0.1, h * 0.9), max(w, h) * 0.5)
        rg2.setColorAt(0.0, c2)
        rg2.setColorAt(1.0, c0)
        p.fillRect(QRectF(0, 0, w, h), QBrush(rg2))

    # -- Dot grid -----------------------------------------------------------

    @staticmethod
    def _draw_dot_grid(p: QPainter, w: int, h: int, accent: QColor):
        c = QColor(accent); c.setAlpha(18)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        sp = 44
        x = 22
        while x < w:
            y = 22
            while y < h:
                p.drawEllipse(QPointF(x, y), 1.0, 1.0)
                y += sp
            x += sp

    # -- Colourful geometric shapes -----------------------------------------

    @staticmethod
    def _draw_colourful_shapes(p: QPainter, w: int, h: int):
        p.setBrush(Qt.NoBrush)
        s = min(w, h)

        shapes = [
            # (type, cx%, cy%, size_factor, color_idx, alpha, thickness, rotation)
            # Large shapes — very faint
            ("circle",  0.82, 0.10, 0.18, 4, 18, 1.4, 0),
            ("circle",  0.12, 0.80, 0.12, 2, 16, 1.2, 0),
            ("hex",     0.75, 0.50, 0.09, 0, 20, 1.2, -30),
            ("hex",     0.75, 0.50, 0.055, 0, 14, 0.8, 0),
            ("diamond", 0.20, 0.42, 0.06, 1, 18, 1.1, 45),
            ("tri",     0.40, 0.18, 0.045, 3, 16, 1.0, -90),
            ("square",  0.88, 0.68, 0.035, 7, 14, 0.9, 45),

            # Medium shapes
            ("circle",  0.50, 0.55, 0.15, 8, 10, 0.7, 0),
            ("hex",     0.30, 0.70, 0.05, 5, 16, 1.0, 0),
            ("tri",     0.65, 0.30, 0.035, 9, 14, 0.9, 30),
            ("diamond", 0.55, 0.82, 0.04, 6, 14, 0.9, 45),
            ("square",  0.10, 0.25, 0.025, 4, 12, 0.8, 15),

            # Small accents
            ("circle",  0.35, 0.38, 0.018, 1, 22, 1.4, 0),
            ("circle",  0.62, 0.65, 0.015, 5, 20, 1.2, 0),
            ("circle",  0.90, 0.35, 0.012, 3, 18, 1.0, 0),
            ("circle",  0.08, 0.60, 0.014, 8, 20, 1.2, 0),
            ("tri",     0.85, 0.85, 0.025, 2, 14, 0.8, 60),
            ("diamond", 0.45, 0.08, 0.02, 7, 16, 0.9, 45),
        ]

        for kind, cx_pct, cy_pct, size_f, ci, alpha, thick, rot in shapes:
            cx, cy = w * cx_pct, h * cy_pct
            r = s * size_f
            c = QColor(_SHAPE_COLORS[ci % len(_SHAPE_COLORS)])
            c.setAlpha(alpha)
            p.setPen(QPen(c, thick))

            if kind == "circle":
                p.drawEllipse(QPointF(cx, cy), r, r)
            elif kind == "hex":
                _draw_poly(p, cx, cy, r, 6, rot)
            elif kind == "tri":
                _draw_poly(p, cx, cy, r, 3, rot)
            elif kind == "diamond":
                _draw_poly(p, cx, cy, r, 4, rot)
            elif kind == "square":
                _draw_poly(p, cx, cy, r, 4, rot)

        # Filled soft circles (colourful blobs)
        blobs = [
            (0.78, 0.15, 0.04, 4, 10),
            (0.15, 0.75, 0.03, 1, 8),
            (0.55, 0.45, 0.025, 5, 6),
            (0.35, 0.60, 0.02, 9, 8),
            (0.92, 0.55, 0.018, 2, 8),
        ]
        for bx, by, bf, ci, alpha in blobs:
            c = QColor(_SHAPE_COLORS[ci % len(_SHAPE_COLORS)])
            c.setAlpha(alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(c))
            br = s * bf
            p.drawEllipse(QPointF(w * bx, h * by), br, br)

    # -- Node network -------------------------------------------------------

    @staticmethod
    def _draw_node_network(p: QPainter, w: int, h: int, accent: QColor):
        nodes = [
            (0.15, 0.15), (0.30, 0.08), (0.48, 0.12), (0.68, 0.06),
            (0.82, 0.20), (0.93, 0.12), (0.06, 0.42), (0.22, 0.35),
            (0.52, 0.40), (0.74, 0.33), (0.90, 0.45), (0.12, 0.70),
            (0.32, 0.62), (0.58, 0.68), (0.78, 0.60), (0.92, 0.72),
            (0.18, 0.90), (0.45, 0.88), (0.65, 0.92), (0.85, 0.85),
        ]
        pts = [(nx * w, ny * h) for nx, ny in nodes]

        edges = [
            (0,1),(1,2),(2,3),(3,4),(4,5),
            (6,7),(7,8),(8,9),(9,10),
            (11,12),(12,13),(13,14),(14,15),
            (16,17),(17,18),(18,19),
            (0,6),(1,7),(2,8),(3,9),(4,10),
            (6,11),(7,12),(8,13),(9,14),(10,15),
            (11,16),(12,17),(13,18),(14,19),
        ]

        lc = QColor(accent); lc.setAlpha(12)
        p.setPen(QPen(lc, 0.6))
        p.setBrush(Qt.NoBrush)
        for a, b in edges:
            p.drawLine(QPointF(*pts[a]), QPointF(*pts[b]))

        nc = QColor(accent); nc.setAlpha(24)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(nc))
        for x, y in pts:
            p.drawEllipse(QPointF(x, y), 2.2, 2.2)

        hc = QColor(accent); hc.setAlpha(18)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(hc, 0.8))
        for idx in (2, 8, 13, 5, 16):
            p.drawEllipse(QPointF(*pts[idx]), 7, 7)

    # -- Arc rings ----------------------------------------------------------

    @staticmethod
    def _draw_arc_rings(p: QPainter, w: int, h: int, accent: QColor):
        p.setBrush(Qt.NoBrush)
        for cx, cy, radii, start_deg, span in [
            (w*0.85, h*0.06, [90,150,220], 200, 80),
            (w*0.06, h*0.90, [70,120,180], 20, 80),
        ]:
            for i, r in enumerate(radii):
                c = QColor(accent); c.setAlpha(max(4, 16 - i*5))
                p.setPen(QPen(c, 0.8))
                p.drawArc(QRectF(cx-r, cy-r, r*2, r*2), start_deg*16, span*16)

    # -- Wave curves --------------------------------------------------------

    @staticmethod
    def _draw_wave_curves(p: QPainter, w: int, h: int, accent: QColor):
        p.setBrush(Qt.NoBrush)
        for i, (y_pct, alpha, thick) in enumerate([
            (0.76, 10, 0.9), (0.80, 7, 0.7), (0.84, 5, 0.5),
        ]):
            c = QColor(accent); c.setAlpha(alpha)
            p.setPen(QPen(c, thick))
            path = QPainterPath()
            path.moveTo(0, h * y_pct)
            sw = w / 4
            for s in range(4):
                x0 = s * sw
                cp1 = QPointF(x0 + sw*0.3, h*y_pct - 22 + i*10)
                cp2 = QPointF(x0 + sw*0.7, h*y_pct + 22 - i*10)
                path.cubicTo(cp1, cp2, QPointF(x0 + sw, h*y_pct))
            p.drawPath(path)


def _draw_poly(p: QPainter, cx: float, cy: float,
               r: float, sides: int, rot_deg: float = 0):
    pts = []
    for i in range(sides):
        a = math.radians(rot_deg + 360 / sides * i)
        pts.append(QPointF(cx + r * math.cos(a), cy + r * math.sin(a)))
    pts.append(pts[0])
    p.drawPolyline(pts)


# =========================================================================
#  Stat mini — compact stat block (value + label) used inside overview card
# =========================================================================

class _StatMini(QFrame):
    """Compact stat: big value on top, small uppercase label below."""
    clicked = Signal()

    def __init__(self, icon_name: str, title: str, value: str = "0",
                 clickable: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("StatMini")
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignCenter)

        self._icon_label = QLabel()
        self._icon_label.setObjectName("StatMiniIcon")
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setFixedSize(28, 28)
        self._icon_name = icon_name
        self._refresh_icon()
        lay.addWidget(self._icon_label, 0, Qt.AlignCenter)

        self._value_label = QLabel(value)
        self._value_label.setObjectName("StatMiniValue")
        self._value_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._value_label)

        self._title_label = QLabel(title.upper())
        self._title_label.setObjectName("StatMiniTitle")
        self._title_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._title_label)

    def set_value(self, v: str):
        self._value_label.setText(v)

    def _refresh_icon(self):
        accent = StyleManager.get_colour("accent")
        pm = IconManager.get_pixmap(self._icon_name, accent, 20)
        if pm:
            self._icon_label.setPixmap(pm)

    def refresh_theme(self):
        self._refresh_icon()

    def mousePressEvent(self, event):
        if self._clickable and event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# =========================================================================
#  Quick-action pill
# =========================================================================

class _QuickAction(QFrame):
    clicked = Signal()

    def __init__(self, icon_name: str, label: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("QuickAction")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)

        self._icon_label = QLabel()
        self._icon_label.setObjectName("QuickActionIcon")
        self._icon_label.setFixedSize(20, 20)
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_name = icon_name
        self._refresh_icon()
        lay.addWidget(self._icon_label)

        lbl = QLabel(label)
        lbl.setObjectName("QuickActionText")
        lay.addWidget(lbl, 1)

        arrow = QLabel("\u203a")
        arrow.setObjectName("QuickActionArrow")
        lay.addWidget(arrow)

    def _refresh_icon(self):
        fg1 = StyleManager.get_colour("fg1")
        pm = IconManager.get_pixmap(self._icon_name, fg1, 18)
        if pm:
            self._icon_label.setPixmap(pm)

    def refresh_theme(self):
        self._refresh_icon()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# =========================================================================
#  Info row
# =========================================================================

class _InfoRow(QFrame):
    def __init__(self, key: str, value: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("HomeInfoRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 3, 0, 3)
        lay.setSpacing(8)
        k = QLabel(key)
        k.setObjectName("HomeInfoKey")
        lay.addWidget(k)
        self._v = QLabel(value)
        self._v.setObjectName("HomeInfoValue")
        self._v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self._v)

    def set_value(self, v: str):
        self._v.setText(v)


# =========================================================================
#  Activity item
# =========================================================================

class _ActivityItem(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ActivityItem")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(10)
        self._dot = QLabel()
        self._dot.setFixedSize(6, 6)
        self._dot.setObjectName("ActivityDot")
        lay.addWidget(self._dot, 0, Qt.AlignVCenter)
        self._text = QLabel()
        self._text.setObjectName("ActivityText")
        self._text.setWordWrap(True)
        lay.addWidget(self._text, 1)
        self._time = QLabel()
        self._time.setObjectName("ActivityTime")
        self._time.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self._time)

    def set_data(self, text: str, ts: str, color: str = "#888"):
        self._text.setText(text)
        self._time.setText(ts)
        self._dot.setStyleSheet(
            f"background:{color};border-radius:3px;border:none;")


# =========================================================================
#  Section label
# =========================================================================

class _SectionLabel(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text.upper(), parent)
        self.setObjectName("DashSectionLabel")


# =========================================================================
#  Home Page
# =========================================================================

class HomePage(QWidget):
    navigate_to = Signal(str)

    def __init__(self, ctx, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx = ctx
        self._pm = None
        self._activity_items: list[_ActivityItem] = []
        self._activity_log: list[tuple[str, str, str]] = []
        self.setObjectName("HomePage")

        # Scroll with painted viewport
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("HomeScroll")

        self._viewport = _PaintedViewport()
        scroll.setViewport(self._viewport)

        container = QWidget()
        container.setObjectName("HomeContainer")
        root = QVBoxLayout(container)
        root.setContentsMargins(36, 28, 36, 28)
        root.setSpacing(20)

        # ── Hero ──────────────────────────────────────────────
        hero = QWidget()
        hero.setObjectName("HomeHero")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        greeting = QLabel("Welcome to Nova")
        greeting.setObjectName("HomeGreeting")
        hl.addWidget(greeting)
        subtitle = QLabel(
            "Plugin-driven application platform  \u2014  Dashboard overview")
        subtitle.setObjectName("HomeSubtitle")
        hl.addWidget(subtitle)
        root.addWidget(hero)

        # ── Plugin Overview — single unified card ─────────────
        root.addWidget(_SectionLabel("Plugin Overview"))

        overview_card = QFrame()
        overview_card.setObjectName("DashPanel")
        overview_card.setFrameShape(QFrame.NoFrame)
        overview_card.setCursor(Qt.PointingHandCursor)
        ov_lay = QVBoxLayout(overview_card)
        ov_lay.setContentsMargins(6, 14, 6, 14)
        ov_lay.setSpacing(0)

        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(0)

        self._st_loaded = _StatMini("extension", "Loaded", "0", clickable=True)
        self._st_loaded.clicked.connect(lambda: self.navigate_to.emit("plugins"))
        self._st_running = _StatMini("play", "Running", "0", clickable=True)
        self._st_running.clicked.connect(lambda: self.navigate_to.emit("plugins"))
        self._st_stopped = _StatMini("stop", "Stopped", "0", clickable=True)
        self._st_stopped.clicked.connect(lambda: self.navigate_to.emit("plugins"))
        self._st_favorites = _StatMini("favorite", "Favorites", "0", clickable=True)
        self._st_favorites.clicked.connect(lambda: self.navigate_to.emit("plugins"))
        self._st_categories = _StatMini("folder", "Categories", "0", clickable=True)
        self._st_categories.clicked.connect(lambda: self.navigate_to.emit("plugins"))
        self._st_status = _StatMini("info", "Status", "Idle")
        self._st_uptime = _StatMini("refresh", "Uptime", "0s")

        for w in (self._st_loaded, self._st_running, self._st_stopped,
                  self._st_favorites, self._st_categories,
                  self._st_status, self._st_uptime):
            stats_row.addWidget(w, 1)

        ov_lay.addLayout(stats_row)
        root.addWidget(overview_card)

        # ── Bottom 3-column panels ────────────────────────────
        bottom = QWidget()
        bottom.setObjectName("HomeBottomRow")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(14)

        # -- Quick Actions --
        qa_card = QFrame()
        qa_card.setObjectName("DashPanel")
        qa_card.setFrameShape(QFrame.NoFrame)
        qa_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        qa_v = QVBoxLayout(qa_card)
        qa_v.setContentsMargins(18, 16, 18, 16)
        qa_v.setSpacing(8)
        qa_v.addWidget(_SectionLabel("Quick Actions"))
        qa_v.addSpacing(4)

        self._qa_plugins = _QuickAction("extension", "Browse Plugins")
        self._qa_plugins.clicked.connect(lambda: self.navigate_to.emit("plugins"))
        qa_v.addWidget(self._qa_plugins)
        self._qa_settings = _QuickAction("settings", "Open Settings")
        self._qa_settings.clicked.connect(lambda: self.navigate_to.emit("settings"))
        qa_v.addWidget(self._qa_settings)
        self._qa_logs = _QuickAction("file", "View Logs")
        self._qa_logs.clicked.connect(lambda: self.navigate_to.emit("logs"))
        qa_v.addWidget(self._qa_logs)
        self._qa_about = _QuickAction("info", "About Nova")
        self._qa_about.clicked.connect(lambda: self.navigate_to.emit("about"))
        qa_v.addWidget(self._qa_about)
        qa_v.addStretch()
        bl.addWidget(qa_card)

        # -- Recent Activity --
        act_card = QFrame()
        act_card.setObjectName("DashPanel")
        act_card.setFrameShape(QFrame.NoFrame)
        act_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        act_v = QVBoxLayout(act_card)
        act_v.setContentsMargins(18, 16, 18, 16)
        act_v.setSpacing(6)
        act_v.addWidget(_SectionLabel("Recent Activity"))
        act_v.addSpacing(4)

        self._activity_container = QVBoxLayout()
        self._activity_container.setContentsMargins(0, 0, 0, 0)
        self._activity_container.setSpacing(2)
        for _ in range(5):
            item = _ActivityItem()
            item.hide()
            self._activity_items.append(item)
            self._activity_container.addWidget(item)
        act_v.addLayout(self._activity_container)

        self._no_activity = QLabel("No activity yet")
        self._no_activity.setObjectName("HomeInfoKey")
        self._no_activity.setAlignment(Qt.AlignCenter)
        act_v.addWidget(self._no_activity)
        act_v.addStretch()
        bl.addWidget(act_card)

        # -- System Info --
        sys_card = QFrame()
        sys_card.setObjectName("DashPanel")
        sys_card.setFrameShape(QFrame.NoFrame)
        sys_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sys_v = QVBoxLayout(sys_card)
        sys_v.setContentsMargins(18, 16, 18, 16)
        sys_v.setSpacing(4)
        sys_v.addWidget(_SectionLabel("System"))
        sys_v.addSpacing(4)

        sys_v.addWidget(_InfoRow("Platform",
                                  f"{platform.system()} {platform.release()}"))
        sys_v.addWidget(_InfoRow("Architecture", platform.machine()))
        sys_v.addWidget(_InfoRow("Python", platform.python_version()))
        try:
            from PySide6 import __version__ as pv
        except ImportError:
            pv = "?"
        sys_v.addWidget(_InfoRow("PySide6", pv))

        sep = QFrame(); sep.setObjectName("DashPanelSep"); sep.setFixedHeight(1)
        sys_v.addSpacing(6); sys_v.addWidget(sep); sys_v.addSpacing(6)

        sys_v.addWidget(_SectionLabel("Plugin Runtime"))
        sys_v.addSpacing(4)
        sys_v.addWidget(_InfoRow("IPC", "Local Socket"))
        sys_v.addWidget(_InfoRow("Isolation", "Process"))
        self._info_plugin_dir = _InfoRow("Plugin Dir", "\u2014")
        sys_v.addWidget(self._info_plugin_dir)
        sys_v.addStretch()
        bl.addWidget(sys_card)

        root.addWidget(bottom, 1)
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Uptime timer
        self._uptime_timer = QTimer(self)
        self._uptime_timer.timeout.connect(self._update_uptime)
        self._uptime_timer.start(1000)

    # ── Public API ──────────────────────────────────────────

    def set_plugin_manager(self, pm):
        self._pm = pm
        if pm and hasattr(pm, '_plugins_dir'):
            d = str(pm._plugins_dir)
            if len(d) > 30:
                d = "..." + d[-27:]
            self._info_plugin_dir.set_value(d)

    def update_stats(self, loaded: int, active: int):
        stopped = max(0, loaded - active)
        self._st_loaded.set_value(str(loaded))
        self._st_running.set_value(str(active))
        self._st_stopped.set_value(str(stopped))

        if active > 0:
            self._st_status.set_value("Running")
        elif loaded > 0:
            self._st_status.set_value("Ready")
        else:
            self._st_status.set_value("Idle")

        if self._pm:
            favs = sum(1 for r in self._pm._records.values()
                       if self._pm.is_favorite(r.manifest.id))
            cats = len({r.manifest.category
                        for r in self._pm._records.values()})
            self._st_favorites.set_value(str(favs))
            self._st_categories.set_value(str(cats))

    def log_activity(self, text: str, color: str = "#888"):
        secs = int(time.monotonic() - _LAUNCH_TIME)
        if secs < 60:
            ts = f"{secs}s ago"
        elif secs < 3600:
            ts = f"{secs // 60}m ago"
        else:
            ts = f"{secs // 3600}h ago"
        self._activity_log.insert(0, (text, ts, color))
        self._activity_log = self._activity_log[:5]
        self._refresh_activity()

    def refresh_icons(self):
        for st in (self._st_loaded, self._st_running, self._st_stopped,
                   self._st_favorites, self._st_categories,
                   self._st_status, self._st_uptime):
            st.refresh_theme()
        for qa in (self._qa_plugins, self._qa_settings,
                   self._qa_logs, self._qa_about):
            qa.refresh_theme()
        self._viewport.update()

    # ── Internal ─────────────────────────────────────────────

    def _refresh_activity(self):
        has = len(self._activity_log) > 0
        self._no_activity.setVisible(not has)
        for i, item in enumerate(self._activity_items):
            if i < len(self._activity_log):
                text, ts, color = self._activity_log[i]
                item.set_data(text, ts, color)
                item.show()
            else:
                item.hide()

    def _update_uptime(self):
        secs = int(time.monotonic() - _LAUNCH_TIME)
        if secs < 60:
            txt = f"{secs}s"
        elif secs < 3600:
            txt = f"{secs // 60}m {secs % 60}s"
        else:
            h = secs // 3600
            m = (secs % 3600) // 60
            txt = f"{h}h {m}m"
        self._st_uptime.set_value(txt)
