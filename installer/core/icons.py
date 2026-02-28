"""
Standalone IconManager for Nova Installer.
Adapted from Nova's core/icons.py — no external dependencies.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_log = logging.getLogger(__name__)

# Nova icon colors — used for the app icon rendered at multiple sizes
ICON_PRIMARY = "#0088CC"
ICON_SECONDARY = "#00BBFF"


class IconManager:
    _instance: Optional["IconManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._icon_cache: dict[str, QImage] = {}
        return cls._instance

    @classmethod
    def get_pixmap(cls, name: str, color: str = "#FFFFFF", size: int = 24) -> Optional[QPixmap]:
        from installer.resources.builtin_icons import ICONS

        svg_str = ICONS.get(name)
        if svg_str is None:
            stripped = name.split("_", 1)[-1] if "_" in name else None
            if stripped:
                svg_str = ICONS.get(stripped)
        if svg_str is None:
            _log.warning("Icon not found: %s", name)
            return None
        return cls.render_svg_string(svg_str, color, size)

    @staticmethod
    def render_svg_string(svg_str: str, color: str = "#FFFFFF", size: int = 24) -> Optional[QPixmap]:
        data = QByteArray(svg_str.encode())
        renderer = QSvgRenderer(data)
        if not renderer.isValid():
            return None

        img = QImage(size, size, QImage.Format_ARGB32)
        img.fill(Qt.transparent)

        painter = QPainter(img)
        renderer.render(painter)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(img.rect(), QColor(color))
        painter.end()

        return QPixmap.fromImage(img)

    @classmethod
    def get_app_icon(cls) -> QIcon:
        """Render the nova_icon SVG at multiple sizes and return a QIcon."""
        from installer.resources.builtin_icons import ICONS

        svg_template = ICONS.get("nova_icon", "")
        svg_str = svg_template.format(
            primary=ICON_PRIMARY, secondary=ICON_SECONDARY,
        )

        icon = QIcon()
        for size in (16, 24, 32, 48, 64, 128, 256):
            data = QByteArray(svg_str.encode())
            renderer = QSvgRenderer(data)
            if not renderer.isValid():
                continue
            img = QImage(size, size, QImage.Format_ARGB32)
            img.fill(Qt.transparent)
            painter = QPainter(img)
            renderer.render(painter)
            painter.end()
            icon.addPixmap(QPixmap.fromImage(img))
        return icon
