"""
Standalone StyleManager for Nova Installer.
Adapted from Nova's core/style.py — no external dependencies.
"""
from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Dict, Union

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

_log = logging.getLogger(__name__)

ColourLike = Union[str, QColor]


class StyleManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._colours: Dict[str, QColor] = {}
            cls._instance._palette = None
            cls._instance._resolved_mode = "dark"
            cls._instance._font_family = '"Segoe UI", "Roboto", sans-serif'
        return cls._instance

    @classmethod
    def mode(cls) -> str:
        return cls()._resolved_mode

    @classmethod
    def set_font_family(cls, family: str) -> None:
        cls()._font_family = f'"{family}", "Segoe UI", "Roboto", sans-serif'

    @classmethod
    def get_font_family(cls) -> str:
        return getattr(cls(), "_font_family", '"Segoe UI", "Roboto", sans-serif')

    @classmethod
    def initialise(cls, accent_hex: str, theme: str = "dark"):
        inst = cls()
        try:
            accent = cls._to_qcolor(accent_hex)
            white = QColor(255, 255, 255)
            black = QColor(0, 0, 0)

            if theme == "system":
                try:
                    from PySide6.QtCore import Qt as _Qt
                    app = QApplication.instance()
                    if app is not None:
                        scheme = app.styleHints().colorScheme()
                        theme = "dark" if scheme == _Qt.ColorScheme.Dark else "light"
                    else:
                        theme = "dark"
                except Exception:
                    theme = "dark"

            inst._resolved_mode = theme

            def blend(c1, c2, t):
                return QColor(
                    int(c1.red() * (1 - t) + c2.red() * t),
                    int(c1.green() * (1 - t) + c2.green() * t),
                    int(c1.blue() * (1 - t) + c2.blue() * t),
                )

            lighten = lambda c, t: blend(c, white, t)
            darken = lambda c, t: blend(c, black, t)

            def make_tiers(base, name):
                if theme == "light":
                    return {
                        name: base,
                        f"{name}_l1": lighten(base, 0.15),
                        f"{name}_l2": lighten(base, 0.30),
                        f"{name}_l3": lighten(base, 0.45),
                        f"{name}_ln": lighten(base, 0.90),
                        f"{name}_d1": darken(base, 0.15),
                        f"{name}_d2": darken(base, 0.30),
                    }
                else:
                    return {
                        name: base,
                        f"{name}_l1": darken(base, 0.15),
                        f"{name}_l2": darken(base, 0.30),
                        f"{name}_l3": darken(base, 0.45),
                        f"{name}_ln": darken(base, 0.90),
                        f"{name}_d1": lighten(base, 0.15),
                        f"{name}_d2": lighten(base, 0.30),
                    }

            inst._colours.update(make_tiers(accent, "accent"))

            if theme == "dark":
                bg = QColor(18, 18, 18)
                bg1 = lighten(bg, 0.05)
                bg2 = lighten(bg, 0.08)
                fg = QColor(255, 255, 255)
                fg1 = blend(fg, bg, 0.15)
                fg2 = blend(fg, bg, 0.30)
            else:
                bg = QColor(247, 247, 247)
                bg1 = darken(bg, 0.05)
                bg2 = darken(bg, 0.08)
                fg = QColor(0, 0, 0)
                fg1 = blend(fg, bg, 0.15)
                fg2 = blend(fg, bg, 0.30)

            inst._colours.update(
                {"bg": bg, "bg1": bg1, "bg2": bg2, "fg": fg, "fg1": fg1, "fg2": fg2}
            )

            p = QPalette()
            p.setColor(QPalette.Window, bg)
            p.setColor(QPalette.WindowText, fg)
            p.setColor(QPalette.Base, bg)
            p.setColor(QPalette.AlternateBase, bg1)
            p.setColor(QPalette.Text, fg)
            p.setColor(QPalette.Button, bg1)
            p.setColor(QPalette.ButtonText, fg)
            p.setColor(QPalette.Highlight, accent)
            p.setColor(QPalette.HighlightedText, white)
            inst._palette = p

        except Exception as e:
            _log.error("StyleManager init failed: %s", e)

    @classmethod
    def get_colour(cls, key: str) -> str:
        inst = cls()
        key = key.lower()
        if key in inst._colours:
            c = inst._colours[key]
            return f"#{c.red():02X}{c.green():02X}{c.blue():02X}"
        return "#FF00FF"

    @classmethod
    def get_palette(cls) -> QPalette:
        return cls()._palette or QPalette()

    @classmethod
    def apply_theme(cls, app: QApplication, qss_content: str):
        processed = qss_content.replace("<font_family>", cls.get_font_family())

        # Write SVG arrows for combo/spinbox
        try:
            url_map = cls._write_qss_icons()
            for token, posix_path in url_map.items():
                processed = processed.replace(f"<{token}>", posix_path)
        except Exception as e:
            _log.warning("Could not write QSS icon files: %s", e)

        def repl(m):
            return cls.get_colour(m.group(1))

        processed = re.sub(r"<([a-zA-Z0-9_]+)>", repl, processed)
        app.setPalette(cls.get_palette())
        app.setStyleSheet(processed)

    @classmethod
    def _write_qss_icons(cls) -> Dict[str, str]:
        fg1 = cls.get_colour("fg1")
        tmp_dir = Path(tempfile.gettempdir()) / "nova_installer_icons"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        def _arrow_down(color):
            return (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                f'<path fill="{color}" d="M7 10l5 5 5-5z"/>'
                "</svg>"
            )

        def _arrow_up(color):
            return (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                f'<path fill="{color}" d="M7 14l5-5 5 5z"/>'
                "</svg>"
            )

        check_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<path fill="white" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>'
            "</svg>"
        )

        files = {
            "url_down_arrow": (tmp_dir / "down_arrow.svg", _arrow_down(fg1)),
            "url_up_arrow": (tmp_dir / "up_arrow.svg", _arrow_up(fg1)),
            "url_check": (tmp_dir / "check.svg", check_svg),
        }
        for _path, _content in files.values():
            _path.write_text(_content, encoding="utf-8")

        return {token: path.as_posix() for token, (path, _) in files.items()}

    @staticmethod
    def _to_qcolor(val: ColourLike) -> QColor:
        if isinstance(val, QColor):
            return val
        c = QColor(val)
        if not c.isValid():
            raise ValueError(f"Invalid color: {val}")
        return c
