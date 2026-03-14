"""Custom frameless titlebar and mixin for Windows 11-style window chrome.

Architecture
------------
All interaction (drag, resize, double-click, Aero Snap, system menu) is
handled *natively* by Windows via ``WM_NCHITTEST``:

* **Edge/corner resize** : HT* edge values (requires ``WS_THICKFRAME``)
* **Titlebar drag + Aero Snap** : ``HTCAPTION``
* **Double-click to maximize** : ``HTCAPTION`` (native behaviour)
* **Buttons** : ``HTCLIENT`` so Qt receives normal click events

``TitleBarWidget`` is a pure layout widget; no mouse-event overrides needed.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
from ctypes import POINTER, Structure, c_int, c_long, windll, byref

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QPushButton, QWidget,
)

from nova.core.icons import IconManager
from nova.core.style import StyleManager

# ---------------------------------------------------------------------------
#  Win32 constants
# ---------------------------------------------------------------------------
WM_NCHITTEST = 0x0084
WM_NCCALCSIZE = 0x0083
WM_NCACTIVATE = 0x0086
WM_GETMINMAXINFO = 0x0024
WM_SYSCOMMAND = 0x0112

HTCLIENT = 1
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
SWP_FRAMECHANGED = 0x0020
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004

# ---------------------------------------------------------------------------
#  Win32 structures
# ---------------------------------------------------------------------------

class MARGINS(Structure):
    _fields_ = [
        ("cxLeftWidth", c_int),
        ("cxRightWidth", c_int),
        ("cyTopHeight", c_int),
        ("cyBottomHeight", c_int),
    ]


class _POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]


class MINMAXINFO(Structure):
    _fields_ = [
        ("ptReserved", _POINT),
        ("ptMaxSize", _POINT),
        ("ptMaxPosition", _POINT),
        ("ptMinTrackSize", _POINT),
        ("ptMaxTrackSize", _POINT),
    ]


class RECT(Structure):
    _fields_ = [
        ("left", c_long),
        ("top", c_long),
        ("right", c_long),
        ("bottom", c_long),
    ]


class MONITORINFO(Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", ctypes.wintypes.DWORD),
    ]


class NCCALCSIZE_PARAMS(Structure):
    _fields_ = [("rgrc", RECT * 3)]


# ---------------------------------------------------------------------------
#  Win32 function bindings
# ---------------------------------------------------------------------------
_user32 = windll.user32
_dwmapi = windll.dwmapi

MonitorFromWindow = _user32.MonitorFromWindow
MonitorFromWindow.restype = ctypes.wintypes.HMONITOR
MonitorFromWindow.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.DWORD]

GetMonitorInfoW = _user32.GetMonitorInfoW
GetMonitorInfoW.restype = ctypes.wintypes.BOOL
GetMonitorInfoW.argtypes = [ctypes.wintypes.HMONITOR, POINTER(MONITORINFO)]

DwmExtendFrameIntoClientArea = _dwmapi.DwmExtendFrameIntoClientArea
DwmExtendFrameIntoClientArea.restype = c_long
DwmExtendFrameIntoClientArea.argtypes = [ctypes.wintypes.HWND, POINTER(MARGINS)]

DwmSetWindowAttribute = _dwmapi.DwmSetWindowAttribute
DwmSetWindowAttribute.restype = c_long
DwmSetWindowAttribute.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.wintypes.DWORD,
]

GetSystemMenu = _user32.GetSystemMenu
GetSystemMenu.restype = ctypes.wintypes.HMENU
GetSystemMenu.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.BOOL]

TrackPopupMenu = _user32.TrackPopupMenu
TrackPopupMenu.restype = ctypes.wintypes.BOOL
TrackPopupMenu.argtypes = [
    ctypes.wintypes.HMENU,
    ctypes.wintypes.UINT,
    c_int, c_int,
    c_int,
    ctypes.wintypes.HWND,
    ctypes.c_void_p,
]

PostMessageW = _user32.PostMessageW
PostMessageW.restype = ctypes.wintypes.BOOL
PostMessageW.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
]

GetWindowRect = _user32.GetWindowRect
GetWindowRect.restype = ctypes.wintypes.BOOL
GetWindowRect.argtypes = [ctypes.wintypes.HWND, POINTER(RECT)]

GetSystemMetrics = _user32.GetSystemMetrics
GetSystemMetrics.restype = c_int
GetSystemMetrics.argtypes = [c_int]

GetWindowLongW = _user32.GetWindowLongW
GetWindowLongW.restype = c_long
GetWindowLongW.argtypes = [ctypes.wintypes.HWND, c_int]

SetWindowLongW = _user32.SetWindowLongW
SetWindowLongW.restype = c_long
SetWindowLongW.argtypes = [ctypes.wintypes.HWND, c_int, c_long]

SetWindowPos = _user32.SetWindowPos
SetWindowPos.restype = ctypes.wintypes.BOOL
SetWindowPos.argtypes = [
    ctypes.wintypes.HWND, ctypes.wintypes.HWND,
    c_int, c_int, c_int, c_int,
    ctypes.wintypes.UINT,
]

MONITOR_DEFAULTTONEAREST = 2
TPM_RETURNCMD = 0x0100

# Invisible DWM frame width (present when WS_THICKFRAME is set).
# GetWindowRect includes this invisible border; the visible edge is inward.
SM_CXSIZEFRAME = 32
SM_CXPADDEDBORDERWIDTH = 92
_DWM_FRAME = max(GetSystemMetrics(SM_CXSIZEFRAME) + GetSystemMetrics(SM_CXPADDEDBORDERWIDTH), 0)

# Resize zone = invisible border + small visible margin
_VISIBLE_RESIZE_MARGIN = 2
_RESIZE_BORDER = _DWM_FRAME + _VISIBLE_RESIZE_MARGIN
_CORNER_BORDER = _DWM_FRAME + 10


# ---------------------------------------------------------------------------
#  TitleBarWidget
# ---------------------------------------------------------------------------

class TitleBarWidget(QWidget):
    """Custom titlebar with optional icon, pluggable content, and window buttons.

    All drag / resize / double-click / Aero Snap behaviour is handled
    natively by Windows via ``WM_NCHITTEST`` returning ``HTCAPTION``.
    This widget is a pure layout container : no mouse overrides needed.
    """

    sig_minimize_clicked = Signal()
    sig_maximize_clicked = Signal()
    sig_close_clicked = Signal()

    def __init__(
        self,
        parent: QMainWindow,
        content_widget: QWidget | None = None,
        height: int = 32,
        show_icon: bool = True,
        title: str = "",
    ):
        super().__init__(parent)
        self.setObjectName("custom_titlebar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(height)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Optional app icon
        if show_icon:
            self._icon_label = QLabel()
            self._icon_label.setObjectName("titlebar_icon")
            accent = StyleManager.get_colour("accent")
            pm = IconManager.get_pixmap("logo", accent, 18)
            if pm:
                self._icon_label.setPixmap(pm)
            self._icon_label.setFixedSize(34, height)
            self._icon_label.setAlignment(Qt.AlignCenter)
            lay.addWidget(self._icon_label)
        else:
            self._icon_label = None

        # Title label
        fg = StyleManager.get_colour("fg")
        if title:
            self._title_label = QLabel(title)
            self._title_label.setObjectName("titlebar_title")
            self._title_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self._title_label.setStyleSheet(
                f"color: {fg}; font-size: 11px; padding-left: 4px;"
            )
            lay.addWidget(self._title_label)
        else:
            self._title_label = None

        # Content area
        if content_widget is not None:
            lay.addWidget(content_widget, 1)
        else:
            lay.addStretch(1)

        # Window control buttons — Win11 native glyphs (Segoe MDL2 Assets)
        # \uE921 = ChromeMinimize, \uE922 = ChromeMaximize,
        # \uE923 = ChromeRestore, \uE8BB = ChromeClose
        # Win11 default: 46px wide × full titlebar height
        btn_w = 46

        self._minimize_btn = QPushButton("\uE921")
        self._minimize_btn.setObjectName("minimizebtn")
        self._minimize_btn.setFixedSize(btn_w, height)
        self._minimize_btn.clicked.connect(self.sig_minimize_clicked.emit)

        self._maximize_btn = QPushButton("\uE922")
        self._maximize_btn.setObjectName("maximizebtn")
        self._maximize_btn.setFixedSize(btn_w, height)
        self._maximize_btn.clicked.connect(self.sig_maximize_clicked.emit)

        self._close_btn = QPushButton("\uE8BB")
        self._close_btn.setObjectName("closebtn")
        self._close_btn.setFixedSize(btn_w, height)
        self._close_btn.clicked.connect(self.sig_close_clicked.emit)

        lay.addWidget(self._minimize_btn)
        lay.addWidget(self._maximize_btn)
        lay.addWidget(self._close_btn)

    @property
    def maximize_button(self) -> QPushButton:
        return self._maximize_btn

    def update_maximize_icon(self, maximized: bool):
        self._maximize_btn.setText("\uE923" if maximized else "\uE922")


# ---------------------------------------------------------------------------
#  Frameless helpers
# ---------------------------------------------------------------------------

def _setup_frameless(window: QMainWindow, titlebar: TitleBarWidget):
    """Configure window flags, WS_THICKFRAME, DWM shadow, and connect signals."""
    window._titlebar = titlebar
    window._pre_max_size = window.size()

    window.setWindowFlags(
        Qt.Window
        | Qt.FramelessWindowHint
        | Qt.WindowSystemMenuHint
        | Qt.WindowMinMaxButtonsHint
    )

    hwnd = int(window.winId())

    # Add WS_THICKFRAME : required for native resize, Aero Snap, and
    # minimize/maximize animations.  FramelessWindowHint removes it,
    # but WM_NCCALCSIZE returning 0 prevents any visible frame border.
    style = GetWindowLongW(hwnd, GWL_STYLE)
    style |= WS_THICKFRAME
    SetWindowLongW(hwnd, GWL_STYLE, style)
    SetWindowPos(
        hwnd, 0, 0, 0, 0, 0,
        SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER,
    )

    # DWM shadow
    margins = MARGINS(1, 1, 1, 1)
    DwmExtendFrameIntoClientArea(hwnd, byref(margins))

    # Win11 rounded corners
    preference = ctypes.c_int(DWMWCP_ROUND)
    DwmSetWindowAttribute(
        hwnd,
        DWMWA_WINDOW_CORNER_PREFERENCE,
        byref(preference),
        ctypes.sizeof(preference),
    )

    # Connect titlebar signals
    titlebar.sig_minimize_clicked.connect(window.showMinimized)
    titlebar.sig_maximize_clicked.connect(lambda: _toggle_max_restore(window))
    titlebar.sig_close_clicked.connect(window.close)


def _handle_native_event(window, event_type, message):
    """Core nativeEvent logic.

    Handles WM_NCCALCSIZE, WM_NCHITTEST, WM_GETMINMAXINFO.
    Returns ``(True, result)`` when handled, ``None`` to fall through.
    """
    try:
        msg = ctypes.wintypes.MSG.from_address(int(message))
    except Exception:
        return None

    hwnd = msg.hWnd

    # --- WM_NCACTIVATE: suppress default inactive frame border ----------
    if msg.message == WM_NCACTIVATE:
        # Return TRUE to accept the activation change without letting
        # Windows redraw the non-client area (grey thick-frame border).
        return True, 1

    # --- WM_NCCALCSIZE: make entire window = client area ----------------
    if msg.message == WM_NCCALCSIZE:
        if msg.wParam:
            params = NCCALCSIZE_PARAMS.from_address(msg.lParam)
            # Only clamp to work area when the window is truly being
            # maximized.  During a restore-by-drag, isMaximized() is
            # still True but the proposed rect is already the smaller
            # restored size : clamping it to the work area causes a
            # content-offset / white-space layout glitch.
            monitor = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            GetMonitorInfoW(monitor, byref(mi))
            mon = mi.rcMonitor
            proposed_w = params.rgrc[0].right - params.rgrc[0].left
            proposed_h = params.rgrc[0].bottom - params.rgrc[0].top
            mon_w = mon.right - mon.left
            mon_h = mon.bottom - mon.top
            if proposed_w >= mon_w and proposed_h >= mon_h:
                # Actually maximizing : clamp to work area
                work = mi.rcWork
                params.rgrc[0].left = work.left
                params.rgrc[0].top = work.top
                params.rgrc[0].right = work.right
                params.rgrc[0].bottom = work.bottom
        return True, 0

    # --- WM_NCHITTEST ---------------------------------------------------
    # All coordinates here are in Win32 physical screen pixels.
    # Widget sizes (Qt logical px) are scaled by devicePixelRatioF().
    if msg.message == WM_NCHITTEST:
        screen_x = ctypes.c_short(msg.lParam & 0xFFFF).value
        screen_y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value

        wr = RECT()
        GetWindowRect(hwnd, byref(wr))
        lx = screen_x - wr.left   # local x (physical px from window-rect left)
        ly = screen_y - wr.top    # local y (physical px from window-rect top)
        w = wr.right - wr.left
        h = wr.bottom - wr.top
        frame = _DWM_FRAME

        # Edge / corner resize (only when not maximized)
        if not window.isMaximized():
            border = _RESIZE_BORDER
            corner = _CORNER_BORDER

            # Corners first (larger hit area)
            if lx < corner and ly < corner:
                return True, HTTOPLEFT
            if lx >= w - corner and ly < corner:
                return True, HTTOPRIGHT
            if lx < corner and ly >= h - corner:
                return True, HTBOTTOMLEFT
            if lx >= w - corner and ly >= h - corner:
                return True, HTBOTTOMRIGHT
            # Edges
            if lx < border:
                return True, HTLEFT
            if lx >= w - border:
                return True, HTRIGHT
            if ly < border:
                return True, HTTOP
            if ly >= h - border:
                return True, HTBOTTOM

        # Titlebar hit-testing (computed in Win32 physical-pixel coords,
        # NOT using mapToGlobal which returns Qt logical coords).
        titlebar = getattr(window, '_titlebar', None)
        if titlebar is not None and titlebar.isVisible():
            dpr = window.devicePixelRatioF()
            tb_h = int(titlebar.height() * dpr)
            tb_top = frame          # visible top of window
            tb_bottom = tb_top + tb_h

            if tb_top <= ly < tb_bottom:
                # Buttons occupy 3 × 46 logical-px at the right edge
                btn_total_w = int(3 * 46 * dpr)
                btn_left = w - frame - btn_total_w
                if lx >= btn_left:
                    return True, HTCLIENT   # over buttons : Qt handles clicks
                return True, HTCAPTION      # titlebar drag area

        return True, HTCLIENT

    # --- WM_GETMINMAXINFO: constrain maximised size ---------------------
    if msg.message == WM_GETMINMAXINFO:
        info = MINMAXINFO.from_address(msg.lParam)
        monitor = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        GetMonitorInfoW(monitor, byref(mi))
        work = mi.rcWork
        info.ptMaxPosition.x = work.left
        info.ptMaxPosition.y = work.top
        info.ptMaxSize.x = work.right - work.left
        info.ptMaxSize.y = work.bottom - work.top
        info.ptMinTrackSize.x = 800
        info.ptMinTrackSize.y = 500
        return True, 0

    return None


def _handle_change_event(window, event):
    """Update the titlebar icon and remember pre-maximize size."""
    if event.type() == QEvent.WindowStateChange:
        if window.isMaximized():
            old_state = event.oldState() if hasattr(event, 'oldState') else None
            if old_state is not None and not (old_state & Qt.WindowMaximized):
                pass  # _pre_max_size already saved by _toggle_max_restore
        else:
            QTimer.singleShot(0, lambda: _save_normal_size(window))
        window._titlebar.update_maximize_icon(window.isMaximized())


def _save_normal_size(window):
    """Capture the normal-state size (deferred so geometry is settled)."""
    if not window.isMaximized() and not window.isMinimized():
        window._pre_max_size = window.size()


def _handle_context_menu(window, event):
    """Show the Win32 system context menu on right-click in the titlebar.

    Note: when WM_NCHITTEST returns HTCAPTION, Windows handles the system
    menu natively on right-click.  This function is a fallback for edge
    cases where Qt still receives contextMenuEvent.
    """
    titlebar = window._titlebar
    tb_pos = titlebar.mapTo(window, QPoint(0, 0))
    tb_rect = QRect(tb_pos, titlebar.size())
    if tb_rect.contains(event.pos()):
        hwnd = int(window.winId())
        hmenu = GetSystemMenu(hwnd, False)
        if hmenu:
            gp = window.mapToGlobal(event.pos())
            cmd = TrackPopupMenu(
                hmenu, TPM_RETURNCMD,
                gp.x(), gp.y(), 0, hwnd, None,
            )
            if cmd:
                PostMessageW(hwnd, WM_SYSCOMMAND, cmd, 0)
        return True
    return False


def _toggle_max_restore(window):
    if not window.isMaximized():
        window._pre_max_size = window.size()
    if window.isMaximized():
        window.showNormal()
    else:
        window.showMaximized()


# ---------------------------------------------------------------------------
#  FramelessMixin
# ---------------------------------------------------------------------------

class FramelessMixin:
    """Mixin for QMainWindow providing frameless window behaviour.

    Subclasses MUST define ``nativeEvent`` and ``changeEvent`` that delegate
    to the ``_frameless_*`` helpers below.
    """

    def init_frameless(self, titlebar: TitleBarWidget):
        _setup_frameless(self, titlebar)

    def _frameless_nativeEvent(self, event_type, message):
        return _handle_native_event(self, event_type, message)

    def _frameless_changeEvent(self, event):
        _handle_change_event(self, event)

    def _frameless_contextMenuEvent(self, event):
        return _handle_context_menu(self, event)

    def _frameless_toggle_max_restore(self):
        _toggle_max_restore(self)
