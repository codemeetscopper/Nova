"""
Installation engine — handles PyInstaller builds, file operations, shortcut
creation, registry entries, uninstaller generation, and maintenance operations.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Signal

_log = logging.getLogger(__name__)


# ── Utility: detect existing installation ──────────────────────

def detect_existing_install(registry_key: str) -> Optional[str]:
    """Check if app is already installed. Returns install path or None."""
    try:
        import winreg
        key_path = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{registry_key}"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        install_path, _ = winreg.QueryValueEx(key, "InstallLocation")
        winreg.CloseKey(key)
        if install_path and Path(install_path).exists():
            return install_path
    except Exception:
        pass
    return None


def load_install_info(install_path: str) -> Optional[Dict[str, Any]]:
    """Load saved install info from a previous installation."""
    info_file = Path(install_path) / ".install_info.json"
    if info_file.exists():
        try:
            return json.loads(info_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


# ── Install Worker ─────────────────────────────────────────────

class InstallWorker(QObject):
    """Runs the installation in a background thread."""

    progress = Signal(int)         # 0-100
    operation = Signal(str)        # current operation text
    log_message = Signal(str)      # log line
    error_message = Signal(str)    # error detail on failure
    finished = Signal(bool)        # success

    def __init__(self, config: "InstallConfig"):
        super().__init__()
        self._config = config
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        cfg = self._config
        try:
            self._log("Starting installation...")
            self._do_install(cfg)
            if self._cancelled:
                self._log("Installation cancelled by user.")
                self.operation.emit("Cleaning up...")
                self._cleanup_partial_install(cfg)
                self.finished.emit(False)
            else:
                self.finished.emit(True)
        except Exception as e:
            self._log(f"ERROR: {e}")
            _log.error("Installation failed: %s", e, exc_info=True)
            self.error_message.emit(str(e))
            self.finished.emit(False)

    def _do_install(self, cfg: "InstallConfig"):
        if cfg.use_pyinstaller:
            # If installer is frozen, use pre-built app bundled inside the exe
            if getattr(sys, "frozen", False):
                self._do_prebuild_install(cfg)
            else:
                self._do_pyinstaller_install(cfg)
        else:
            self._do_copy_install(cfg)

    # ── Pre-built installation (frozen installer) ────────────────

    def _do_prebuild_install(self, cfg: "InstallConfig"):
        """Install from pre-built app bundled inside the installer exe."""
        total_steps = 4
        step = 0

        # Locate the bundled pre-built app
        meipass = Path(sys._MEIPASS)
        prebuild_dir = meipass / "_nova_app"
        if not prebuild_dir.exists():
            msg = "Pre-built application data not found in installer."
            self._log(f"  ERROR: {msg}")
            self.error_message.emit(msg)
            self.finished.emit(False)
            return

        # Step 1: Prepare install directory
        step += 1
        self._update(step, total_steps, "Preparing installation directory...")
        install_dir = Path(cfg.install_path)
        if install_dir.exists() and any(install_dir.iterdir()):
            self._log("  Cleaning existing installation directory...")
            self._clean_install_dir(install_dir)
        install_dir.mkdir(parents=True, exist_ok=True)
        self._log(f"  Install directory: {install_dir}")

        if self._cancelled:
            return

        # Step 2: Copy pre-built application files
        step += 1
        self._update(step, total_steps, "Installing application files...")
        app_name = cfg.app_name.replace(" ", "")
        cfg._built_exe_name = f"{app_name}.exe"

        copied = 0
        for item in prebuild_dir.rglob("*"):
            if item.is_file():
                rel = item.relative_to(prebuild_dir)
                dest_file = install_dir / rel
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest_file)
                copied += 1
                if copied % 50 == 0:
                    self._log(f"  Copied {copied} files...")
                    pct = int(step / total_steps * 100 * 0.5 +
                              (copied / max(1, copied + 100)) * 50)
                    self.progress.emit(min(pct, 95))
            if self._cancelled:
                return

        self._log(f"  Installed {copied} files to {install_dir}")

        if self._cancelled:
            return

        # Step 3: Create shortcuts
        step += 1
        self._update(step, total_steps, "Creating shortcuts...")
        if cfg.desktop_shortcut:
            self._create_shortcut_exe(cfg, "desktop")
        if cfg.start_menu:
            self._create_shortcut_exe(cfg, "start_menu")
        if cfg.auto_start:
            self._create_autostart_exe(cfg)

        if self._cancelled:
            return

        # Step 4: Registry, uninstaller, save manifest
        step += 1
        self._update(step, total_steps, "Registering application...")
        self._write_uninstall_info(cfg)
        self._generate_uninstaller(cfg)
        self._save_install_info(cfg)

        self._update(total_steps, total_steps, "Installation complete!")
        self._log("Installation finished successfully.")

    # ── PyInstaller-based installation (dev mode) ────────────────

    def _do_pyinstaller_install(self, cfg: "InstallConfig"):
        total_steps = 6
        step = 0

        # Step 1: Prepare install directory
        step += 1
        self._update(step, total_steps, "Preparing installation directory...")
        install_dir = Path(cfg.install_path)
        if install_dir.exists() and any(install_dir.iterdir()):
            self._log("  Cleaning existing installation directory...")
            self._clean_install_dir(install_dir)
        install_dir.mkdir(parents=True, exist_ok=True)
        self._log(f"  Install directory: {install_dir}")

        if self._cancelled:
            return

        # Step 2: Build with PyInstaller
        step += 1
        self._update(step, total_steps, "Building application with PyInstaller...")
        source = Path(cfg.source_dir)
        entry = source / cfg.entry_script if cfg.entry_script else None

        if not entry or not entry.exists():
            msg = f"Entry script not found: {entry}"
            self._log(f"  ERROR: {msg}")
            self.error_message.emit(msg)
            self.finished.emit(False)
            return

        build_dir = Path(tempfile.mkdtemp(prefix="nova_build_"))
        dist_dir = build_dir / "dist"
        work_dir = build_dir / "build"

        try:
            exe_path = self._run_pyinstaller(
                cfg, entry, source, dist_dir, work_dir
            )
        except Exception as e:
            msg = f"PyInstaller build failed: {e}"
            self._log(f"  {msg}")
            self.error_message.emit(msg)
            self.finished.emit(False)
            return

        if self._cancelled:
            return

        # Step 3: Copy built files to install directory
        step += 1
        self._update(step, total_steps, "Copying built application...")
        if exe_path and exe_path.exists():
            if cfg.pyinstaller_onefile:
                dest_exe = install_dir / exe_path.name
                shutil.copy2(exe_path, dest_exe)
                cfg._built_exe_name = exe_path.name
                self._log(f"  Copied {exe_path.name} to {install_dir}")
            else:
                app_folder = exe_path.parent
                copied = 0
                for item in app_folder.rglob("*"):
                    if item.is_file():
                        rel = item.relative_to(app_folder)
                        dest_file = install_dir / rel
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest_file)
                        copied += 1
                        if copied % 100 == 0:
                            self._log(f"  Copied {copied} files...")
                cfg._built_exe_name = exe_path.name
                self._log(f"  Copied {copied} files to {install_dir}")
        else:
            self._log("  WARNING: No executable found after build")
            cfg._built_exe_name = ""

        # Clean up temp build dir
        try:
            shutil.rmtree(build_dir, ignore_errors=True)
        except Exception:
            pass

        if self._cancelled:
            return

        # Step 4: Copy resource directories
        step += 1
        self._update(step, total_steps, "Copying resources...")
        source = Path(cfg.source_dir)
        self._copy_resource_dirs(cfg.resource_dirs, source, install_dir)

        if self._cancelled:
            return

        # Step 5: Create shortcuts (pointing to .exe)
        step += 1
        self._update(step, total_steps, "Creating shortcuts...")
        if cfg.desktop_shortcut:
            self._create_shortcut_exe(cfg, "desktop")
        if cfg.start_menu:
            self._create_shortcut_exe(cfg, "start_menu")
        if cfg.auto_start:
            self._create_autostart_exe(cfg)

        if self._cancelled:
            return

        # Step 6: Registry, uninstaller, save manifest
        step += 1
        self._update(step, total_steps, "Registering application...")
        self._write_uninstall_info(cfg)
        self._generate_uninstaller(cfg)
        self._save_install_info(cfg)

        self._update(total_steps, total_steps, "Installation complete!")
        self._log("Installation finished successfully.")

    def _run_pyinstaller(self, cfg: "InstallConfig", entry: Path,
                          source: Path, dist_dir: Path,
                          work_dir: Path) -> Optional[Path]:
        """Run PyInstaller with real-time verbose output."""
        app_name = cfg.app_name.replace(" ", "")

        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--name", app_name,
            "--distpath", str(dist_dir),
            "--workpath", str(work_dir),
            "--specpath", str(work_dir),
            "--noconfirm",
            "--clean",
        ]

        if cfg.pyinstaller_onefile:
            cmd.append("--onefile")
        else:
            cmd.append("--onedir")

        if not cfg.pyinstaller_console:
            cmd.append("--noconsole")

        if cfg.pyinstaller_icon:
            icon_path = Path(cfg.pyinstaller_icon)
            if not icon_path.is_absolute():
                icon_path = source / icon_path
            if icon_path.exists():
                cmd.extend(["--icon", str(icon_path)])

        for imp in cfg.pyinstaller_hidden_imports:
            cmd.extend(["--hidden-import", imp])

        for data in cfg.pyinstaller_data_files:
            # Resolve relative source paths to absolute (relative to source dir)
            parts = data.split(";") if ";" in data else data.split(":")
            if len(parts) == 2:
                src_path = Path(parts[0])
                if not src_path.is_absolute():
                    src_path = source / src_path
                data = f"{src_path}{os.pathsep}{parts[1]}"
            cmd.extend(["--add-data", data])

        cmd.extend(cfg.pyinstaller_extra_args)
        cmd.append(str(entry))

        self._log(f"  Building: {app_name}")
        self._log(f"  Entry: {entry}")
        self._log(f"  Mode: {'onefile' if cfg.pyinstaller_onefile else 'onedir'}")
        self._log(f"  Hidden imports: {len(cfg.pyinstaller_hidden_imports)}")
        self._log(f"  Data files: {len(cfg.pyinstaller_data_files)}")
        self._log("")

        # Stream output in real-time using Popen
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(source),
            bufsize=1,
        )

        for line in process.stdout:
            line = line.rstrip()
            if line:
                self._log(f"  [build] {line}")
            if self._cancelled:
                process.kill()
                return None

        process.wait()

        if process.returncode != 0:
            raise RuntimeError(
                f"PyInstaller exited with code {process.returncode}"
            )

        self._log("")
        self._log("  Build completed successfully!")

        # Find the built executable
        if cfg.pyinstaller_onefile:
            exe = dist_dir / f"{app_name}.exe"
            if not exe.exists():
                exe = dist_dir / app_name
        else:
            exe = dist_dir / app_name / f"{app_name}.exe"
            if not exe.exists():
                exe = dist_dir / app_name / app_name

        self._log(f"  Executable: {exe}")
        return exe

    # ── Resource directory copying ─────────────────────────────

    def _copy_resource_dirs(self, resource_dirs: List[str],
                             source: Path, install_dir: Path):
        """Copy resource directories from source to install dir."""
        if not resource_dirs:
            self._log("  No resource directories to copy")
            return

        for dir_name in resource_dirs:
            src = source / dir_name
            dst = install_dir / dir_name
            if src.exists() and src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(
                    src, dst,
                    ignore=shutil.ignore_patterns(
                        "__pycache__", "*.pyc", ".git"
                    ),
                )
                count = sum(1 for _ in dst.rglob("*") if _.is_file())
                self._log(f"  Copied resource directory: {dir_name} ({count} files)")
            else:
                self._log(f"  Resource directory not found: {src}")

    # ── File-copy-based installation (fallback) ────────────────

    def _do_copy_install(self, cfg: "InstallConfig"):
        total_steps = 5
        step = 0

        # Step 1: Prepare install directory
        step += 1
        self._update(step, total_steps, "Preparing installation directory...")
        install_dir = Path(cfg.install_path)
        if install_dir.exists() and any(install_dir.iterdir()):
            self._log("  Cleaning existing installation directory...")
            self._clean_install_dir(install_dir)
        install_dir.mkdir(parents=True, exist_ok=True)
        self._log(f"  Install directory: {install_dir}")

        if self._cancelled:
            return

        # Step 2: Copy files
        step += 1
        self._update(step, total_steps, "Copying application files...")
        source = Path(cfg.source_dir)
        if source.exists():
            copied = self._copy_files(source, install_dir,
                                       cfg.include_patterns, cfg.exclude_patterns)
            self._log(f"  Copied {copied} files")
        else:
            self._log(f"  Source directory not found: {source}")

        if self._cancelled:
            return

        # Step 3: Install requirements
        step += 1
        if cfg.requirements_file:
            self._update(step, total_steps, "Installing Python dependencies...")
            req_path = install_dir / cfg.requirements_file
            if req_path.exists():
                self._install_requirements(req_path, install_dir, cfg.create_venv)
            else:
                self._log(f"  Requirements file not found: {req_path}")
        else:
            self._update(step, total_steps, "Skipping dependencies (none specified)...")
            self._log("  No requirements file specified")

        if self._cancelled:
            return

        # Step 4: Create shortcuts
        step += 1
        self._update(step, total_steps, "Creating shortcuts...")
        if cfg.desktop_shortcut:
            self._create_shortcut(cfg, "desktop")
        if cfg.start_menu:
            self._create_shortcut(cfg, "start_menu")
        if cfg.auto_start:
            self._create_autostart(cfg)

        if self._cancelled:
            return

        # Step 5: Registry & uninstaller
        step += 1
        self._update(step, total_steps, "Registering application...")
        self._write_uninstall_info(cfg)
        self._generate_uninstaller(cfg)
        self._save_install_info(cfg)

        self._update(total_steps, total_steps, "Installation complete!")
        self._log("Installation finished successfully.")

    def _copy_files(self, source: Path, dest: Path,
                    includes: List[str], excludes: List[str]) -> int:
        count = 0
        for item in source.rglob("*"):
            if not item.is_file():
                continue
            rel = item.relative_to(source)
            rel_str = str(rel)

            excluded = False
            for pattern in excludes:
                if fnmatch(rel_str, pattern) or fnmatch(item.name, pattern):
                    excluded = True
                    break
                for part in rel.parts:
                    if fnmatch(part, pattern):
                        excluded = True
                        break
                if excluded:
                    break
            if excluded:
                continue

            included = False
            for pattern in includes:
                if fnmatch(rel_str, pattern) or fnmatch(item.name, pattern):
                    included = True
                    break
            if not included and includes != ["**/*"]:
                continue

            dest_file = dest / rel
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest_file)
            count += 1
            if count % 50 == 0:
                self._log(f"  Copied {count} files...")

        return count

    def _install_requirements(self, req_path: Path, install_dir: Path,
                               create_venv: bool):
        if create_venv:
            venv_dir = install_dir / ".venv"
            self._log(f"  Creating virtual environment: {venv_dir}")
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                capture_output=True, text=True,
            )
            pip = venv_dir / "Scripts" / "pip.exe"
        else:
            pip = Path(sys.executable).parent / "pip.exe"
            if not pip.exists():
                pip = "pip"

        self._log(f"  Installing requirements from {req_path.name}...")
        result = subprocess.run(
            [str(pip), "install", "-r", str(req_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            self._log(f"  pip install failed: {result.stderr[:500]}")
        else:
            self._log("  Dependencies installed successfully")

    # ── Install directory management ───────────────────────────

    def _clean_install_dir(self, install_dir: Path):
        """Remove contents of install directory, preserving the dir itself."""
        for item in install_dir.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
            except Exception as e:
                self._log(f"  Warning: could not remove {item.name}: {e}")

    def _cleanup_partial_install(self, cfg: "InstallConfig"):
        """Remove partially installed files after cancellation."""
        install_dir = Path(cfg.install_path)
        if install_dir.exists():
            try:
                self._log(f"  Removing partial installation at {install_dir}")
                shutil.rmtree(install_dir, ignore_errors=True)
                if install_dir.exists():
                    self._log("  Warning: some files could not be removed")
                else:
                    self._log("  Partial installation removed successfully")
            except Exception as e:
                self._log(f"  Warning: cleanup failed: {e}")

    def _save_install_info(self, cfg: "InstallConfig"):
        """Save installation details for repair/modify operations."""
        install_dir = Path(cfg.install_path)
        info = {
            "app_name": cfg.app_name,
            "app_version": cfg.app_version,
            "author": cfg.author,
            "install_path": cfg.install_path,
            "install_type": cfg.install_type,
            "registry_key": cfg.registry_key,
            "use_pyinstaller": cfg.use_pyinstaller,
            "desktop_shortcut": cfg.desktop_shortcut,
            "start_menu": cfg.start_menu,
            "auto_start": cfg.auto_start,
            "entry_script": cfg.entry_script,
            "source_dir": cfg.source_dir,
            "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        info_file = install_dir / ".install_info.json"
        info_file.write_text(json.dumps(info, indent=2), encoding="utf-8")
        self._log("  Saved installation manifest")

    # ── Shortcuts for exe-based installs ────────────────────────

    def _create_shortcut_exe(self, cfg: "InstallConfig", location: str):
        try:
            install_dir = Path(cfg.install_path)
            exe_name = getattr(cfg, "_built_exe_name", "") or f"{cfg.app_name}.exe"
            target_exe = install_dir / exe_name

            if location == "desktop":
                link_dir = Path(os.path.expandvars(r"%USERPROFILE%\Desktop"))
            else:
                link_dir = Path(os.path.expandvars(
                    r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"
                ))

            link_path = link_dir / f"{cfg.app_name}.lnk"
            ps_script = (
                f'$ws = New-Object -ComObject WScript.Shell; '
                f'$s = $ws.CreateShortcut("{link_path}"); '
                f'$s.TargetPath = "{target_exe}"; '
                f'$s.WorkingDirectory = "{install_dir}"; '
                f'$s.Description = "{cfg.app_name}"; '
                f'$s.Save()'
            )
            subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True, text=True,
            )
            self._log(f"  Created shortcut: {link_path}")
        except Exception as e:
            self._log(f"  Failed to create shortcut ({location}): {e}")

    def _create_autostart_exe(self, cfg: "InstallConfig"):
        try:
            import winreg
            install_dir = Path(cfg.install_path)
            exe_name = getattr(cfg, "_built_exe_name", "") or f"{cfg.app_name}.exe"
            target_exe = install_dir / exe_name

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE,
            )
            winreg.SetValueEx(key, cfg.app_name, 0, winreg.REG_SZ,
                              f'"{target_exe}"')
            winreg.CloseKey(key)
            self._log(f"  Registered auto-start for {cfg.app_name}")
        except Exception as e:
            self._log(f"  Failed to set auto-start: {e}")

    # ── Shortcuts for copy-based installs ──────────────────────

    def _create_shortcut(self, cfg: "InstallConfig", location: str):
        try:
            install_dir = Path(cfg.install_path)
            if cfg.entry_script:
                target = str(install_dir / cfg.entry_script)
            else:
                target = str(install_dir)

            if location == "desktop":
                link_dir = Path(os.path.expandvars(r"%USERPROFILE%\Desktop"))
            else:
                link_dir = Path(os.path.expandvars(
                    r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"
                ))

            link_path = link_dir / f"{cfg.app_name}.lnk"
            ps_script = (
                f'$ws = New-Object -ComObject WScript.Shell; '
                f'$s = $ws.CreateShortcut("{link_path}"); '
                f'$s.TargetPath = "{sys.executable}"; '
                f'$s.Arguments = "{target}"; '
                f'$s.WorkingDirectory = "{install_dir}"; '
                f'$s.Description = "{cfg.app_name}"; '
                f'$s.Save()'
            )
            subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True, text=True,
            )
            self._log(f"  Created shortcut: {link_path}")
        except Exception as e:
            self._log(f"  Failed to create shortcut ({location}): {e}")

    def _create_autostart(self, cfg: "InstallConfig"):
        try:
            import winreg
            install_dir = Path(cfg.install_path)
            target = str(install_dir / cfg.entry_script) if cfg.entry_script else ""
            if not target:
                return

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE,
            )
            winreg.SetValueEx(key, cfg.app_name, 0, winreg.REG_SZ,
                              f'"{sys.executable}" "{target}"')
            winreg.CloseKey(key)
            self._log(f"  Registered auto-start for {cfg.app_name}")
        except Exception as e:
            self._log(f"  Failed to set auto-start: {e}")

    # ── Registry & uninstaller ─────────────────────────────────

    def _write_uninstall_info(self, cfg: "InstallConfig"):
        try:
            import winreg
            reg_key = cfg.registry_key or cfg.app_name.replace(" ", "")
            key_path = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{reg_key}"

            root = winreg.HKEY_CURRENT_USER
            key = winreg.CreateKeyEx(root, key_path, 0, winreg.KEY_SET_VALUE)

            install_dir = Path(cfg.install_path)
            uninstaller = install_dir / "uninstall.bat"

            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, cfg.app_name)
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, cfg.app_version)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, cfg.author)
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(install_dir))
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, str(uninstaller))
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 0)

            winreg.CloseKey(key)
            self._log("  Registered in Add/Remove Programs")
        except Exception as e:
            self._log(f"  Failed to write registry: {e}")

    def _generate_uninstaller(self, cfg: "InstallConfig"):
        try:
            install_dir = Path(cfg.install_path)
            reg_key = cfg.registry_key or cfg.app_name.replace(" ", "")

            bat_content = f'''@echo off
echo Uninstalling {cfg.app_name}...
echo.

:: Remove auto-start
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "{cfg.app_name}" /f 2>nul

:: Remove registry entry
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{reg_key}" /f 2>nul

:: Remove shortcuts
del "%USERPROFILE%\\Desktop\\{cfg.app_name}.lnk" 2>nul
del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\{cfg.app_name}.lnk" 2>nul

:: Remove install directory (delayed to allow bat to finish)
echo Removing files...
cd /d "%TEMP%"
rmdir /s /q "{install_dir}" 2>nul
echo {cfg.app_name} has been uninstalled.
pause
'''
            uninstaller = install_dir / "uninstall.bat"
            uninstaller.write_text(bat_content, encoding="utf-8")
            self._log("  Generated uninstaller")
        except Exception as e:
            self._log(f"  Failed to generate uninstaller: {e}")

    # ── Helpers ────────────────────────────────────────────────

    def _update(self, step: int, total: int, operation: str):
        pct = int((step / total) * 100)
        self.progress.emit(pct)
        self.operation.emit(operation)
        self._log(f"[{pct}%] {operation}")

    def _log(self, msg: str):
        self.log_message.emit(msg)
        _log.info(msg)


# ── Uninstall Worker ───────────────────────────────────────────

class UninstallWorker(QObject):
    """Runs the uninstallation in a background thread."""

    progress = Signal(int)
    operation = Signal(str)
    log_message = Signal(str)
    finished = Signal(bool)

    def __init__(self, app_name: str, install_path: str, registry_key: str):
        super().__init__()
        self._app_name = app_name
        self._install_path = install_path
        self._registry_key = registry_key or app_name.replace(" ", "")
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self._log(f"Uninstalling {self._app_name}...")
            self._do_uninstall()
            if not self._cancelled:
                self.finished.emit(True)
        except Exception as e:
            self._log(f"ERROR: {e}")
            _log.error("Uninstall failed: %s", e, exc_info=True)
            self.finished.emit(False)

    def _do_uninstall(self):
        total = 4
        step = 0

        # Step 1: Remove shortcuts
        step += 1
        self._update(step, total, "Removing shortcuts...")
        self._remove_shortcuts()

        if self._cancelled:
            return

        # Step 2: Remove auto-start
        step += 1
        self._update(step, total, "Removing auto-start entry...")
        self._remove_autostart()

        if self._cancelled:
            return

        # Step 3: Remove registry entries
        step += 1
        self._update(step, total, "Removing registry entries...")
        self._remove_registry()

        if self._cancelled:
            return

        # Step 4: Remove files
        step += 1
        self._update(step, total, "Removing files...")
        install_dir = Path(self._install_path)
        if install_dir.exists():
            file_count = sum(1 for _ in install_dir.rglob("*") if _.is_file())
            self._log(f"  Removing {file_count} files from {install_dir}")
            shutil.rmtree(install_dir, ignore_errors=True)
            if install_dir.exists():
                self._log("  Warning: some files could not be removed")
            else:
                self._log("  All files removed")

        self._update(total, total, "Uninstall complete!")
        self._log(f"{self._app_name} has been uninstalled.")

    def _remove_shortcuts(self):
        desktop = Path(os.path.expandvars(r"%USERPROFILE%\Desktop"))
        startmenu = Path(os.path.expandvars(
            r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"
        ))
        for link_dir in [desktop, startmenu]:
            link = link_dir / f"{self._app_name}.lnk"
            if link.exists():
                link.unlink()
                self._log(f"  Removed: {link}")

    def _remove_autostart(self):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE,
            )
            try:
                winreg.DeleteValue(key, self._app_name)
                self._log(f"  Removed auto-start entry")
            except FileNotFoundError:
                self._log("  No auto-start entry found")
            winreg.CloseKey(key)
        except Exception as e:
            self._log(f"  Could not remove auto-start: {e}")

    def _remove_registry(self):
        try:
            import winreg
            key_path = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{self._registry_key}"
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
            self._log("  Removed uninstall registry entry")
        except Exception as e:
            self._log(f"  Could not remove registry entry: {e}")

    def _update(self, step: int, total: int, operation: str):
        pct = int((step / total) * 100)
        self.progress.emit(pct)
        self.operation.emit(operation)
        self._log(f"[{pct}%] {operation}")

    def _log(self, msg: str):
        self.log_message.emit(msg)
        _log.info(msg)


# ── Install Config ─────────────────────────────────────────────

class InstallConfig:
    """Flat configuration passed to the install worker."""

    def __init__(self):
        self.app_name: str = ""
        self.app_version: str = ""
        self.author: str = ""
        self.install_path: str = ""
        self.install_type: str = "user"
        self.source_dir: str = ""
        self.include_patterns: List[str] = ["**/*"]
        self.exclude_patterns: List[str] = []
        self.requirements_file: str = ""
        self.create_venv: bool = False
        self.entry_script: str = ""
        self.registry_key: str = ""
        self.desktop_shortcut: bool = True
        self.start_menu: bool = True
        self.auto_start: bool = False
        self.components: List[bool] = []
        self.run_after_install: str = ""

        # PyInstaller settings
        self.use_pyinstaller: bool = False
        self.pyinstaller_onefile: bool = True
        self.pyinstaller_console: bool = False
        self.pyinstaller_icon: str = ""
        self.pyinstaller_extra_args: List[str] = []
        self.pyinstaller_hidden_imports: List[str] = []
        self.pyinstaller_data_files: List[str] = []
        self.resource_dirs: List[str] = []

        # Set by engine during build
        self._built_exe_name: str = ""


# ── Installation Engine ────────────────────────────────────────

class InstallationEngine(QObject):
    """
    Orchestrates installation/uninstallation in a background thread.
    Connect to progress/operation/log_message/finished signals for UI updates.
    """

    progress = Signal(int)
    operation = Signal(str)
    log_message = Signal(str)
    error_message = Signal(str)
    finished = Signal(bool)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread: Optional[QThread] = None
        self._worker: Optional[QObject] = None

    def start(self, config: InstallConfig):
        self._thread = QThread()
        self._worker = InstallWorker(config)
        self._worker.moveToThread(self._thread)

        self._worker.progress.connect(self.progress)
        self._worker.operation.connect(self.operation)
        self._worker.log_message.connect(self.log_message)
        self._worker.error_message.connect(self.error_message)
        self._worker.finished.connect(self._on_finished)

        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def start_uninstall(self, app_name: str, install_path: str,
                        registry_key: str):
        self._thread = QThread()
        self._worker = UninstallWorker(app_name, install_path, registry_key)
        self._worker.moveToThread(self._thread)

        self._worker.progress.connect(self.progress)
        self._worker.operation.connect(self.operation)
        self._worker.log_message.connect(self.log_message)
        self._worker.finished.connect(self._on_finished)

        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def cancel(self):
        if self._worker and hasattr(self._worker, 'cancel'):
            self._worker.cancel()

    def _on_finished(self, success: bool):
        self.finished.emit(success)
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None
