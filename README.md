# SinkSwitch

Route application audio to different outputs (Bluetooth, USB, HDMI, etc.) by rule. Runs as a standalone GUI on Linux with PipeWire or PulseAudio.

**What it does:** Pick a default output, then define rules so specific apps (browsers, meetings, music players) always use the device you choose. The router runs inside the app—use **Start** / **Stop** in the toolbar. You see active streams, which rule applies, and can close to tray or launch at login.

## Default routing (out of the box)

- **First run** — If no config exists, SinkSwitch auto-generates an initial set of routing rules from your connected devices (e.g. browsers, meetings, media → Bluetooth or USB headset when present). You can edit or remove these in the Routing Rules tab.
- **Router off until you start it** — Until you click **Start** in the toolbar, the router does nothing; all apps use the system default output.
- **Default output** — Once the router is running, streams that do not match any rule go to the **Default output** you set in the toolbar. Matched streams go to the device specified by their rule.

## Install and run

### Option A: GitHub release (Flatpak)

From [Releases](https://github.com/crashman79/sinkswitch/releases), download **`sinkswitch-<version>-x86_64.flatpak`**, then:

```bash
flatpak install --user ./sinkswitch-<version>-x86_64.flatpak
flatpak run io.github.crashman79.sinkswitch
```

### Option B: Flatpak (build from source)

See **[flatpak/README.md](flatpak/README.md)**. After `flatpak-builder --install`, run `flatpak run io.github.crashman79.sinkswitch`.

### Option C: From source or venv

See **Run from source** below or `packaging/install-user-venv.sh`.

On first run the app creates config at `~/.config/sinkswitch/`. Use the GUI to add routing rules and start the router.

## Run from source

```bash
pip install -r requirements.txt
python3 run_app.py
```

Same config and behavior; config dir is `~/.config/sinkswitch/` (or set `AUDIO_ROUTER_CONFIG`).

### Optional: local PyInstaller binary (development)

Releases ship **Flatpak only**. To build a standalone binary on your machine (debugging, etc.):

```bash
./build.sh
./dist/sinkswitch
```

**Onedir:** `./build.sh --onedir` → `./dist/sinkswitch/sinkswitch`. See `packaging/README.md`. For day-to-day use, prefer **Flatpak** or **source/venv**.

### Releasing a new version

Pushing a tag `v*` runs **Flatpak release**: builds `sinkswitch-<version>-x86_64.flatpak` and creates the GitHub release with that artifact.

1. Bump **`src/_version.py`** and **`flatpak/...metainfo.xml`** `<release>` (or let CI rewrite metainfo + `_version.py` from the tag during the workflow).
2. `git tag v0.7.19 && git push origin v0.7.19`

Run **Flatpak release** manually from the Actions tab (**workflow_dispatch**) to test the Flatpak build without creating a release.

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
- For the Flatpak: Freedesktop 24.08 runtime (installed with the bundle)
- For source: Python 3.8+, PyQt6

## License

MIT
