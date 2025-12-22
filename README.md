# PipeWire Audio Tools

A collection of utilities for PipeWire/PulseAudio audio management on Linux.

## Projects

### [Audio Router](./audio-router/)
Automatic audio stream routing based on application type and connected devices. Routes applications to specific audio outputs (Bluetooth headsets, USB speakers, HDMI, etc.) automatically.

**Status**: ✅ Production-ready

## Quick Start

```bash
cd audio-router
./install.sh
systemctl --user start pipewire-router
systemctl --user enable pipewire-router
```

For detailed instructions, see [audio-router/README.md](./audio-router/README.md)

## Project Structure

```
.
├── audio-router/              # Audio output routing based on app type
│   ├── src/                   # Python source code
│   ├── config/                # Configuration files
│   ├── systemd/               # Systemd service files
│   ├── install.sh             # Installation script
│   └── README.md              # Audio router documentation
└── README.md                  # This file
```

## Requirements

- Linux with PipeWire or PulseAudio
- Python 3.8+
- System tray support (for audio-router UI)

## License

MIT

---

<sub>Development assisted by AI tools including GitHub Copilot and OpenCode.</sub>

