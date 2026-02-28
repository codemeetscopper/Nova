# Nova

A futuristic, plugin-driven application platform built on PySide6. Each plugin runs in an isolated subprocess for maximum stability and security.

## Features

- **Plugin Architecture** — Plugins run in isolated subprocesses with QLocalSocket IPC
- **Docking System** — Plugins can be docked, undocked, and rearranged
- **Dark Theme** — QSS-based theming with configurable accent colors and color tokens
- **Installer Wizard** — 7-step installer with frameless UI, animated stepper, and fast-forward install
- **Windows Integration** — Desktop/Start Menu shortcuts, registry entries, auto-start, and uninstaller

## Project Structure

```
Nova/
├── main.py                 # Nova application entry point
├── installer_main.py       # Installer entry point
├── setup.py                # Build script (creates NovaInstaller.exe)
├── installer.json          # Installer configuration manifest
├── LICENSE                 # MIT License
│
├── nova/                   # Nova application package
│   ├── app.py              # Application bootstrap
│   ├── core/               # Core services
│   │   ├── style.py        # StyleManager — QSS theming + color tokens
│   │   ├── icons.py        # IconManager — inline SVG rendering
│   │   ├── config.py       # ConfigManager — app settings
│   │   ├── paths.py        # Path resolution
│   │   ├── plugin_manager.py  # Plugin lifecycle management
│   │   ├── plugin_bridge.py   # QLocalSocket IPC (host side)
│   │   └── worker_host.py     # Subprocess host for plugins
│   ├── pages/              # Built-in UI pages
│   ├── ui/                 # UI components
│   └── resources/          # QSS themes, inline SVG icons
│
├── installer/              # Installer UI package
│   ├── app.py              # Installer orchestration
│   ├── core/               # Config, engine, style, icons
│   │   ├── config.py       # Reads installer.json manifest
│   │   ├── engine.py       # Install/uninstall workers (QThread)
│   │   ├── style.py        # Standalone StyleManager
│   │   └── icons.py        # Standalone IconManager
│   ├── pages/              # Wizard pages (7 steps)
│   │   ├── welcome_page.py    # Install Now / Customize buttons
│   │   ├── license_page.py
│   │   ├── install_type_page.py  # User vs System install
│   │   ├── path_page.py
│   │   ├── options_page.py
│   │   ├── progress_page.py
│   │   └── finish_page.py
│   ├── ui/
│   │   ├── installer_window.py  # Frameless window + title bar
│   │   └── step_topbar.py       # Animated progress stepper
│   └── resources/
│       ├── builtin_icons.py     # Inline SVG icon library
│       └── installer.qss        # Installer theme
│
└── plugins/                # Plugin directory
    ├── clock_widget/       # Clock widget plugin
    ├── system_monitor/     # System monitor plugin
    └── dummy/              # Demo plugin
```

## Quick Start

### Run Nova

```bash
python main.py
```

### Run the Installer (dev mode)

```bash
python installer_main.py
```

### Build NovaInstaller.exe

```bash
python setup.py                 # Full build
python setup.py --skip-app      # Skip rebuilding Nova, reuse previous build
python setup.py --debug         # Build with console window
```

The build process:
1. Builds the Nova app using PyInstaller (source to onedir bundle)
2. Copies resource directories (plugins) alongside the build
3. Bundles everything into a single `NovaInstaller.exe` using PyInstaller onefile

Output: `dist/NovaInstaller.exe`

## Installer Flow

```
Welcome ─── License ─── Install Type ─── Location ─── Options ─── Installing ─── Complete
  │                                                                    ▲
  └── "Install Now" (fast-forward with defaults) ──────────────────────┘
```

The installer supports two paths from the Welcome page:

- **Install Now** — One-click install with default settings (user mode, default path, all components, desktop + start menu shortcuts)
- **Customize Installation** — Full 7-step wizard with granular control

When an existing installation is detected, the installer enters **Maintenance Mode** with options to Modify, Repair, Update, or Uninstall.

## Configuration

The `installer.json` manifest controls both the Nova app build and installer behavior:

```json
{
  "app": {
    "name": "Nova",
    "version": "1.0.0",
    "accent_color": "#0088CC"
  },
  "install": {
    "source_dir": "./",
    "include": ["**/*"],
    "exclude": ["__pycache__", "*.pyc", ".git", "..."],
    "registry_key": "Nova"
  },
  "pyinstaller": {
    "enabled": true,
    "hidden_imports": ["..."],
    "data_files": ["nova/resources;nova/resources"],
    "resource_dirs": ["plugins"]
  },
  "components": [
    { "name": "Core Application", "default": true },
    { "name": "Built-in Plugins", "default": true }
  ]
}
```

## Plugin System

Plugins are self-contained directories under `plugins/`. Each plugin:

- Runs in its own **subprocess** for crash isolation
- Communicates with the host via **QLocalSocket** (JSON messages)
- Can provide custom UI rendered in the main window
- Supports **docking/undocking** into separate windows
- Has lifecycle management: start, stop, reload

## Theming

Nova uses a QSS color token system. Tokens in `.qss` files are replaced at runtime:

| Token | Description |
|-------|-------------|
| `<accent>` | Primary accent color |
| `<accent_l1>` to `<accent_l3>` | Lighter accent tiers |
| `<accent_d1>`, `<accent_d2>` | Darker accent tiers |
| `<accent_ln>` | Lightest accent (near-white tint) |
| `<bg>`, `<bg1>`, `<bg2>` | Background tiers (base, card, border) |
| `<fg>`, `<fg1>`, `<fg2>` | Foreground tiers (text, secondary, dim) |

Both light and dark themes are supported. The accent color is configurable via `installer.json`.

## License

MIT License. See [LICENSE](LICENSE) for details.
