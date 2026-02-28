"""
Nova Installer — Application orchestration.

Reads installer.json, creates all pages, wires signals, and runs the wizard.
Detects existing installations and offers maintenance options.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from installer.core.config import InstallerConfig, discover_plugins
from installer.core.engine import (
    InstallConfig, InstallationEngine,
    detect_existing_install, load_install_info,
)
from installer.core.icons import IconManager
from installer.core.style import StyleManager
from installer.pages.finish_page import FinishPage
from installer.pages.install_type_page import InstallTypePage
from installer.pages.license_page import LicensePage
from installer.pages.maintenance_page import MaintenancePage
from installer.pages.options_page import OptionsPage
from installer.pages.path_page import PathPage
from installer.pages.progress_page import ProgressPage
from installer.pages.welcome_page import WelcomePage
from installer.ui.installer_window import InstallerWindow

_log = logging.getLogger(__name__)


def run(config_path: Path) -> None:
    """Main entry point for the installer."""
    app = QApplication.instance() or QApplication(sys.argv)

    # ── Load manifest ──────────────────────────────────────
    cfg = InstallerConfig.load(config_path)
    manifest = cfg.manifest

    # ── Initialise styling ─────────────────────────────────
    style = StyleManager()
    style.initialise(accent_hex=manifest.accent_color, theme="light")

    # ── Set app icon ──────────────────────────────────────────
    app.setWindowIcon(IconManager.get_app_icon())

    qss_path = Path(__file__).parent / "resources" / "installer.qss"
    if qss_path.exists():
        style.apply_theme(app, qss_path.read_text(encoding="utf-8"))
    else:
        _log.warning("installer.qss not found at %s", qss_path)

    # ── Resolve source dir relative to manifest ────────────
    source_dir = Path(manifest.source_dir)
    if not source_dir.is_absolute():
        source_dir = config_path.parent / source_dir

    # ── Resolve license file ───────────────────────────────
    license_file = ""
    if manifest.license_file:
        lp = Path(manifest.license_file)
        if not lp.is_absolute():
            lp = config_path.parent / lp
        if lp.exists():
            license_file = str(lp)

    # ── Detect existing installation ───────────────────────
    reg_key = manifest.registry_key or manifest.name.replace(" ", "")
    existing_path = detect_existing_install(reg_key)

    # ── Engine ─────────────────────────────────────────────
    engine = InstallationEngine()

    # ── Create window ──────────────────────────────────────
    window = InstallerWindow()
    window.set_app_info(manifest.name, manifest.version)

    if existing_path:
        _run_maintenance_mode(
            app, window, engine, manifest, cfg, source_dir,
            existing_path, reg_key,
        )
    else:
        _run_install_mode(
            app, window, engine, manifest, cfg, source_dir,
            license_file, reg_key,
        )


def _build_install_config(manifest, source_dir, install_path,
                           install_type="user", opts=None):
    """Build InstallConfig from manifest and UI state."""
    ic = InstallConfig()
    ic.app_name = manifest.name
    ic.app_version = manifest.version
    ic.author = manifest.author
    ic.install_path = install_path
    ic.install_type = install_type
    ic.source_dir = str(source_dir)
    ic.include_patterns = manifest.include_patterns
    ic.exclude_patterns = manifest.exclude_patterns
    ic.requirements_file = manifest.requirements_file
    ic.create_venv = manifest.create_venv
    ic.entry_script = manifest.entry_script
    ic.registry_key = manifest.registry_key

    # PyInstaller settings
    ic.use_pyinstaller = manifest.use_pyinstaller
    ic.pyinstaller_onefile = manifest.pyinstaller_onefile
    ic.pyinstaller_console = manifest.pyinstaller_console
    ic.pyinstaller_icon = manifest.pyinstaller_icon
    ic.pyinstaller_extra_args = manifest.pyinstaller_extra_args
    ic.pyinstaller_hidden_imports = manifest.pyinstaller_hidden_imports
    ic.pyinstaller_data_files = manifest.pyinstaller_data_files
    ic.resource_dirs = manifest.pyinstaller_resource_dirs

    if opts:
        ic.desktop_shortcut = opts["desktop_shortcut"]
        ic.start_menu = opts["start_menu"]
        ic.auto_start = opts["auto_start"]
        ic.components = opts["components"]
        ic.selected_plugins = opts.get("selected_plugins")

    ic.run_after_install = manifest.run_after_install
    return ic


# ── Fresh install flow ─────────────────────────────────────────

def _run_install_mode(app, window, engine, manifest, cfg,
                      source_dir, license_file, reg_key):
    """Standard installation flow."""

    # Discover plugins from source directory
    discovered_plugins = discover_plugins(source_dir)

    welcome = WelcomePage(
        app_name=manifest.name,
        app_version=manifest.version,
        description=manifest.description,
    )
    license_pg = LicensePage(license_file=license_file)
    install_type_pg = InstallTypePage()
    path_pg = PathPage(
        app_name=manifest.name,
        default_dir=manifest.default_install_dir,
    )
    options_pg = OptionsPage(
        components=manifest.components,
        plugins=discovered_plugins,
    )
    progress_pg = ProgressPage()
    finish_pg = FinishPage(app_name=manifest.name)

    window.add_page("Welcome", welcome)
    window.add_page("License", license_pg)
    window.add_page("Install Type", install_type_pg)
    window.add_page("Location", path_pg)
    window.add_page("Options", options_pg)
    window.add_page("Installing", progress_pg)
    window.add_page("Complete", finish_pg)

    window.set_install_step(5)
    window.finalise()

    # Sync install type → path page
    install_type_pg.type_changed.connect(path_pg.set_install_type)

    # Disable Next when license checkbox is unchecked
    def _on_license_toggled(accepted: bool):
        if window._current_index == 1:  # License page
            window._bottom.set_next_enabled(accepted)

    license_pg.accepted_changed.connect(_on_license_toggled)

    # Also update Next state when navigating; hide Next on welcome page
    _orig_update_nav = window._update_nav

    def _patched_update_nav():
        _orig_update_nav()
        if window._current_index == 0:
            # Welcome page uses its own Install Now / Customize buttons
            window._bottom.set_next_visible(False)
        if window._current_index == 1 and not window._is_finished:
            window._bottom.set_next_enabled(license_pg._accepted)

    window._update_nav = _patched_update_nav

    # ── Fast-forward: Install Now (skip to progress with defaults) ──
    def _on_install_now():
        ic = _build_install_config(
            manifest, source_dir,
            path_pg.install_path,  # default path
            "user",
        )
        ic.desktop_shortcut = True
        ic.start_menu = True
        ic.auto_start = False
        ic.components = [c["name"] for c in manifest.components]
        ic.selected_plugins = [p["id"] for p in discovered_plugins]
        window.navigate(5)  # jump to progress page

    welcome.install_now.connect(_on_install_now)

    # Customize: normal wizard flow starting at License page
    welcome.customize.connect(lambda: window.navigate(1))

    # Hook navigation to trigger install
    _original_navigate = window.navigate

    def _hooked_navigate(index: int):
        _original_navigate(index)
        if index == 5:
            window.set_installing(True)
            ic = _build_install_config(
                manifest, source_dir,
                path_pg.install_path,
                install_type_pg.install_type,
                options_pg.get_options(),
            )
            progress_pg.reset()
            engine.start(ic)

    window.navigate = _hooked_navigate

    # Cancel during installation → engine.cancel()
    window.cancel_install.connect(engine.cancel)

    # Engine → progress page
    engine.progress.connect(progress_pg.set_progress)
    engine.operation.connect(progress_pg.set_operation)
    engine.log_message.connect(progress_pg.append_log)
    engine.error_message.connect(finish_pg.set_error_detail)

    def _on_install_finished(success: bool):
        progress_pg.set_completed(success)
        finish_pg.set_success(success)
        window.set_installing(False)
        window.set_finished(True)
        window.navigate(6)

    engine.finished.connect(_on_install_finished)

    # Finish → launch app
    def _on_finish():
        if finish_pg.launch_after:
            install_dir = Path(path_pg.install_path)
            if manifest.use_pyinstaller:
                exe_name = manifest.name.replace(" ", "") + ".exe"
                target = install_dir / exe_name
                if target.exists():
                    subprocess.Popen([str(target)], cwd=str(install_dir))
            elif manifest.entry_script:
                target = install_dir / manifest.entry_script
                if target.exists():
                    subprocess.Popen(
                        [sys.executable, str(target)],
                        cwd=str(install_dir),
                    )

    window.finished.connect(_on_finish)

    # Show
    window.navigate(0)
    window.show()
    sys.exit(app.exec())


# ── Maintenance flow ───────────────────────────────────────────

def _run_maintenance_mode(app, window, engine, manifest, cfg,
                          source_dir, existing_path, reg_key):
    """Maintenance flow: Modify, Repair, Update, or Uninstall."""

    discovered_plugins = discover_plugins(source_dir)

    maintenance_pg = MaintenancePage(
        app_name=manifest.name,
        install_path=existing_path,
    )
    options_pg = OptionsPage(
        components=manifest.components,
        plugins=discovered_plugins,
    )
    progress_pg = ProgressPage()
    finish_pg = FinishPage(app_name=manifest.name)

    window.add_page("Maintenance", maintenance_pg)
    window.add_page("Options", options_pg)
    window.add_page("Processing", progress_pg)
    window.add_page("Complete", finish_pg)

    window.set_install_step(2)  # Progress page is at index 2
    window.finalise()

    # Load saved install info for repair
    saved_info = load_install_info(existing_path)

    # Track the current action
    current_action = {"value": "repair"}

    def _on_action_changed(action: str):
        current_action["value"] = action

    maintenance_pg.action_changed.connect(_on_action_changed)

    # Hook navigation
    _original_navigate = window.navigate

    def _hooked_navigate(index: int):
        action = current_action["value"]

        # Skip options page for repair/update/uninstall
        if index == 1 and action in ("repair", "update", "uninstall"):
            _original_navigate(2)
            _start_action(action)
            return

        _original_navigate(index)

        if index == 2:
            _start_action(action)

    def _start_action(action: str):
        window.set_installing(True)
        progress_pg.reset()

        if action == "uninstall":
            progress_pg._title.setText("Uninstalling...")
            progress_pg._subtitle.setText(
                f"Removing {manifest.name} from your computer."
            )
            engine.start_uninstall(manifest.name, existing_path, reg_key)

        elif action in ("repair", "update"):
            progress_pg._title.setText(
                "Repairing..." if action == "repair" else "Updating..."
            )
            progress_pg._subtitle.setText(
                "Please wait while the application is being re-installed."
            )
            ic = _build_install_config(
                manifest, source_dir, existing_path,
                saved_info.get("install_type", "user") if saved_info else "user",
            )
            # Use saved shortcut preferences for repair
            if saved_info:
                ic.desktop_shortcut = saved_info.get("desktop_shortcut", True)
                ic.start_menu = saved_info.get("start_menu", True)
                ic.auto_start = saved_info.get("auto_start", False)
            engine.start(ic)

        elif action == "modify":
            ic = _build_install_config(
                manifest, source_dir, existing_path,
                saved_info.get("install_type", "user") if saved_info else "user",
                options_pg.get_options(),
            )
            engine.start(ic)

    window.navigate = _hooked_navigate

    # Cancel during operation → engine.cancel()
    window.cancel_install.connect(engine.cancel)

    # Engine → progress page
    engine.progress.connect(progress_pg.set_progress)
    engine.operation.connect(progress_pg.set_operation)
    engine.log_message.connect(progress_pg.append_log)
    engine.error_message.connect(finish_pg.set_error_detail)

    def _on_finished(success: bool):
        action = current_action["value"]
        progress_pg.set_completed(success)

        if action == "uninstall":
            if success:
                finish_pg.set_uninstall_success(manifest.name)
            else:
                finish_pg.set_success(False)
        else:
            finish_pg.set_success(success)

        window.set_installing(False)
        window.set_finished(True)
        window.navigate(3)  # Complete page

    engine.finished.connect(_on_finished)

    window.finished.connect(lambda: None)

    # Show
    window.navigate(0)
    window.show()
    sys.exit(app.exec())
