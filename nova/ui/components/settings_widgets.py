"""
OOP setting-widget hierarchy for Nova's Settings page.

Hierarchy
---------
BaseSettingWidget(QWidget)
  value_changed = Signal(object)
  get_value() / set_value(val)

  ├── TextSettingWidget         type: "text"
  ├── DropdownSettingWidget     type: "dropdown"
  ├── BoolSettingWidget         type: "bool"
  ├── ColorSettingWidget        type: "colorpicker"
  ├── PathSettingWidget(mode)   mode: "file" | "folder" | "font"
  └── SpinboxSettingWidget      type: "number" | "spinbox"

Factory
-------
create_setting_widget(item: SettingItem) -> BaseSettingWidget
"""

from __future__ import annotations

from typing import List, Optional, Any

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QFileDialog,
    QHBoxLayout, QLineEdit, QPushButton, QSizePolicy,
    QSpinBox, QWidget,
)

_MIN_INPUT_WIDTH = 260  # minimum width for text/path inputs
_COMBO_WIDTH     = 260  # fixed width for combo boxes (finite option list)


class BaseSettingWidget(QWidget):
    """Abstract base for all setting input widgets."""

    value_changed = Signal(object)

    def get_value(self) -> Any:
        raise NotImplementedError

    def set_value(self, val: Any) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Concrete widgets
# ---------------------------------------------------------------------------

class TextSettingWidget(BaseSettingWidget):
    """Single-line text input."""

    def __init__(self, value: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._edit = QLineEdit(str(value))
        self._edit.setObjectName("SettingEdit")
        self._edit.setMinimumWidth(_MIN_INPUT_WIDTH)
        self._edit.editingFinished.connect(lambda: self.value_changed.emit(self._edit.text()))
        layout.addWidget(self._edit)

    def get_value(self) -> str:
        return self._edit.text()

    def set_value(self, val: Any) -> None:
        self._edit.setText(str(val))


class DropdownSettingWidget(BaseSettingWidget):
    """Combo-box drop-down."""

    def __init__(self, value: str = "", options: List[str] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._combo = QComboBox()
        self._combo.setObjectName("SettingCombo")
        self._combo.setMinimumWidth(_COMBO_WIDTH)
        for opt in (options or []):
            self._combo.addItem(str(opt))
        idx = self._combo.findText(str(value))
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        self._combo.currentTextChanged.connect(lambda t: self.value_changed.emit(t))
        layout.addWidget(self._combo)

    def get_value(self) -> str:
        return self._combo.currentText()

    def set_value(self, val: Any) -> None:
        idx = self._combo.findText(str(val))
        if idx >= 0:
            self._combo.setCurrentIndex(idx)


class BoolSettingWidget(BaseSettingWidget):
    """Simple checkbox."""

    def __init__(self, value: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._chk = QCheckBox()
        checked = (str(value).lower() == "true") if isinstance(value, str) else bool(value)
        self._chk.setChecked(checked)
        self._chk.stateChanged.connect(lambda s: self.value_changed.emit(s == 2))
        layout.addWidget(self._chk)

    def get_value(self) -> bool:
        return self._chk.isChecked()

    def set_value(self, val: Any) -> None:
        checked = (str(val).lower() == "true") if isinstance(val, str) else bool(val)
        self._chk.setChecked(checked)


class ColorSettingWidget(BaseSettingWidget):
    """Colour-swatch button + QColorDialog."""

    def __init__(self, value: str = "#000000", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._btn = QPushButton()
        self._btn.setObjectName("ColorPickerButton")
        self._btn.setMinimumWidth(110)
        self._btn.setFixedHeight(26)
        self._current = str(value) or "#000000"
        self._update_button(self._current)
        self._btn.clicked.connect(self._on_clicked)
        layout.addWidget(self._btn)

    def _on_clicked(self):
        initial = QColor(self._current)
        if not initial.isValid():
            initial = QColor("#000000")
        chosen = QColorDialog.getColor(initial, self, "Choose colour")
        if chosen.isValid():
            self._current = "#{:02X}{:02X}{:02X}".format(chosen.red(), chosen.green(), chosen.blue())
            self._update_button(self._current)
            self.value_changed.emit(self._current)

    def _update_button(self, hex_val: str):
        c = QColor(hex_val)
        if not c.isValid():
            c = QColor(0, 0, 0)
        lum = (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255
        text_color = "#000000" if lum > 0.5 else "#FFFFFF"
        self._btn.setText(hex_val.upper())
        self._btn.setStyleSheet(
            f"background-color: {hex_val}; color: {text_color}; "
            "border: none; border-radius: 14px; font-weight: 600; "
            "min-height: 28px; max-height: 28px;"
        )

    def get_value(self) -> str:
        return self._current

    def set_value(self, val: Any) -> None:
        self._current = str(val)
        self._update_button(self._current)


class PathSettingWidget(BaseSettingWidget):
    """Line-edit + browse button.  mode: 'file' | 'folder' | 'font'"""

    def __init__(self, value: str = "", mode: str = "file",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._mode = mode

        # Allow the whole widget to expand horizontally so the edit fills space
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._edit = QLineEdit(str(value))
        self._edit.setObjectName("SettingEdit")
        self._edit.setMinimumWidth(_MIN_INPUT_WIDTH)
        self._edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._edit.editingFinished.connect(lambda: self.value_changed.emit(self._edit.text()))

        _icon_map = {"folder": "folder", "font": "font"}
        btn = QPushButton(_icon_map.get(mode, "file").capitalize() + "…")
        btn.setObjectName("BrowseButton")
        btn.setMinimumWidth(72)
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn.clicked.connect(self._on_browse)
        try:
            from nova.core.icons import IconManager
            from nova.core.style import StyleManager
            _icon_name = _icon_map.get(mode, "file")
            _px = IconManager.get_pixmap(_icon_name, StyleManager.get_colour("ctrl_fg"), 14)
            if _px and not _px.isNull():
                btn.setIcon(QIcon(_px))
                btn.setIconSize(QSize(14, 14))
        except Exception:
            pass

        layout.addWidget(self._edit, 1)
        layout.addWidget(btn)

    def _on_browse(self):
        current = self._edit.text()
        if self._mode == "folder":
            path = QFileDialog.getExistingDirectory(self, "Select Folder", current)
            if path:
                self._edit.setText(path)
                self.value_changed.emit(path)
        elif self._mode == "font":
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Font File", current,
                "Font Files (*.ttf *.otf);;All Files (*)"
            )
            if path:
                self._edit.setText(path)
                self.value_changed.emit(path)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select File", current)
            if path:
                self._edit.setText(path)
                self.value_changed.emit(path)

    def get_value(self) -> str:
        return self._edit.text()

    def set_value(self, val: Any) -> None:
        self._edit.setText(str(val))


class SpinboxSettingWidget(BaseSettingWidget):
    """Integer spin-box."""

    def __init__(self, value: int = 0, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._spin = QSpinBox()
        self._spin.setObjectName("SettingSpinbox")
        self._spin.setMinimumWidth(100)
        self._spin.setRange(-999999, 999999)
        try:
            self._spin.setValue(int(value))
        except (ValueError, TypeError):
            self._spin.setValue(0)
        self._spin.valueChanged.connect(lambda v: self.value_changed.emit(v))
        layout.addWidget(self._spin)

    def get_value(self) -> int:
        return self._spin.value()

    def set_value(self, val: Any) -> None:
        try:
            self._spin.setValue(int(val))
        except (ValueError, TypeError):
            pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_setting_widget(item) -> Optional[BaseSettingWidget]:
    """Instantiate the correct BaseSettingWidget subclass for *item* (a SettingItem)."""
    t = (getattr(item, "type", "") or "").lower()
    val = getattr(item, "value", "")
    vals = getattr(item, "values", []) or []

    if t == "colorpicker":
        return ColorSettingWidget(str(val) if val else "#000000")

    if t == "dropdown":
        return DropdownSettingWidget(str(val), [str(v) for v in vals])

    if t == "bool":
        return BoolSettingWidget(val)

    if t == "filebrowse":
        return PathSettingWidget(str(val) if val else "", mode="file")

    if t == "folderbrowse":
        return PathSettingWidget(str(val) if val else "", mode="folder")

    if t == "fontbrowse":
        return PathSettingWidget(str(val) if val else "", mode="font")

    if t in ("number", "spinbox"):
        return SpinboxSettingWidget(val)

    if t == "text":
        return TextSettingWidget(str(val) if val else "")

    return None
