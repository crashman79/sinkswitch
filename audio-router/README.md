# PipeWire/PulseAudio Audio Router

Standalone app: automatic audio stream routing by application and connected devices. No install script or systemd required.

## Features

- **Standalone app** – Run from project directory; config created on first run at `~/.config/pipewire-router/`
- **Intelligent routing** – Routes audio by application type (browsers, meetings, media) to chosen outputs
- **Device detection** – USB headsets, Bluetooth, HDMI, analog speakers
- **GUI** – Configure rules, see devices and streams, start/stop router, optional “launch at login”
- **PipeWire & PulseAudio** – Works with both backends

## Supported Browsers

- Firefox
- Chrome/Chromium
- Opera
- Edge
- Brave
- Vivaldi

## Quick Start (standalone)

**Requirements:** Python 3.8+, PyQt6, PyYAML (and `dbus-python` for Bluetooth). Example: `pip install -r requirements.txt`

```bash
cd audio-router
python3 run_app.py
```

On first run the app creates `~/.config/pipewire-router/config/routing_rules.yaml` (and can auto-generate rules from connected devices). Use the GUI to adjust rules, start/stop the router, and optionally enable “Launch app at login” in Settings.

**GUI:** Devices, Routing rules, Active streams, Logs, Settings (start on login, auto-start routing, **Add to application menu**).

### Launch without a terminal

- **Application menu:** In the app, open **Settings** → **Add to application menu**. The app will appear in your app launcher (e.g. GNOME/KDE menu) so you can start it without a terminal.
- **Single binary:** Build a standalone executable and run it (or move it to your PATH):

```bash
cd audio-router
pip install pyinstaller
./build.sh
# Binary: dist/pipewire-audio-router
./dist/pipewire-audio-router
```

You can move `dist/pipewire-audio-router` anywhere and run it directly; config is still in `~/.config/pipewire-router/`.

## Command Line Usage

```bash
# Auto-generate routing rules based on connected devices
python3 src/audio_router.py generate-config

# List available devices
python3 src/audio_router.py list-devices

# Apply routing rules once
python3 src/audio_router.py apply-rules config/routing_rules.yaml

# Monitor and apply rules continuously
python3 src/audio_router.py monitor config/routing_rules.yaml
```

## Configuration

Routing rules are defined in YAML format in `config/routing_rules.yaml`:

```yaml
routing_rules:
  - name: "Browser to USB Headset"
    applications:
      - "firefox"
      - "chrome"
    application_keywords:
      - "browser"
    target_device: "USB Headset"
    enable_default_fallback: true
```

## Optional: install script and systemd

For a system-wide install under `~/.config/pipewire-router` and a systemd user service, run `./install.sh`. The standalone app does not require it.
