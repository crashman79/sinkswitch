# SinkSwitch

Route application audio to different outputs (Bluetooth, USB, HDMI, etc.) by rule. Runs as a standalone GUI on Linux with PipeWire or PulseAudio.

**What it does:** Pick a default output, then define rules so specific apps (browsers, meetings, music players) always use the device you choose. The router runs inside the app—use **Start** / **Stop** in the toolbar. You see active streams, which rule applies, and can close to tray or launch at login.

## Default routing (out of the box)

- **First run** — If no config exists, SinkSwitch auto-generates an initial set of routing rules from your connected devices (e.g. browsers, meetings, media → Bluetooth or USB headset when present). You can edit or remove these in the Routing Rules tab.
- **Router off until you start it** — Until you click **Start** in the toolbar, the router does nothing; all apps use the system default output.
- **Default output** — Once the router is running, streams that do not match any rule go to the **Default output** you set in the toolbar. Matched streams go to the device specified by their rule.

## Install and run

1. **Download** the Linux binary from [Releases](https://github.com/crashman79/bluetooth-audio-router/releases).
2. **Run** it (e.g. `chmod +x sinkswitch && ./sinkswitch`).
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
./dist/sinkswitch
```

## Requirements

- Linux with PipeWire or PulseAudio
- For the release binary: desktop and glibc
- For source: Python 3.8+, PyQt6

## License

MIT
