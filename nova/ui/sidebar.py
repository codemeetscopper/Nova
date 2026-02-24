from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

EXPANDED = 240
COLLAPSED = 64
ANIM_MS = 200

# Horizontal padding so nav icon centres align with the hamburger icon centre.
# hamburger: 28px button at left=18  → centre at 32px from sidebar edge
# nav icon : 20px label  at left=18+4(container)=22 → centre at 32px  ✓
_COLLAPSED_PAD = (COLLAPSED - 28) // 2   # 18 — header hamburger left pad
_NAV_LEFT_PAD  = _COLLAPSED_PAD          # 18 — nav items, same centre as hamburger


def _accent_color() -> str:
    try:
        from nova.core.style import StyleManager
        return StyleManager.get_colour("accent")
    except Exception:
        return "#0088CC"


def _fg1_color() -> str:
    try:
        from nova.core.style import StyleManager
        return StyleManager.get_colour("fg1")
    except Exception:
        return "#444444"


def _get_icon_pixmap(icon_name: str, color: str, size: int = 20) -> Optional[QPixmap]:
    try:
        from nova.core.icons import IconManager
        return IconManager.get_pixmap(icon_name, color, size)
    except Exception:
        return None


class SidebarItem(QWidget):
    """A single navigation row — icon + optional label."""

    clicked = Signal(str)   # item id

    def __init__(self, item_id: str, label: str, icon_name: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._id = item_id
        self._label_text = label
        self._icon_name = icon_name
        self._active = False

        self.setObjectName("SidebarItem")
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(_NAV_LEFT_PAD, 0, 12, 0)
        self._layout.setSpacing(16)

        # Icon — pixmap if IconManager has it, otherwise plain text
        self._icon = QLabel()
        self._icon.setObjectName("SidebarItemIcon")
        self._icon.setFixedSize(20, 20)
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setScaledContents(True)

        self._text = QLabel(label)
        self._text.setObjectName("SidebarItemText")
        self._text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._text.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self._layout.addWidget(self._icon)
        self._layout.addWidget(self._text)

        self._apply_inactive_style()

    # ──────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────

    def set_text_visible(self, visible: bool):
        self._text.setVisible(visible)
        if visible:
            self._layout.setContentsMargins(_NAV_LEFT_PAD, 0, 3, 0)
            self.setToolTip("")
        else:
            self._layout.setContentsMargins(_NAV_LEFT_PAD, 0, _NAV_LEFT_PAD, 0)
            self.setToolTip(self._label_text)

    def set_active(self, active: bool):
        if self._active == active:
            return
        self._active = active
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)
        if active:
            self._apply_active_style()
        else:
            self._apply_inactive_style()
        self.update()

    def refresh_style(self):
        """Re-apply current active/inactive colours (called after theme change)."""
        if self._active:
            self._apply_active_style()
        else:
            self._apply_inactive_style()

    def is_active(self) -> bool:
        return self._active

    # ──────────────────────────────────────────────────────
    #  Internal
    # ──────────────────────────────────────────────────────

    def _set_icon_pixmap(self, color: str):
        """Set the icon QLabel pixmap with the requested colour."""
        clean_name = self._icon_name.strip()
        if clean_name.startswith("<") and "svg" in clean_name:
            try:
                from nova.core.icons import IconManager
                px = IconManager.render_svg_string(clean_name, color, 20)
                if px and not px.isNull():
                    self._icon.setPixmap(px)
                    self._icon.setStyleSheet("background: transparent;")
                    return
            except Exception:
                pass

        px = _get_icon_pixmap(self._icon_name, color)
        if px is not None and not px.isNull():
            self._icon.setPixmap(px)
            self._icon.setStyleSheet("background: transparent;")
        else:
            short = self._icon_name if len(self._icon_name) < 20 else "?"
            self._icon.setText(short)
            self._icon.setStyleSheet(f"color: {color}; background: transparent;")

    def _apply_active_style(self):
        ac = _accent_color()
        self._set_icon_pixmap(ac)
        self._text.setStyleSheet(
            f"color: {ac}; font-weight: 600; background: transparent;"
        )

    def _apply_inactive_style(self):
        fg = _fg1_color()
        self._set_icon_pixmap(fg)
        self._text.setStyleSheet(f"color: {fg}; background: transparent;")

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit(self._id)


class SidebarSeparator(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SidebarSeparator")
        self.setFrameShape(QFrame.HLine)
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class Sidebar(QFrame):
    """
    Collapsible hamburger sidebar.

    Layout (top-to-bottom in nav area):
      [standard items]
      [plugin items]  ← inserted before separator
      [separator]
      [settings / about items]
      [stretch]

    Signals:
        item_clicked(str)   emitted with the page id when a nav item is clicked
    """

    item_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self._expanded = True
        self._items: Dict[str, SidebarItem] = {}
        self._separator: Optional[SidebarSeparator] = None

        self.setMinimumWidth(EXPANDED)
        self.setMaximumWidth(EXPANDED)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──────────────────────────────────────────
        header = QWidget()
        header.setObjectName("SidebarHeader")
        header.setFixedHeight(56)
        h_layout = QHBoxLayout(header)
        # 18px left — icon LEFT EDGE aligns with nav item icons (_COLLAPSED_PAD = 18)
        h_layout.setContentsMargins(_COLLAPSED_PAD, 0, 2, 0)
        h_layout.setSpacing(8)

        # 28×28 button — icon fills button exactly, aligning with 28px nav icons
        self._hamburger = QPushButton()
        self._hamburger.setObjectName("HamburgerButton")
        self._hamburger.setFixedSize(28, 28)
        self._hamburger.setCursor(Qt.PointingHandCursor)
        self._hamburger.clicked.connect(self.toggle)
        self._set_hamburger_icon()

        self._logo = QLabel("Nova")
        self._logo.setObjectName("SidebarLogo")

        h_layout.addWidget(self._hamburger)
        h_layout.addWidget(self._logo)
        h_layout.addStretch()
        root.addWidget(header)

        # ── Scroll area ──────────────────────────────────────
        scroll = QScrollArea()
        scroll.setObjectName("SidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)

        self._nav_container = QWidget()
        self._nav_layout = QVBoxLayout(self._nav_container)
        self._nav_layout.setContentsMargins(4, 0, 4, 0)
        self._nav_layout.setSpacing(0)
        self._nav_layout.addStretch()

        scroll.setWidget(self._nav_container)
        root.addWidget(scroll, 1)

        # ── Animations ───────────────────────────────────────
        self._anim_min = QPropertyAnimation(self, b"minimumWidth")
        self._anim_min.setDuration(ANIM_MS)
        self._anim_min.setEasingCurve(QEasingCurve.InOutCubic)

        self._anim_max = QPropertyAnimation(self, b"maximumWidth")
        self._anim_max.setDuration(ANIM_MS)
        self._anim_max.setEasingCurve(QEasingCurve.InOutCubic)

    # ──────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────

    def add_item(self, item_id: str, label: str, icon_name: str) -> SidebarItem:
        """Add a standard navigation item (appended before the trailing stretch)."""
        item = SidebarItem(item_id, label, icon_name)
        item.clicked.connect(self.item_clicked)
        self._nav_layout.insertWidget(self._nav_layout.count() - 1, item)
        self._items[item_id] = item
        return item

    def add_plugin_item(self, item_id: str, label: str, icon_name: str) -> SidebarItem:
        """
        Add a plugin navigation item, inserted BEFORE the separator so plugin
        pages appear between the main nav items and settings/about.
        """
        if item_id in self._items:
            return self._items[item_id]

        item = SidebarItem(item_id, label, icon_name)
        item.clicked.connect(self.item_clicked)

        if self._separator is not None:
            idx = self._nav_layout.indexOf(self._separator)
            self._nav_layout.insertWidget(idx, item)
        else:
            self._nav_layout.insertWidget(self._nav_layout.count() - 1, item)

        self._items[item_id] = item

        if not self._expanded:
            item.set_text_visible(False)

        return item

    def remove_item(self, item_id: str):
        item = self._items.pop(item_id, None)
        if item is not None:
            self._nav_layout.removeWidget(item)
            item.setParent(None)
            item.deleteLater()

    def add_separator(self):
        sep = SidebarSeparator()
        self._nav_layout.insertWidget(self._nav_layout.count() - 1, sep)
        if self._separator is None:
            self._separator = sep

    def set_active(self, item_id: str):
        for sid, item in self._items.items():
            item.set_active(sid == item_id)

    def refresh_colors(self):
        """Re-render all item icons/text with up-to-date theme colours.
        Call this after StyleManager.initialise() to reflect accent/theme changes."""
        self._set_hamburger_icon()
        for item in self._items.values():
            item.refresh_style()

    def toggle(self):
        if self._expanded:
            self._collapse()
        else:
            self._expand()

    # ──────────────────────────────────────────────────────
    #  Internal
    # ──────────────────────────────────────────────────────

    def _set_hamburger_icon(self):
        px = _get_icon_pixmap("menu", _fg1_color(), 22)
        if px is not None and not px.isNull():
            self._hamburger.setIcon(px)
            self._hamburger.setIconSize(px.size())
            self._hamburger.setText("")
        else:
            self._hamburger.setText("☰")

    def _expand(self):
        self._expanded = True
        self._logo.setVisible(True)
        for item in self._items.values():
            item.set_text_visible(True)
        self._animate(self.width(), EXPANDED)

    def _collapse(self):
        self._expanded = False
        self._logo.setVisible(False)
        for item in self._items.values():
            item.set_text_visible(False)
        self._animate(self.width(), COLLAPSED)

    def _animate(self, start: int, end: int):
        for anim in (self._anim_min, self._anim_max):
            anim.stop()
            anim.setStartValue(start)
            anim.setEndValue(end)
            anim.start()
