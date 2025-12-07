# PipeWire Audio Tools

A collection of utilities for PipeWire/PulseAudio audio management on Linux.

## Projects

### [Audio Router](./audio-router/)
Automatic audio stream routing based on application type and connected devices. Routes applications to specific audio outputs (Bluetooth headsets, USB speakers, HDMI, etc.) automatically.

**Status**: ✅ Production-ready

### [Noise Suppression](./noise-suppression/)
Real-time noise suppression for microphone input using RNNoise.

**Status**: 🔄 In development

## Quick Start

### Audio Router
```bash
cd audio-router
./install.sh
systemctl --user start pipewire-router
systemctl --user enable pipewire-router
```

For detailed instructions, see [audio-router/README.md](./audio-router/README.md)

### Noise Suppression
Coming soon - see [noise-suppression/README.md](./noise-suppression/README.md)

## Project Structure

```
.
├── audio-router/              # Audio output routing based on app type
│   ├── src/                   # Python source code
│   ├── config/                # Configuration files
│   ├── systemd/               # Systemd service files
│   ├── install.sh             # Installation script
│   └── README.md              # Audio router documentation
│
├── noise-suppression/         # Microphone input noise suppression
│   ├── src/                   # Python source code (coming soon)
│   └── README.md              # Noise suppression documentation
│
└── README.md                  # This file
```

## Requirements

- Linux with PipeWire or PulseAudio
- Python 3.8+
- System tray support (for audio-router UI)

## License

MIT
## License

MIT

