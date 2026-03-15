# PipeWire Audio Router – Project Instructions

## Project Overview

Standalone GUI application for automatic audio stream routing on PipeWire/PulseAudio: route applications to specific outputs (Bluetooth, USB, HDMI, etc.) by rule. No systemd or install script required for normal use.

## Development Guidelines

### Terminal / shell

- Use **bash** for commands and scripts (not fish). Use `bash -c "..."` or run in a bash session when needed.
- For systemd/journal: use `--no-pager` (e.g. `systemctl --user status pipewire-router --no-pager`).

### Python / Arch (PEP 668)

- User may be on Arch/CachyOS; avoid `pip install --user` or `--break-system-packages`.
- Use a **venv** for Python deps. The app’s `build.sh` creates `.venv-build` and installs PyInstaller + requirements there.

## Project Structure

- **audio-router/**
  - `run_app.py` – Standalone launcher (script or frozen binary); sets env, bootstraps config, runs GUI.
  - `build.sh` – Builds single binary with PyInstaller using a project venv.
  - `run_app.spec` – PyInstaller spec.
  - **src/** – Python source:
    - `audio_router_gui.py` – Main window, integrated tray, in-app monitor thread, Settings.
    - `device_monitor.py` – Device list, `watch_devices(stop_event=...)`, friendly names.
    - `audio_router_engine.py` – pactl-based routing.
    - `config_parser.py`, `intelligent_audio_router.py` – Config and auto-generation.
    - `tray_icon.py` – Legacy standalone tray for systemd (optional).
  - **config/** – Example/default routing config.
  - **systemd/** – Optional user service (used by install.sh).
  - **install.sh** – Optional: copy to ~/.config/pipewire-router, venv, systemd service.

## Features

- **Standalone app**: Run via `python3 run_app.py` or `./dist/pipewire-audio-router`; config in `~/.config/pipewire-router/`.
- **GUI**: Devices (friendly names), Routing rules, Active streams (app names from pactl), Logs, Settings.
- **In-app router**: Start/Stop/Restart control a background thread; no systemd required.
- **Settings**: Start on login (XDG), Start routing when app opens, Close to tray, Add to application menu.
- **Tray**: Integrated tray icon (Show, Start/Stop, Quit); “Close to tray” hides window instead of quitting.
- **Optional**: `install.sh` for systemd user service at session start.

## Usage (for AI / docs)

```bash
# Run app (from repo)
cd audio-router && python3 run_app.py

# Build binary
cd audio-router && ./build.sh && ./dist/pipewire-audio-router

# Optional install + systemd
cd audio-router && ./install.sh && systemctl --user start pipewire-router
```

## Configuration

- **Path**: `~/.config/pipewire-router/` or `AUDIO_ROUTER_CONFIG`.
- **Rules**: `config/routing_rules.yaml` (YAML with `routing_rules` list).
- **App settings**: `app_settings.json` (start_on_login, start_routing_on_launch, close_to_tray).
