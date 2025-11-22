# PipeWire/PulseAudio Automatic Audio Stream Switching

A comprehensive configuration system for automatic audio stream switching in PipeWire/PulseAudio based on application classes and connected output devices.

## Features

- **Automatic Device Detection**: Monitors connected audio output devices
- **Application-Based Routing**: Routes audio streams based on application class/name
- **Conditional Switching**: Only switches if target device is connected
- **Python Configuration Tool**: CLI and daemon modes for managing routing rules
- **Systemd Integration**: Run as user service for persistent configuration
- **PipeWire & PulseAudio Support**: Works with both audio systems

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

## Requirements

- PipeWire or PulseAudio
- Python 3.8+
- PyYAML
- dbus-python (for device monitoring)

## Installation

1. Clone or copy this project to `~/.config/pipewire-router/`
2. Install dependencies: `pip3 install -r requirements.txt`
3. Run installation: `./install.sh`
4. Configure routing rules in `config/routing_rules.yaml`
5. Start the service: `systemctl --user start pipewire-router`

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
