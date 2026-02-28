"""
Nova Installer — Build Script

Builds the installer itself into a standalone one-file executable.

The build process:
  1. Reads installer.json to get the Nova app's PyInstaller config.
  2. Builds the Nova app using PyInstaller (source → dist/Nova/).
  3. Copies resource directories (plugins, config) alongside the build.
  4. Bundles the pre-built Nova app + installer UI into a single
     NovaInstaller.exe using PyInstaller --onefile.

The resulting NovaInstaller.exe:
  - Requires NO Python or pip on the target machine.
  - Contains the pre-built Nova application embedded inside.
  - At install time, extracts and copies files to the chosen directory.
  - Creates shortcuts, registry entries, and an uninstaller.

Usage:
    python setup.py                 # Build NovaInstaller.exe (one-file)
    python setup.py --debug         # Build with console window for debugging
    python setup.py --skip-app      # Skip rebuilding Nova, reuse previous build
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
INSTALLER_PKG = ROOT / "installer"
MAIN_SCRIPT = ROOT / "installer_main.py"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
PREBUILD_DIR = ROOT / "build" / "_nova_prebuild"
ICON_FILE = ROOT / "build" / "nova.ico"


def _generate_ico(output_path: Path) -> Path:
    """Generate a .ico file from the nova_icon SVG template.

    Uses PySide6 to render the SVG at multiple sizes, then writes a raw
    ICO file (PNG-encoded entries).  No Pillow dependency required.
    """
    import struct

    # Import PySide6 — a QGuiApplication is needed for rendering
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    # Ensure a QGuiApplication exists
    app = QGuiApplication.instance()
    created_app = False
    if app is None:
        app = QGuiApplication([])
        created_app = True

    try:
        from installer.resources.builtin_icons import ICONS

        svg_template = ICONS.get("nova_icon", "")
        svg_str = svg_template.format(primary="#0088CC", secondary="#00BBFF")
        svg_data = QByteArray(svg_str.encode())

        sizes = [16, 24, 32, 48, 64, 128, 256]
        png_blobs: list[tuple[int, bytes]] = []

        for sz in sizes:
            renderer = QSvgRenderer(svg_data)
            if not renderer.isValid():
                continue
            img = QImage(sz, sz, QImage.Format_ARGB32)
            img.fill(Qt.transparent)
            painter = QPainter(img)
            renderer.render(painter)
            painter.end()

            buf = QBuffer()
            buf.open(QIODevice.WriteOnly)
            img.save(buf, "PNG")
            png_blobs.append((sz, bytes(buf.data())))
            buf.close()

        if not png_blobs:
            print("  WARNING: Could not render icon SVG")
            return output_path

        # Write ICO file: ICONDIR + ICONDIRENTRY[] + PNG data
        count = len(png_blobs)
        header = struct.pack("<HHH", 0, 1, count)  # reserved, type=ICO, count

        dir_entries = b""
        data_offset = 6 + count * 16  # header + entries
        image_data = b""

        for sz, blob in png_blobs:
            w = 0 if sz >= 256 else sz  # 0 means 256 in ICO spec
            h = w
            entry = struct.pack(
                "<BBBBHHII",
                w, h,           # width, height
                0, 0,           # colorCount, reserved
                1, 32,          # planes, bitCount
                len(blob),      # bytesInRes
                data_offset,    # imageOffset
            )
            dir_entries += entry
            data_offset += len(blob)
            image_data += blob

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(header + dir_entries + image_data)
        print(f"  Generated icon: {output_path} ({count} sizes)")
        return output_path
    finally:
        if created_app:
            del app


def _load_manifest():
    """Load and return the installer.json manifest."""
    config_path = ROOT / "installer.json"
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def _build_nova_app(manifest):
    """Step 1: Build the Nova application using PyInstaller."""
    print("=" * 60)
    print("  STEP 1: Building Nova application")
    print("=" * 60)

    app_cfg = manifest["app"]
    install_cfg = manifest["install"]
    python_cfg = manifest["python"]
    pi_cfg = manifest["pyinstaller"]

    app_name = app_cfg["name"].replace(" ", "")
    source_dir = ROOT / install_cfg["source_dir"]
    source_dir = source_dir.resolve()
    entry_script = source_dir / python_cfg["entry_script"]

    if not entry_script.exists():
        print(f"  ERROR: Entry script not found: {entry_script}")
        sys.exit(1)

    # Prepare build directories
    nova_dist = PREBUILD_DIR / "dist"
    nova_work = PREBUILD_DIR / "work"
    nova_dist.mkdir(parents=True, exist_ok=True)
    nova_work.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", app_name,
        "--distpath", str(nova_dist),
        "--workpath", str(nova_work),
        "--specpath", str(nova_work),
        "--noconfirm",
        "--clean",
    ]

    # Always build as onedir for the pre-built bundle
    cmd.append("--onedir")

    if not pi_cfg.get("console", False):
        cmd.append("--noconsole")

    # Icon — prefer generated ico, then fall back to manifest setting
    if ICON_FILE.exists():
        cmd.extend(["--icon", str(ICON_FILE)])
    else:
        icon = pi_cfg.get("icon", "")
        if icon:
            icon_path = Path(icon)
            if not icon_path.is_absolute():
                icon_path = source_dir / icon_path
            if icon_path.exists():
                cmd.extend(["--icon", str(icon_path)])

    # Hidden imports
    for imp in pi_cfg.get("hidden_imports", []):
        cmd.extend(["--hidden-import", imp])

    # Data files (resolve relative paths)
    for data in pi_cfg.get("data_files", []):
        parts = data.split(";") if ";" in data else data.split(":")
        if len(parts) == 2:
            src = Path(parts[0])
            if not src.is_absolute():
                src = source_dir / src
            data = f"{src}{os.pathsep}{parts[1]}"
        cmd.extend(["--add-data", data])

    # Extra args
    cmd.extend(pi_cfg.get("extra_args", []))

    cmd.append(str(entry_script))

    print(f"  App name:    {app_name}")
    print(f"  Source:      {source_dir}")
    print(f"  Entry:       {entry_script}")
    print(f"  Imports:     {len(pi_cfg.get('hidden_imports', []))}")
    print(f"  Data files:  {len(pi_cfg.get('data_files', []))}")
    print()

    result = subprocess.run(cmd, cwd=str(source_dir))
    if result.returncode != 0:
        print(f"\n  ERROR: PyInstaller build failed (exit code {result.returncode})")
        sys.exit(1)

    # Verify the built exe exists
    built_dir = nova_dist / app_name
    built_exe = built_dir / f"{app_name}.exe"
    if not built_exe.exists():
        print(f"  ERROR: Expected exe not found: {built_exe}")
        sys.exit(1)

    print(f"\n  Nova app built successfully: {built_dir}")
    return built_dir, app_name


def _copy_resource_dirs(manifest, built_dir):
    """Step 2: Copy resource directories alongside the build."""
    print()
    print("=" * 60)
    print("  STEP 2: Copying resource directories")
    print("=" * 60)

    install_cfg = manifest["install"]
    pi_cfg = manifest["pyinstaller"]
    source_dir = (ROOT / install_cfg["source_dir"]).resolve()

    resource_dirs = pi_cfg.get("resource_dirs", [])
    if not resource_dirs:
        print("  No resource directories to copy.")
        return

    for rdir in resource_dirs:
        src = source_dir / rdir
        dst = built_dir / rdir
        if src.exists() and src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(
                src, dst,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"),
            )
            count = sum(1 for _ in dst.rglob("*") if _.is_file())
            print(f"  Copied {rdir}/ ({count} files)")
        else:
            print(f"  WARNING: Resource dir not found: {src}")


def _build_installer(manifest, nova_app_dir, app_name, debug=False):
    """Step 3: Build the installer exe, bundling the pre-built Nova app."""
    print()
    print("=" * 60)
    print("  STEP 3: Building NovaInstaller.exe")
    print("=" * 60)

    installer_name = f"{app_name}Installer"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", installer_name,
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR / "installer_work"),
        "--specpath", str(BUILD_DIR / "installer_work"),
        "--noconfirm",
        "--clean",
        "--onefile",
    ]

    if not debug:
        cmd.append("--noconsole")

    # Hidden imports for the installer UI
    hidden_imports = [
        "PySide6.QtWidgets",
        "PySide6.QtGui",
        "PySide6.QtCore",
        "PySide6.QtSvg",
        "installer",
        "installer.app",
        "installer.core.config",
        "installer.core.engine",
        "installer.core.style",
        "installer.core.icons",
        "installer.ui.installer_window",
        "installer.ui.step_topbar",
        "installer.pages.welcome_page",
        "installer.pages.license_page",
        "installer.pages.install_type_page",
        "installer.pages.path_page",
        "installer.pages.options_page",
        "installer.pages.progress_page",
        "installer.pages.finish_page",
        "installer.pages.maintenance_page",
        "installer.resources.builtin_icons",
    ]
    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])

    # Bundle the QSS
    qss_path = INSTALLER_PKG / "resources" / "installer.qss"
    if qss_path.exists():
        cmd.extend(["--add-data", f"{qss_path}{os.pathsep}installer/resources"])

    # Bundle installer.json
    config_path = ROOT / "installer.json"
    if config_path.exists():
        cmd.extend(["--add-data", f"{config_path}{os.pathsep}."])

    # Bundle the entire pre-built Nova app as _nova_app/
    if nova_app_dir.exists():
        cmd.extend(["--add-data", f"{nova_app_dir}{os.pathsep}_nova_app"])
        # Count total files being bundled
        total_files = sum(1 for _ in nova_app_dir.rglob("*") if _.is_file())
        print(f"  Bundling {total_files} pre-built app files")

    # Icon — use generated ico
    if ICON_FILE.exists():
        cmd.extend(["--icon", str(ICON_FILE)])

    cmd.append(str(MAIN_SCRIPT))

    print(f"  Installer:   {installer_name}")
    print(f"  Mode:        onefile")
    print(f"  Console:     {'yes' if debug else 'no'}")
    print(f"  Imports:     {len(hidden_imports)}")
    print()

    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"\n  ERROR: Installer build failed (exit code {result.returncode})")
        sys.exit(1)

    exe_path = DIST_DIR / f"{installer_name}.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n  Build successful!")
        print(f"  Output:  {exe_path}")
        print(f"  Size:    {size_mb:.1f} MB")
    else:
        print(f"\n  ERROR: Expected output not found: {exe_path}")
        sys.exit(1)

    return exe_path


def build():
    args = sys.argv[1:]
    debug = "--debug" in args
    skip_app = "--skip-app" in args

    manifest = _load_manifest()
    app_name = manifest["app"]["name"].replace(" ", "")

    print()
    print("  Nova Installer — Build System")
    print(f"  Building: {manifest['app']['name']} v{manifest['app']['version']}")
    print()

    # Generate .ico from SVG template
    print("  Generating application icon...")
    _generate_ico(ICON_FILE)
    print()

    # Step 1 & 2: Build and prepare the Nova app
    nova_app_dir = PREBUILD_DIR / "dist" / app_name

    if skip_app and nova_app_dir.exists():
        print("  --skip-app: Reusing previous Nova build")
        print(f"  Pre-built dir: {nova_app_dir}")
    else:
        nova_app_dir, app_name = _build_nova_app(manifest)
        _copy_resource_dirs(manifest, nova_app_dir)

    # Step 3: Build the installer exe
    _build_installer(manifest, nova_app_dir, app_name, debug=debug)

    print()
    print("  Done! Distribute the .exe file to users.")
    print()


if __name__ == "__main__":
    build()
