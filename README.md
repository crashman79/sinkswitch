# PipeWire Audio Router

Route application audio to different outputs (Bluetooth, USB, HDMI, etc.) by rule. Runs as a standalone GUI on Linux with PipeWire or PulseAudio.

**What it does:** Pick a default output, then define rules so specific apps (browsers, meetings, music players) always use the device you choose. The router runs inside the app—use **Start** / **Stop** in the toolbar. You see active streams, which rule applies, and can close to tray or launch at login.

## Install and run

1. **Download** the Linux binary from [Releases](https://github.com/crashman79/bluetooth-audio-router/releases).
2. **Run** it (e.g. `chmod +x pipewire-audio-router && ./pipewire-audio-router`).
3. On first run the app creates config at `~/.config/pipewire-router/`. Use the GUI to add routing rules and start the router. **Settings** → Add to application menu or launch at login if you like.

## Run from source

```bash
cd audio-router
pip install -r requirements.txt
python3 run_app.py
```

Same config and behavior; config dir is `~/.config/pipewire-router/` (or set `AUDIO_ROUTER_CONFIG`).

### Build the binary yourself

```bash
cd audio-router
./build.sh
./dist/pipewire-audio-router
```

## Requirements

- Linux with PipeWire or PulseAudio
- For the release binary: desktop and glibc
- For source: Python 3.8+, PyQt6

## License

MIT
