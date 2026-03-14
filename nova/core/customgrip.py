"""Drop shadow effect for frameless QMainWindow.

Applies a ``QGraphicsDropShadowEffect`` to the central widget for a
native-looking window border shadow.  Edge/corner resize is handled
natively by ``WM_NCHITTEST`` in :mod:`nova.core.titlebar`.

Usage::

    from nova.core.customgrip import CustomGrip

    class MyWindow(FramelessMixin, QMainWindow):
        def __init__(self):
            super().__init__()
            ...
            self.init_frameless(self._custom_titlebar)
            self._grip = CustomGrip(self)
"""
from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QMainWindow

# Drop shadow parameters
_SHADOW_RADIUS = 20
_SHADOW_COLOR = QColor(0, 0, 0, 60)
_SHADOW_OFFSET = 0

# Kept for backward compatibility (unused : resize is handled by WM_NCHITTEST)
_GRIP_SIZE = 12


class CustomGrip:
    """Applies a drop shadow to a frameless window's central widget.

    Parameters
    ----------
    window : QMainWindow
        The frameless window to add the shadow to.
    grip_size : int
        Unused : kept for backward compatibility.
    shadow : bool
        If *True* (default), apply a ``QGraphicsDropShadowEffect``.
    """

    def __init__(
        self,
        window: QMainWindow,
        grip_size: int = _GRIP_SIZE,
        shadow: bool = True,
    ):
        self._window = window
        self._shadow_effect: QGraphicsDropShadowEffect | None = None
        if shadow:
            self._apply_shadow()

    def _apply_shadow(self):
        """Apply a drop shadow effect to the window's central widget."""
        central = self._window.centralWidget()
        if central is None:
            return
        effect = QGraphicsDropShadowEffect(central)
        effect.setBlurRadius(_SHADOW_RADIUS)
        effect.setColor(_SHADOW_COLOR)
        effect.setOffset(_SHADOW_OFFSET, _SHADOW_OFFSET)
        central.setGraphicsEffect(effect)
        self._shadow_effect = effect

    def destroy(self):
        """Remove the shadow effect."""
        if self._shadow_effect:
            central = self._window.centralWidget()
            if central:
                central.setGraphicsEffect(None)
            self._shadow_effect = None
