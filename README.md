# PipeWire/PulseAudio Automatic Audio Stream Switching

A comprehensive configuration system for automatic audio stream switching in PipeWire/PulseAudio based on application classes and connected output devices.

## Features

- **Automatic Device Detection**: Monitors connected audio output devices
- **Application-Based Routing**: Routes audio streams based on application class/name
- **Conditional Switching**: Only switches if target device is connected
- **Python Configuration Tool**: CLI and daemon modes for managing routing rules
- **Systemd Integration**: Run as user service for persistent configuration
- **PipeWire & PulseAudio Support**: Works with both audio systems
- **System Tray Icon**: Optional PyQt6-based tray icon with visual status and quick controls

## Project Structure

```
.
├── src/
│   ├── audio_router.py              # Main CLI interface
│   ├── device_monitor.py            # Device detection and monitoring
│   ├── config_parser.py             # YAML configuration parsing
│   ├── audio_router_engine.py       # Routing logic (pactl-based)
│   └── intelligent_audio_router.py  # Device classification and auto-generation
├── config/
│   └── routing_rules.yaml            # Auto-generated routing configuration
├── systemd/
│   └── pipewire-router.service      # Systemd user service
├── examples/
│   ├── basic_routing.yaml            # Reference example (auto-generated in practice)
│   └── advanced_routing.yaml         # Reference example with advanced features
└── install.sh                        # Installation script
```

## Configuration Format

### YAML Routing Rules

Routing rules are automatically generated based on your connected devices. Here's the format:

```yaml
routing_rules:
  - name: "Rule Name"
    applications:
      - "app1"
      - "app2"
    target_device: "bluez_output.XX_XX_XX_XX_XX_XX.1"
    enable_default_fallback: true
```

### Configuration Fields

- **name**: Human-readable rule name
- **applications**: List of application names to match
- **target_device**: Device ID to route to (find with: `pactl list sinks`)
- **enable_default_fallback**: If true, falls back to default device if target is disconnected

### Getting Device IDs

Find your actual device IDs:
```bash
pactl list sinks | grep "Name:"
```

Example output:
```
Name: alsa_output.usb-Logitech_Headset-00.analog-stereo
Name: bluez_output.00_02_3C_AD_09_85.1
Name: alsa_output.pci-0000_0e_00.4.analog-stereo
```

## Usage

### CLI Mode

```bash
# Auto-generate routing rules based on connected devices
python3 src/audio_router.py generate-config config/routing_rules.yaml

# List available audio devices
python3 src/audio_router.py list-devices

# Apply routing rules once
python3 src/audio_router.py apply-rules config/routing_rules.yaml

# Monitor devices and apply rules automatically
python3 src/audio_router.py monitor config/routing_rules.yaml
```

### Daemon Mode

```bash
# Install as systemd user service
./install.sh

# Start the service
systemctl --user start pipewire-router

# Enable on boot
systemctl --user enable pipewire-router

# View logs
journalctl --user -u pipewire-router --no-pager
```

**Note:** Routing rules are automatically generated on every service startup based on currently connected devices. No manual configuration needed!

## System Tray Icon (Optional)

A system tray icon is available for KDE Plasma and Gnome desktops. The tray shows:
- **Left-click**: Display current routing status and connected devices
- **Right-click menu**:
  - **Pause/Resume**: Temporarily disable auto-routing without stopping service
  - **Regenerate Config**: Force re-detection of devices and rule update
  - **View Logs**: Open service logs in default text viewer
  - **Quit**: Exit tray icon (service continues running)

### Launching the Tray Icon

The tray icon is **optional** - the core service works without it.

```bash
# Manual launch from terminal
~/.config/pipewire-router/launch-tray-icon.sh

# Auto-launch on login (installed during ./install.sh)
# Desktop entry: ~/.config/autostart/audio-router-tray.desktop
```

**Requirements:**
- A desktop environment with system tray support (KDE Plasma, Gnome, XFCE, etc.)
- Display server (X11 or Wayland)
- Python GTK bindings: `python-gobject`

**Install on Arch/CachyOS:**
```bash
sudo pacman -S python-gobject
```

**Compatibility:**
- **KDE Plasma 5/6**: Native StatusNotifierItem support
- **Gnome 42+**: Uses DBus StatusNotifierItem
- **XFCE, MATE, etc**: GTK-based tray integration

## Requirements

### Core (Required)
- PipeWire or PulseAudio
- Python 3.8+
- PyYAML

### System Tray Icon (Optional)
- `python-pyqt6` (Arch: `sudo pacman -S python-pyqt6`)
- Display server (X11 or Wayland with proper support)
- Desktop environment with system tray support (KDE Plasma, Gnome, XFCE, MATE)

*Note: Core audio routing works perfectly without the tray icon.*

## Installation

1. Clone or copy this project
2. Run installation: `./install.sh`
3. Start the service: `systemctl --user start pipewire-router`
4. Enable on boot: `systemctl --user enable pipewire-router`

### Optional: System Tray Icon

The system tray icon provides a visual indicator of routing status and quick controls. It auto-launches on login via desktop entry.

**Manual launch:**
```bash
~/.config/pipewire-router/launch-tray-icon.sh
```

**Features:**
- 🟢 **Green circle** - Routes active (target devices connected)
- 🟡 **Yellow circle** - Limited (service running, no target devices connected)
- 🟣 **Purple circle** - Paused (routing paused)
- 🔴 **Red circle** - Stopped (service not running)

**Controls:**
- **Left-click**: Toggle pause/resume routing
- **Right-click**: Context menu (regenerate config, view logs, quit)
- **Hover**: View detailed status with all routing rules

**Autostart:**
The tray icon is configured to auto-launch on login via `~/.config/autostart/audio-router-tray.desktop`. To disable autostart, remove or rename that file.

## Device Names

To find device names:

```bash
pactl list sinks
# or with PipeWire:
pw-cli ls
```

## Troubleshooting

- Check logs: `journalctl --user -u pipewire-router -f`
- Test configuration: `python3 src/audio_router.py apply-rules config/routing_rules.yaml`
- Verify devices: `python3 src/audio_router.py list-devices`

## License

MIT
