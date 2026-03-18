# SinkSwitch (source)

This folder contains the source and build files for SinkSwitch. For install and run instructions, see the [root README](../README.md).

## Run from source

```bash
pip install -r requirements.txt
python3 run_app.py
```

## Build standalone binary

```bash
./build.sh
./dist/sinkswitch
```

## Releasing a new version (so in-app version updates)

Version is taken from the **git tag** at build time. No manual edit needed.

1. Tag the release: `git tag v0.7.11` (or the version you want).
2. Run `./build.sh` — it writes `src/_version.py` from the tag and builds `dist/sinkswitch`.
3. Push the tag, create the GitHub release, and upload `dist/sinkswitch`.

The binary will report that version; the update checker uses the same tag from the API.

## Default behavior (out of the box)

- **First run** — If no config exists, the app auto-generates initial routing rules from connected devices (browsers, meetings, media, etc. → Bluetooth/USB headset when available). Edit or remove them in the Routing Rules tab.
- **Router off until Start** — Until you click **Start**, all audio uses the system default; the app does not change routing.
- **Default output** — When the router is running, any stream that does not match a rule is sent to the **Default output** selected in the toolbar.

## Config and rules

- **Config dir**: `~/.config/sinkswitch/` (or `AUDIO_ROUTER_CONFIG`)
- **Rules file**: `config/routing_rules.yaml`

Example:

```yaml
routing_rules:
  - name: "Browsers to headset"
    applications:
      - "firefox"
      - "chrome"
    target_device: "bluez_output.XX_XX_XX_XX_XX_XX.1"   # sink name from Devices tab
    enable_default_fallback: true
```

Use the GUI to add rules and pick devices; the **Default output** in the toolbar is where unmatched apps go.

## CLI (when running from source)

From the `audio-router` directory with deps installed:

```bash
python3 src/audio_router.py list-devices
python3 src/audio_router.py generate-config --output config/routing_rules.yaml
python3 src/audio_router.py apply-rules config/routing_rules.yaml
python3 src/audio_router.py monitor config/routing_rules.yaml
```

The GUI runs the monitor internally; these are for scripting or debugging.
