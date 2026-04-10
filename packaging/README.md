# Packaging SinkSwitch

## What to expect

SinkSwitch is distributed as a Flatpak and can also run from source or a user venv on Linux.

SinkSwitch runs **`pactl` and `pw-cli` on the host**. The **Flatpak** build does this via `flatpak-spawn --host` (`src/host_command.py`); other sandboxed formats would need similar glue.

## Recommended ways to run

1. **Flatpak** (see `../flatpak/README.md`) — sandboxed app + `flatpak-spawn --host` for `pactl` / `pw-cli`; reproducible runtime after Flathub-style deps pinning.
2. **From source** — `pip install -r requirements.txt` and `python3 run_app.py` (same as README).
3. **User venv install** — `packaging/install-user-venv.sh` installs dependencies into `~/.local/share/sinkswitch/venv` and a small launcher you can put on `PATH`. Uses your system Python; PyQt6 and PipeWire control stay aligned with the machine.

## Build helpers

- `./build.sh` — build/install Flatpak locally.
- `./build-and-run.sh` — build/install Flatpak then run it.
