from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_log = logging.getLogger(__name__)


class IconManager:
    """
    Inline-SVG icon manager — no filesystem I/O.
    All icons come from nova.resources.builtin_icons.ICONS.
    """

    _instance: Optional["IconManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._icon_cache: dict[str, QImage] = {}
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def get_pixmap(cls, name: str, color: str = "#FFFFFF", size: int = 24) -> Optional[QPixmap]:
        """Return a coloured QPixmap for *name* from the built-in icon set."""
        from nova.resources.builtin_icons import ICONS

        svg_str = ICONS.get(name)
        if svg_str is None:
            # Try stripping a leading word prefix (e.g. "action_home" → "home")
            stripped = name.split("_", 1)[-1] if "_" in name else None
            if stripped:
                svg_str = ICONS.get(stripped)
        if svg_str is None:
            _log.warning("Icon not found in built-in set: %s", name)
            return None

        return cls.render_svg_string(svg_str, color, size)

    @staticmethod
    def render_svg_string(svg_str: str, color: str = "#FFFFFF", size: int = 24) -> Optional[QPixmap]:
        """Render an SVG string to a solid-colour QPixmap (SourceIn compositing)."""
        data = QByteArray(svg_str.encode())
        renderer = QSvgRenderer(data)
        if not renderer.isValid():
            _log.warning("Invalid SVG data passed to render_svg_string")
            return None

        img = QImage(size, size, QImage.Format_ARGB32)
        img.fill(Qt.transparent)

        painter = QPainter(img)
        renderer.render(painter)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(img.rect(), QColor(color))
        painter.end()

        return QPixmap.fromImage(img)
