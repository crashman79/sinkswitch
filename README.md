# SinkSwitch

Route application audio to different outputs (Bluetooth, USB, HDMI, etc.) by rule. Runs as a standalone GUI on Linux with PipeWire or PulseAudio.

**What it does:** Pick a default output, then define rules so specific apps (browsers, meetings, music players) always use the device you choose. The router runs inside the app—use **Start** / **Stop** in the toolbar. You see active streams, which rule applies, and can close to tray or launch at login.

## Default routing (out of the box)

- **First run** — If no config exists, SinkSwitch auto-generates an initial set of routing rules from your connected devices (e.g. browsers, meetings, media → Bluetooth or USB headset when present). You can edit or remove these in the Routing Rules tab.
- **Router off until you start it** — Until you click **Start** in the toolbar, the router does nothing; all apps use the system default output.
- **Default output** — Once the router is running, streams that do not match any rule go to the **Default output** you set in the toolbar. Matched streams go to the device specified by their rule.

## Install and run

### Option A: GitHub release (single-file binary)

1. **Download** the Linux binary from [Releases](https://github.com/crashman79/sinkswitch/releases).
2. **Run** it (e.g. `chmod +x sinkswitch && ./sinkswitch`).

### Option B: Flatpak (build locally)

Uses your system PipeWire/Pulse tools on the host while bundling the GUI. See **[flatpak/README.md](flatpak/README.md)**.

After `flatpak-builder --install`, run `flatpak run io.github.crashman79.sinkswitch`.

### Option C: From source or venv

See **Run from source** below or `packaging/install-user-venv.sh`.

On first run the app creates config at `~/.config/sinkswitch/`. Use the GUI to add routing rules and start the router. **Settings** → Add to application menu or launch at login if you like.

## Run from source

```bash
pip install -r requirements.txt
python3 run_app.py
```

Same config and behavior; config dir is `~/.config/sinkswitch/` (or set `AUDIO_ROUTER_CONFIG`).

### Build the binary yourself

```bash
./build.sh
./dist/sinkswitch
```

For a **portable directory** build (same PyInstaller bundle as releases, easier to debug than a single file): `./build.sh --onedir` then run `./dist/sinkswitch/sinkswitch`. For maximum stability on your distro, use **from source** or the venv installer in `packaging/install-user-venv.sh` (see `packaging/README.md`).

### Releasing a new version

Version comes from the **git tag** at build time. The GitHub Action builds the binary and creates the release when you push a tag.

1. Tag and push: `git tag v0.7.11 && git push origin v0.7.11`
2. The workflow builds the binary with that version and creates the GitHub release with the asset.

For a **local** build, run `./build.sh` — it sets the version from the current repo tag.

## Config and rules

- **Config dir**: `~/.config/sinkswitch/` (or `AUDIO_ROUTER_CONFIG`)
- **Bundled example layout**: `config/routing_rules.yaml` in this repo (the app uses `~/.config/sinkswitch/config/routing_rules.yaml` at runtime)

Use the GUI to add rules and pick devices; the **Default output** in the toolbar is where unmatched apps go. See `examples/` for YAML samples.

## CLI (scripting / debugging)

With dependencies installed from the repository root:

```bash
python3 src/audio_router.py list-devices
python3 src/audio_router.py generate-config --output config/routing_rules.yaml
python3 src/audio_router.py apply-rules config/routing_rules.yaml
python3 src/audio_router.py monitor config/routing_rules.yaml
```

The GUI runs the monitor internally; these commands are optional.

## Requirements

- Linux with PipeWire or PulseAudio
- For the release binary: desktop and glibc
- For source: Python 3.8+, PyQt6

## License

MIT
