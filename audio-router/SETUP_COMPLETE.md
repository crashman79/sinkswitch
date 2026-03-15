# PipeWire Audio Router – Setup & Usage

## Recommended: Standalone App

The app runs without installing a service. Use the GUI to configure routing and start/stop the router.

### First-time setup

1. **Requirements**: Python 3.8+, PyQt6, PyYAML (and `dbus-python` for Bluetooth).
   ```bash
   pip install -r requirements.txt
   ```
   On PEP 668 distros (e.g. Arch), use a venv or run `build.sh` to create a binary.

2. **Run the app**
   ```bash
   cd audio-router
   python3 run_app.py
   ```
   Or build a binary and run it:
   ```bash
   ./build.sh
   ./dist/pipewire-audio-router
   ```

3. **First run**: The app creates `~/.config/pipewire-router/config/routing_rules.yaml` (auto-generated from connected devices if possible).

4. **GUI**
   - **Devices**: See outputs with friendly names; refresh as needed.
   - **Routing rules**: Add/edit/delete rules, or **Auto-Generate Rules**.
   - **Active streams**: See which app is playing and where it’s routed.
   - **Logs**: In-app log buffer (no journal when running standalone).
   - **Settings**: Start on login (XDG autostart), Start routing when app opens, Close to tray, **Add to application menu**.

5. **Start/Stop**: Use the toolbar buttons. They are enabled only when applicable (e.g. Start is disabled while the router is running).

6. **Tray**: If your desktop has a system tray, the app shows an icon. With **Close to tray** enabled, closing the window hides the app to the tray instead of quitting. Use the tray menu to Show, Start/Stop router, or Quit.

### Config location

- **Config dir**: `~/.config/pipewire-router/` (or set `AUDIO_ROUTER_CONFIG`).
- **Rules**: `config/routing_rules.yaml`.
- **App settings**: `app_settings.json` (start on login, close to tray, etc.).

### Launch without a terminal

- **Settings → Add to application menu**: Adds a launcher to `~/.local/share/applications/` so the app appears in your app menu.
- **Settings → Launch app at login**: Adds an entry to `~/.config/autostart/` so the app starts when you log in.

---

## Optional: Install script and systemd

If you prefer the router to run as a user service (no GUI required) at session start:

```bash
cd audio-router
./install.sh
systemctl --user start pipewire-router
systemctl --user enable pipewire-router
```

This installs files under `~/.config/pipewire-router/`, creates a venv, and installs `~/.config/systemd/user/pipewire-router.service`. The standalone app does **not** require this; it runs the router inside the GUI process.

### Service commands (when using install.sh)

```bash
systemctl --user status pipewire-router --no-pager
journalctl --user -u pipewire-router -f
systemctl --user restart pipewire-router
```

---

## Troubleshooting

### Routing not working (standalone app)

- Ensure the router is **Running** (green) in the GUI; click **Start** if needed.
- Check **Devices**: target devices should appear with friendly names.
- Check **Active streams**: application names should appear; if not, pactl may use a different property format.
- **Logs** tab: look for errors.

### Routing not working (systemd)

- `systemctl --user status pipewire-router --no-pager`
- `journalctl --user -u pipewire-router --no-pager | tail -30`
- Regenerate config and restart: edit or regenerate `~/.config/pipewire-router/config/routing_rules.yaml`, then `systemctl --user restart pipewire-router`

### Wrong device or “Unknown” in streams

- Use **Auto-Generate Rules** in the GUI to refresh rules from current devices.
- For Active streams, the app reads `application.name` from `pactl list sink-inputs`; if your app doesn’t set it, the name may be generic or “Unknown”.

### Tray icon missing

- The tray is only shown if `QSystemTrayIcon.isSystemTrayAvailable()` is true (e.g. GNOME/KDE/XFCE with a system tray).
- “Close to tray” only has an effect when the tray is available.

---

## Architecture (standalone app)

- **run_app.py**: Sets `AUDIO_ROUTER_CONFIG`, `AUDIO_ROUTER_LAUNCH_CMD`, `AUDIO_ROUTER_WORKING_DIR`; bootstraps config; runs GUI.
- **GUI**: Starts a `MonitorThread` that runs `DeviceMonitor.watch_devices(..., stop_event=...)` and applies rules; config can auto-regenerate on Bluetooth/USB changes.
- **Config**: YAML `routing_rules` with `name`, `applications`, `target_device` (sink id), `enable_default_fallback`.
- **Quit**: With `setQuitOnLastWindowClosed(False)`, the app only exits when you use **Quit** from the tray or close the window with “Close to tray” disabled.
