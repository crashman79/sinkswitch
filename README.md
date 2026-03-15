# PipeWire Audio Tools

A collection of utilities for PipeWire/PulseAudio audio management on Linux.

## Projects

### [Audio Router](./audio-router/)
Standalone app: automatic audio stream routing by application and connected devices. Routes applications to specific outputs (Bluetooth, USB, HDMI, etc.) via a GUI—no systemd or install script required.

**Status**: ✅ Production-ready

## Quick Start (recommended)

```bash
cd audio-router
pip install -r requirements.txt   # once: PyQt6, PyYAML, dbus-python
python3 run_app.py
```

Config is created on first run at `~/.config/pipewire-router/`. Use the GUI to edit rules, start/stop the router, and optionally **Settings → Add to application menu** or **Launch app at login**.

To build a single executable: `./build.sh` → run `./dist/pipewire-audio-router`.

## Optional: install script and systemd

For a traditional install under `~/.config/pipewire-router` with a systemd user service:

```bash
cd audio-router
./install.sh
systemctl --user start pipewire-router
systemctl --user enable pipewire-router
```

See [audio-router/README.md](./audio-router/README.md) for details.

## Project Structure

```
.
├── audio-router/           # Standalone audio routing app
│   ├── src/                # Python source
│   ├── run_app.py          # Standalone launcher (no install required)
│   ├── build.sh            # Build single binary (PyInstaller)
│   ├── run_app.spec        # PyInstaller spec
│   ├── config/             # Example/default config
│   ├── systemd/            # Optional systemd service
│   ├── install.sh          # Optional install script
│   └── README.md
└── README.md
```

## Requirements

- Linux with PipeWire or PulseAudio
- Python 3.8+ (or use the built binary from `build.sh`)
- PyQt6 for the GUI

## License

MIT
