# Audio Router: Service → App Conversion

## Current State

- **Router**: `audio_router.py monitor <config>` runs a polling loop (`DeviceMonitor.watch_devices`) that applies routing rules on device/stream changes and can regenerate config on Bluetooth/USB changes.
- **Service**: systemd user unit runs that process; `install.sh` installs to `~/.config/pipewire-router/` and `~/.config/systemd/user/pipewire-router.service`.
- **GUI** (`audio_router_gui.py`): PyQt6 window with Devices, Routing Rules, Active Streams, Logs; Start/Stop/Restart control the **systemd service** only.
- **Tray** (`tray_icon.py`): Tray icon with pause/resume (systemctl stop/start), regenerate config, view logs.

## Goal

- **App-first**: Single graphical app as main entry point, with configuration and status.
- **Run modes**:
  1. **Run in app** – Router runs inside the app (background thread). No systemd required.
  2. **Use systemd** – Keep current behavior; GUI/tray only control the service.
- **Start on login** (multiple methods for different Linux DEs):
  1. **None** – Manual start.
  2. **Launch app at login** – XDG Autostart (`.desktop` in `~/.config/autostart/`). Works on GNOME, KDE, XFCE, MATE, LXDE, etc.
  3. **Start router with systemd at session start** – `systemctl --user enable pipewire-router` (runs monitor at user session start, no GUI required).

## Implementation Summary

| Item | Action |
|------|--------|
| `device_monitor.py` | Add optional `stop_event` to `watch_devices()` so the loop can be stopped from a QThread. |
| GUI | Add **Settings** tab: run mode (Run in app / Use systemd), start-on-login (None / Launch app at login / Systemd at session start). Persist in `~/.config/pipewire-router/app_settings.json`. |
| GUI | When "Run in app": Start/Stop start/stop an in-app monitor thread (using existing config + regen callback). When "Use systemd": keep current systemctl start/stop. |
| Autostart | "Launch app at login" = add/remove a `.desktop` in `~/.config/autostart/` that runs the app (e.g. `launch-gui.sh` or a new `launch-app.sh`). Option: "Start routing when app opens" so routing begins automatically. |
| Install | Install script: still install systemd unit (for "systemd at session" option); install one app `.desktop` for menu + optional autostart; document app-first usage. |

## Files to Add/Change

- `ANALYSIS.md` (this file)
- `src/device_monitor.py` – optional `stop_event` in `watch_devices`
- `src/audio_router_gui.py` – Settings tab, in-app monitor thread, autostart read/write
- `config/app_settings.json` (generated) – run_mode, start_on_login, start_routing_on_launch
- `audio-router-app.desktop` – single desktop entry for app (menu + copy to autostart when "Launch app at login")
- `install.sh` – install app desktop; mention app-first flow
