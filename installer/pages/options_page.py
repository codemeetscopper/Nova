"""Options page — desktop shortcut, start menu, components, etc."""
from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from installer.core.icons import IconManager
from installer.core.style import StyleManager


class _OptionCard(QFrame):
    """A styled checkbox option with icon and description."""

    def __init__(self, icon_name: str, title: str, description: str,
                 checked: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("OptionCard")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # Icon
        icon_label = QLabel()
        icon_label.setObjectName("OptionIcon")
        icon_label.setFixedSize(24, 24)
        icon_label.setAlignment(Qt.AlignCenter)
        fg1 = StyleManager.get_colour("fg1")
        px = IconManager.get_pixmap(icon_name, fg1, 18)
        if px and not px.isNull():
            icon_label.setPixmap(px)
            icon_label.setStyleSheet("background: transparent;")
        layout.addWidget(icon_label, 0, Qt.AlignVCenter)

        # Text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)
        text_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel(title)
        title_label.setObjectName("OptionTitle")
        title_label.setMinimumHeight(16)
        text_layout.addWidget(title_label)

        desc_label = QLabel(description)
        desc_label.setObjectName("OptionDesc")
        desc_label.setWordWrap(True)
        desc_label.setMinimumHeight(14)
        text_layout.addWidget(desc_label)

        layout.addLayout(text_layout, 1)

        # Checkbox
        self._checkbox = QCheckBox()
        self._checkbox.setObjectName("OptionCheckbox")
        self._checkbox.setChecked(checked)
        self._checkbox.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self._checkbox, 0, Qt.AlignVCenter)

    @property
    def checked(self) -> bool:
        return self._checkbox.isChecked()

    def set_checked(self, checked: bool):
        self._checkbox.setChecked(checked)


class OptionsPage(QWidget):
    def __init__(self, components: List[Dict[str, Any]] | None = None,
                 plugins: List[Dict[str, Any]] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("OptionsPage")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setObjectName("OptionsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        title = QLabel("Installation Options")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        subtitle = QLabel("Customize your installation with the options below.")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(subtitle)

        root.addSpacing(2)

        # ── Shortcuts section ────────────────────────────────
        section_title = QLabel("SHORTCUTS")
        section_title.setObjectName("SectionLabel")
        root.addWidget(section_title)

        shortcuts_card = QFrame()
        shortcuts_card.setObjectName("OptionsGroupCard")
        shortcuts_card.setFrameShape(QFrame.NoFrame)
        sc_layout = QVBoxLayout(shortcuts_card)
        sc_layout.setContentsMargins(0, 0, 0, 0)
        sc_layout.setSpacing(0)

        self._desktop_opt = _OptionCard(
            "desktop", "Desktop Shortcut",
            "Create a shortcut on the desktop for quick access.",
            checked=True,
        )
        sc_layout.addWidget(self._desktop_opt)

        sep1 = QFrame()
        sep1.setObjectName("OptionSep")
        sep1.setFrameShape(QFrame.HLine)
        sc_layout.addWidget(sep1)

        self._startmenu_opt = _OptionCard(
            "shortcut", "Start Menu Entry",
            "Add the application to the Windows Start Menu.",
            checked=True,
        )
        sc_layout.addWidget(self._startmenu_opt)

        sep2 = QFrame()
        sep2.setObjectName("OptionSep")
        sep2.setFrameShape(QFrame.HLine)
        sc_layout.addWidget(sep2)

        self._autostart_opt = _OptionCard(
            "auto_start", "Launch at Startup",
            "Automatically start the application when you log in.",
            checked=False,
        )
        sc_layout.addWidget(self._autostart_opt)

        root.addWidget(shortcuts_card)

        # ── Components section (from manifest) ───────────────
        self._component_opts: List[_OptionCard] = []
        if components:
            comp_title = QLabel("COMPONENTS")
            comp_title.setObjectName("SectionLabel")
            root.addWidget(comp_title)

            comp_card = QFrame()
            comp_card.setObjectName("OptionsGroupCard")
            comp_card.setFrameShape(QFrame.NoFrame)
            cc_layout = QVBoxLayout(comp_card)
            cc_layout.setContentsMargins(0, 0, 0, 0)
            cc_layout.setSpacing(0)

            for i, comp in enumerate(components):
                if i > 0:
                    sep = QFrame()
                    sep.setObjectName("OptionSep")
                    sep.setFrameShape(QFrame.HLine)
                    cc_layout.addWidget(sep)

                opt = _OptionCard(
                    comp.get("icon", "extension"),
                    comp.get("name", "Component"),
                    comp.get("description", ""),
                    checked=comp.get("default", True),
                )
                cc_layout.addWidget(opt)
                self._component_opts.append(opt)

            root.addWidget(comp_card)

        # ── Plugins section (discovered from plugins/) ────────
        self._plugin_ids: List[str] = []
        self._plugin_opts: List[_OptionCard] = []
        if plugins:
            plug_title = QLabel("PLUGINS")
            plug_title.setObjectName("SectionLabel")
            root.addWidget(plug_title)

            plug_card = QFrame()
            plug_card.setObjectName("OptionsGroupCard")
            plug_card.setFrameShape(QFrame.NoFrame)
            pc_layout = QVBoxLayout(plug_card)
            pc_layout.setContentsMargins(0, 0, 0, 0)
            pc_layout.setSpacing(0)

            for i, plug in enumerate(plugins):
                if i > 0:
                    sep = QFrame()
                    sep.setObjectName("OptionSep")
                    sep.setFrameShape(QFrame.HLine)
                    pc_layout.addWidget(sep)

                opt = _OptionCard(
                    plug.get("icon", "extension"),
                    plug.get("name", "Plugin"),
                    plug.get("description", ""),
                    checked=plug.get("default", True),
                )
                pc_layout.addWidget(opt)
                self._plugin_ids.append(plug.get("id", ""))
                self._plugin_opts.append(opt)

            root.addWidget(plug_card)

        root.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def get_options(self) -> Dict[str, Any]:
        selected_plugins = [
            pid for pid, opt in zip(self._plugin_ids, self._plugin_opts)
            if opt.checked
        ]
        return {
            "desktop_shortcut": self._desktop_opt.checked,
            "start_menu": self._startmenu_opt.checked,
            "auto_start": self._autostart_opt.checked,
            "components": [opt.checked for opt in self._component_opts],
            "selected_plugins": selected_plugins,
        }
