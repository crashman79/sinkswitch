# PipeWire/PulseAudio Audio Router

Automatic audio stream routing based on application classes and connected output devices.

## Features

- **Intelligent Device Routing**: Automatically routes audio to different output devices based on application type
- **Device Detection**: Automatically detects USB headsets, Bluetooth devices, HDMI outputs, and analog speakers
- **Application Categories**: Groups applications by type (browsers, meetings, music, games) with optimized routing
- **Graphical Interface**: Full-featured GUI for managing devices and routing rules
- **System Tray Icon**: KDE Plasma and Gnome desktop integration
- **Daemon Mode**: Runs as systemd user service for automatic routing
- **PulseAudio Compatible**: Works with both PipeWire and PulseAudio backends

## Supported Browsers

- Firefox
- Chrome/Chromium
- Opera
- Edge
- Brave
- Vivaldi

## Quick Start

```bash
./install.sh
systemctl --user start pipewire-router
systemctl --user enable pipewire-router
```

## Graphical Interface

Launch the GUI for easy configuration:

```bash
~/.config/pipewire-router/launch-gui.sh
```

Or search for "PipeWire Audio Router" in your application menu.

**GUI Features:**
- 🎧 Visual device list with real-time connection status
- 🔀 Create and edit routing rules with forms
- 📊 Monitor active audio streams in real-time
- ⚙️ Service control (start/stop/restart)
- 📋 Built-in log viewer

**Requirements:** `sudo pacman -S python-pyqt6`

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

## Installation

See SETUP_COMPLETE.md for detailed installation instructions.
