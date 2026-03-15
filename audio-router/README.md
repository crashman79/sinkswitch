# PipeWire Audio Router (source)

This folder contains the source and build files for PipeWire Audio Router. For install and run instructions, see the [root README](../README.md).

## Run from source

```bash
pip install -r requirements.txt
python3 run_app.py
```

## Build standalone binary

```bash
./build.sh
./dist/pipewire-audio-router
```

## Config and rules

- **Config dir**: `~/.config/pipewire-router/` (or `AUDIO_ROUTER_CONFIG`)
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
