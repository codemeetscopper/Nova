from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from nova.core.paths import get_app_root
from nova.core.plugin_manager import PluginManager
from nova.pages.about_page import AboutPage
from nova.pages.home_page import HomePage
from nova.pages.log_page import LogPage
from nova.pages.plugins_page import PluginsPage
from nova.pages.settings_page import SettingsPage
from nova.ui.main_window import MainWindow

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_plugins_dir(config) -> Path:
    try:
        raw = config.get_value("system.plugins_path", "./plugins")
    except Exception:
        raw = "./plugins"
    p = Path(raw)
    if not p.is_absolute():
        p = get_app_root() / p
    return p


def _apply_font_from_config(config, app) -> None:
    try:
        path = config.get_value("appearance.font", "")
        if path:
            p = Path(path)
            if p.exists() and p.suffix.lower() in (".ttf", ".otf"):
                from PySide6.QtGui import QFont, QFontDatabase
                from nova.core.style import StyleManager
                fid = QFontDatabase.addApplicationFont(str(p))
                families = QFontDatabase.applicationFontFamilies(fid)
                if families:
                    StyleManager.set_font_family(families[0])
                    app.setFont(QFont(families[0]))
    except Exception as exc:
        _log.warning("Font load failed at startup: %s", exc)


def _wire_pm_signals(pm, home, window, plugins_pg, settings) -> None:
    def _update_home(*_):
        home.update_stats(pm.loaded_count(), pm.active_count())

    pm.plugin_loaded.connect(_update_home)
    pm.plugin_started.connect(_update_home)
    pm.plugin_stopped.connect(_update_home)
    pm.plugin_crashed.connect(_update_home)
    pm.plugin_deleted.connect(_update_home)
    pm.plugin_imported.connect(_update_home)
    _update_home()

    # Update header status + action bar when plugin state changes
    pm.plugin_started.connect(lambda pid: window.update_plugin_status(pid, True))
    pm.plugin_stopped.connect(lambda pid: window.update_plugin_status(pid, False))
    pm.plugin_crashed.connect(lambda pid, _msg: window.update_plugin_status(pid, False))

    # Sync favorite icon in header/detached action bars
    pm.plugin_favorite_changed.connect(lambda pid, fav: window.update_plugin_favorite(pid, fav))

    def _on_navigate(pid: str):
        page_id = f"plugin_{pid}"
        if page_id in window._pages or window.is_detached(page_id):
            window.navigate(page_id)

    plugins_pg.navigate_to_plugin.connect(_on_navigate)

    def _on_favorite_changed(pid: str, is_fav: bool):
        page_id = f"plugin_{pid}"
        if page_id not in window._pages and not window.is_detached(page_id):
            return
        record = pm._records.get(pid)
        if record is None:
            return
        if is_fav:
            window.show_plugin_in_sidebar(page_id, record.manifest.name,
                                           record.manifest.icon or "extension")
        else:
            window.hide_plugin_from_sidebar(page_id)

    pm.plugin_favorite_changed.connect(_on_favorite_changed)

    def _on_plugin_imported(pid: str):
        if pm.load(pid):
            widget = pm.create_widget(pid)
            if widget is not None:
                record = pm._records.get(pid)
                title = record.manifest.name if record else pid
                icon = record.manifest.icon if record else "extension"
                window.add_plugin_page(f"plugin_{pid}", title, icon, widget,
                                       pm.is_favorite(pid))
        plugins_pg.refresh()
        _update_home()

    pm.plugin_imported.connect(_on_plugin_imported)

    def _on_plugin_deleted(pid: str):
        window.remove_plugin_page(f"plugin_{pid}")
        _update_home()

    pm.plugin_deleted.connect(_on_plugin_deleted)


def _do_plugin_hot_reload(ctx, new_path_str: str, old_pm,
                          window, plugins_pg, settings, home) -> PluginManager:
    old_pm.stop_all()
    # Dock all detached windows before reload
    window.dock_all()
    for pid in list(window._pages.keys()):
        if pid.startswith("plugin_"):
            window.remove_plugin_page(pid)

    new_path = Path(new_path_str)
    if not new_path.is_absolute():
        new_path = get_app_root() / new_path

    new_pm = PluginManager(ctx, new_path)
    window._pm = new_pm
    plugins_pg.update_plugin_manager(new_pm)
    settings.update_plugin_manager(new_pm)
    _wire_pm_signals(new_pm, home, window, plugins_pg, settings)

    for manifest in new_pm.discover():
        if new_pm.load(manifest.id):
            widget = new_pm.create_widget(manifest.id)
            if widget is not None:
                window.add_plugin_page(
                    f"plugin_{manifest.id}", manifest.name,
                    manifest.icon or "extension", widget,
                    in_sidebar=new_pm.is_favorite(manifest.id),
                )
            new_pm.start(manifest.id)
    plugins_pg.refresh()
    return new_pm


def _cascade_theme_to_plugins(pm, ctx) -> None:
    """Notify all loaded plugins that the theme has changed."""
    for record in pm._records.values():
        if record.plugin is not None:
            try:
                record.plugin.on_theme_changed(ctx.style)
            except Exception as exc:
                _log.debug("on_theme_changed failed for %s: %s", record.manifest.id, exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(ctx) -> None:
    app = QApplication.instance() or QApplication(sys.argv)

    # Set application-level icon (taskbar, window headers, Alt-Tab)
    from nova.core.icons import IconManager
    accent = ctx.config.get_value("appearance.accent", "#0088CC")
    app.setWindowIcon(IconManager.get_app_icon(primary=accent))

    _apply_font_from_config(ctx.config, app)

    nova_qss = Path(__file__).parent /"resources" / "nova.qss"
    if nova_qss.exists():
        ctx.style.apply_theme(app, nova_qss.read_text(encoding="utf-8"))
    else:
        _log.warning("nova.qss not found at %s — running unstyled", nova_qss)

    from PySide6.QtCore import qInstallMessageHandler, QtMsgType

    def _qt_msg(mode, context, message):
        if mode == QtMsgType.QtInfoMsg:     _log.info("[Qt] %s", message)
        elif mode == QtMsgType.QtWarningMsg:  _log.warning("[Qt] %s", message)
        elif mode == QtMsgType.QtCriticalMsg: _log.error("[Qt] %s", message)
        elif mode == QtMsgType.QtFatalMsg:    _log.critical("[Qt] %s", message)
        else:                                 _log.debug("[Qt] %s", message)

    qInstallMessageHandler(_qt_msg)

    plugins_dir = _resolve_plugins_dir(ctx.config)
    pm = PluginManager(ctx, plugins_dir)

    home      = HomePage(ctx)
    plugins_pg = PluginsPage(pm)
    settings  = SettingsPage(ctx, pm)
    log_pg    = LogPage(ctx)
    about     = AboutPage(ctx)

    window = MainWindow(ctx, pm)

    window.add_page("home",    "Home",    "home",      home)
    window.add_page("plugins", "Plugins", "extension", plugins_pg)
    window.add_separator()
    window.add_page("settings", "Settings", "settings", settings)
    window.add_page("logs",     "Logs",     "file",     log_pg)
    window.add_page("about",    "About",    "info",     about)

    for manifest in pm.discover():
        if pm.load(manifest.id):
            widget = pm.create_widget(manifest.id)
            if widget is not None:
                window.add_plugin_page(
                    f"plugin_{manifest.id}", manifest.name,
                    manifest.icon or "extension", widget,
                    in_sidebar=pm.is_favorite(manifest.id),
                )
            # pm.start(manifest.id)

    plugins_pg.refresh()
    _wire_pm_signals(pm, home, window, plugins_pg, settings)

    # ── Style change: sidebar + plugin cards + plugin instances + detached ──
    def _on_style_changed():
        window._sidebar.refresh_colors()
        window._header.refresh_icons()
        window.refresh_detached_themes()
        plugins_pg.refresh_icons()
        _cascade_theme_to_plugins(pm, ctx)

    settings.style_changed.connect(_on_style_changed)

    # ── Plugins path hot-reload ───────────────────────────────────────────
    def _on_plugins_path_changed(new_path: str):
        nonlocal pm
        pm = _do_plugin_hot_reload(ctx, new_path, pm, window, plugins_pg, settings, home)

    settings.plugins_path_changed.connect(_on_plugins_path_changed)

    window.navigate("home")
    window.resize(1280, 780)
    window.show()

    sys.exit(app.exec())
