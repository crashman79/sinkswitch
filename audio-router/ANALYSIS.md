# Audio Router: Design Overview

## Current Design (Standalone App)

The app is a **standalone graphical application**. No install script or systemd is required for normal use.

- **Entry point**: `run_app.py` (script) or `dist/pipewire-audio-router` (PyInstaller binary from `build.sh`).
- **Config**: `~/.config/pipewire-router/` (or `AUDIO_ROUTER_CONFIG`). Created on first run; `config/routing_rules.yaml` is bootstrapped if missing.
- **Router**: Runs inside the app in a background thread (`MonitorThread`). Start/Stop/Restart in the GUI control this thread. No systemd.
- **GUI** (`audio_router_gui.py`): Devices (friendly names), Routing rules, Active streams (real app names from pactl), Logs (in-app buffer), Settings.
- **Settings**: Start on login (None / Launch app at login via XDG Autostart), Start routing when app opens, Close to tray, Add to application menu.
- **Tray**: Integrated system tray when available: Show, Start/Stop router, Quit. With "Close to tray", closing the window hides to tray; app quits only via tray Quit or when close-to-tray is off.
- **Friendly names**: `device_monitor` enriches each device with `device_type` and `friendly_name` (from pactl description or derived from id).

## Optional: install.sh and systemd

Running `./install.sh` copies files to `~/.config/pipewire-router/`, creates a venv, and installs a systemd user service. Useful if you want the router to run at session start without the GUI. The standalone app does not depend on it.

## Key Files

| File | Purpose |
|------|---------|
| `run_app.py` | Launcher: sets path/env, bootstraps config, runs GUI. Works frozen (binary) or as script. |
| `run_app.spec` | PyInstaller spec; build via `build.sh` (uses .venv-build, installs deps + pyinstaller). |
| `src/audio_router_gui.py` | Main window, tray, in-app monitor thread, Settings (autostart, close-to-tray, app menu). |
| `src/device_monitor.py` | Device list, `watch_devices()` with optional `stop_event`; `_enrich_device()` adds friendly_name/device_type. |
| `~/.config/pipewire-router/app_settings.json` | Persisted settings: start_on_login, start_routing_on_launch, close_to_tray. |
