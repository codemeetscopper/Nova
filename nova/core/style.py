from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Union, Optional

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

_log = logging.getLogger(__name__)

ColourLike = Union[str, QColor]

class StyleManager:
    """
    Manages application theme colors.
    Replaces qtpop.appearance.stylemanager.StyleManager
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StyleManager, cls).__new__(cls)
            cls._instance._colours = {}
            cls._instance._palette = None
            cls._instance._resolved_mode = "light"
            cls._instance._font_family = '"Segoe UI", "Roboto", sans-serif'
        return cls._instance

    @classmethod
    def mode(cls) -> str:
        """Return the currently resolved theme mode ('dark' or 'light')."""
        return cls()._resolved_mode

    @classmethod
    def set_font_family(cls, family: str) -> None:
        """Store the custom font family so apply_theme() injects it into QSS."""
        cls()._font_family = f'"{family}", "Segoe UI", "Roboto", sans-serif'

    @classmethod
    def get_font_family(cls) -> str:
        return getattr(cls(), '_font_family', '"Segoe UI", "Roboto", sans-serif')

    @classmethod
    def initialise(cls, accent_hex: str, support_hex: str = "#FF9800", neutral_hex: str = "#4CAF50", theme: str = "dark"):
        inst = cls()
        try:
            accent = cls._to_qcolor(accent_hex)
            support = cls._to_qcolor(support_hex)
            neutral = cls._to_qcolor(neutral_hex)

            # Resolve "system" → detect OS colour scheme (Qt 6.5+)
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

            white = QColor(255, 255, 255)
            black = QColor(0, 0, 0)
            
            # Simple blending helpers
            def blend(c1, c2, t):
                r = c1.red() * (1-t) + c2.red() * t
                g = c1.green() * (1-t) + c2.green() * t
                b = c1.blue() * (1-t) + c2.blue() * t
                return QColor(int(r), int(g), int(b))

            lighten = lambda c, t: blend(c, white, t)
            darken = lambda c, t: blend(c, black, t)

            def make_tiers(base, name):
                if theme == "light":
                    return {
                        f"{name}": base,
                        f"{name}_l1": lighten(base, 0.15),
                        f"{name}_l2": lighten(base, 0.30),
                        f"{name}_l3": lighten(base, 0.45),
                        f"{name}_ln": lighten(base, 0.90),
                        f"{name}_d1": darken(base, 0.15),
                        f"{name}_d2": darken(base, 0.30),
                    }
                else:
                    return {
                        f"{name}": base,
                        f"{name}_l1": darken(base, 0.15),
                        f"{name}_l2": darken(base, 0.30),
                        f"{name}_l3": darken(base, 0.45),
                        f"{name}_ln": darken(base, 0.90),
                        f"{name}_d1": lighten(base, 0.15),
                        f"{name}_d2": lighten(base, 0.30),
                    }

            inst._colours.update(make_tiers(accent, "accent"))
            inst._colours.update(make_tiers(support, "support"))
            inst._colours.update(make_tiers(neutral, "neutral"))

            if theme == "dark":
                bg = QColor(18, 18, 18)
                bg1 = lighten(bg, 0.05)
                bg2 = lighten(bg, 0.08)
                fg = QColor(255, 255, 255)
                fg1 = blend(fg, bg, 0.15) # slightly dimmed white
                fg2 = blend(fg, bg, 0.30)
            else:
                bg = QColor(247, 247, 247)
                bg1 = darken(bg, 0.05)
                bg2 = darken(bg, 0.08)
                fg = QColor(0, 0, 0)
                fg1 = blend(fg, bg, 0.15)
                fg2 = blend(fg, bg, 0.30)

            inst._colours.update({
                "bg": bg, "bg1": bg1, "bg2": bg2,
                "fg": fg, "fg1": fg1, "fg2": fg2
            })

            # High-contrast control colours (textboxes, combos, spinboxes, buttons)
            if theme == "dark":
                ctrl_bg       = QColor(255, 255, 255)   # white controls on dark card
                ctrl_bg_hover = QColor(230, 230, 230)   # slightly dimmed on hover/focus
                ctrl_fg       = QColor(17,  17,  17)    # near-black text on white
            else:
                ctrl_bg       = QColor(25,  25,  25)    # near-black controls on light card
                ctrl_bg_hover = QColor(50,  50,  50)    # slightly lighter on hover/focus
                ctrl_fg       = QColor(240, 240, 240)   # near-white text on dark
            inst._colours.update({
                "ctrl_bg":       ctrl_bg,
                "ctrl_bg_hover": ctrl_bg_hover,
                "ctrl_fg":       ctrl_fg,
            })
            
            # Build palette (simplified)
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
            _log.error(f"StyleManager init failed: {e}")

    @classmethod
    def get_colour(cls, key: str) -> str:
        """Returns hex string for a color key."""
        inst = cls()
        key = key.lower()
        if key in inst._colours:
            c = inst._colours[key]
            return f"#{c.red():02X}{c.green():02X}{c.blue():02X}"
        return "#FF00FF" # Magenta fallback

    @classmethod
    def get_palette(cls) -> QPalette:
        return cls()._palette or QPalette()
        
    @classmethod
    def _write_qss_icons(cls) -> Dict[str, str]:
        """Write SVG icon files to tmp_qss_icons/ and return a token→path mapping.

        Two sets of arrows are produced:
        • url_down_arrow / url_up_arrow  — coloured fg1, used by generic QComboBox
          which sits on bg/bg1 backgrounds.
        • url_down_arrow_ctrl / url_up_arrow_ctrl — coloured ctrl_fg, used by
          settings controls that sit on the high-contrast ctrl_bg background.
        • url_check — white checkmark for the accent-coloured checkbox indicator.
        """
        from nova.core.paths import get_temp_dir

        fg1      = cls.get_colour("fg1")      # readable on theme-bg backgrounds
        ctrl_fg  = cls.get_colour("ctrl_fg")  # readable on white/dark ctrl_bg

        tmp_dir = get_temp_dir() / "qss_icons"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        def _arrow_down(color: str) -> str:
            return (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                f'<path fill="{color}" d="M7 10l5 5 5-5z"/>'
                '</svg>'
            )

        def _arrow_up(color: str) -> str:
            return (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                f'<path fill="{color}" d="M7 14l5-5 5 5z"/>'
                '</svg>'
            )

        check_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<path fill="white" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>'
            '</svg>'
        )

        files: Dict[str, tuple] = {
            "url_down_arrow":      (tmp_dir / "down_arrow.svg",      _arrow_down(fg1)),
            "url_up_arrow":        (tmp_dir / "up_arrow.svg",        _arrow_up(fg1)),
            "url_down_arrow_ctrl": (tmp_dir / "down_arrow_ctrl.svg", _arrow_down(fg1)),
            "url_up_arrow_ctrl":   (tmp_dir / "up_arrow_ctrl.svg",   _arrow_up(fg1)),
            "url_check":           (tmp_dir / "check.svg",           check_svg),
        }
        for _path, _content in files.values():
            _path.write_text(_content, encoding="utf-8")

        return {token: path.as_posix() for token, (path, _) in files.items()}

    @classmethod
    def apply_theme(cls, app: QApplication, qss_content: str):
        """Process QSS and apply to app."""
        import re

        # 1. Font-family token (not a colour)
        processed_qss = qss_content.replace("<font_family>", cls.get_font_family())

        # 2. SVG icon file paths for url() references in QSS
        try:
            url_map = cls._write_qss_icons()
            for token, posix_path in url_map.items():
                processed_qss = processed_qss.replace(f"<{token}>", posix_path)
        except Exception as e:
            _log.warning(f"Could not write QSS icon files: {e}")

        # 3. Colour tokens <token>
        def repl(m):
            key = m.group(1)
            return cls.get_colour(key)

        processed_qss = re.sub(r"<([a-zA-Z0-9_]+)>", repl, processed_qss)

        app.setPalette(cls.get_palette())
        app.setStyleSheet(processed_qss)

    @staticmethod
    def _to_qcolor(val: ColourLike) -> QColor:
        if isinstance(val, QColor): return val
        c = QColor(val)
        if not c.isValid(): raise ValueError(f"Invalid color: {val}")
        return c
