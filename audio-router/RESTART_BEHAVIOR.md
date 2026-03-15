# Restart & Startup Behavior

## Standalone App

### When you run the app

1. **First run**: The app creates `~/.config/pipewire-router/` and `config/routing_rules.yaml` (empty or auto-generated from connected devices).
2. **Router**: Click **Start** to run the in-app router (background thread). It monitors device and stream changes and applies routing rules. If **Start routing when app opens** is enabled in Settings, the router starts automatically.
3. **Closing**: With **Close to tray** enabled, closing the window hides the app; the router keeps running. With it disabled, closing the window quits the app and stops the router.

### Start on login

- **None**: You start the app manually (e.g. from app menu or terminal).
- **Launch app at login**: The app adds a desktop entry to `~/.config/autostart/`. After login, the app starts; if “Start routing when app opens” is enabled, the router starts automatically.

### Device hotplug (in-app router)

The in-app monitor watches for device and stream changes. On **significant device changes** (e.g. Bluetooth or USB connect/disconnect), it can **auto-regenerate** the routing config and reload rules, so new devices are picked up without restarting the app.

---

## Optional: systemd service (install.sh)

If you used `install.sh` and enabled the systemd user service:

- **On session start**: The service starts (if enabled with `systemctl --user enable pipewire-router`).
- **ExecStartPre**: Runs a script that regenerates `routing_rules.yaml` from current devices.
- **ExecStart**: Runs `audio_router.py monitor ...`, which applies rules continuously.
- **Restart**: On failure the service restarts (Restart=on-failure).

Restarting the service or rebooting runs ExecStartPre again, so the config is regenerated from currently connected devices.

---

## PipeWire auto-routing

If you have disabled PipeWire’s own auto-routing (e.g. via a config snippet), that is independent of this app and persists across reboots. The app (and the systemd service) do not re-enable it.
