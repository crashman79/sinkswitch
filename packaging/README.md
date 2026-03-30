# Packaging SinkSwitch (flexibility vs portability)

## What to expect

On Linux, a **single self-contained binary** that bundles **Qt, Python, and dozens of shared libraries** cannot be as stable as using your **distro’s Python and Qt**. Different glibc versions, GPU/Mesa, Wayland vs X11, and PipeWire all interact with those libraries. PyInstaller mitigations (excluding `libxkbcommon`, preferring Wayland when available) narrow the problem but do not remove it.

SinkSwitch runs **`pactl` and `pw-cli` on the host**. The **Flatpak** build does this via `flatpak-spawn --host` (`src/host_command.py`); other sandboxed formats would need similar glue.

## Recommended ways to run (most reliable first)

1. **Flatpak** (see `../flatpak/README.md`) — sandboxed app + `flatpak-spawn --host` for `pactl` / `pw-cli`; reproducible runtime after Flathub-style deps pinning.
2. **From source** — `pip install -r requirements.txt` and `python3 run_app.py` (same as README).
3. **User venv install** — `packaging/install-user-venv.sh` installs dependencies into `~/.local/share/sinkswitch/venv` and a small launcher you can put on `PATH`. Uses your system Python; PyQt6 and PipeWire control stay aligned with the machine.
4. **PyInstaller onedir** — `./build.sh --onedir` produces `dist/sinkswitch/` (folder with `sinkswitch` executable). Same bundling logic as the onefile release, but easier to debug and to override libraries if needed.
5. **PyInstaller onefile** — `./build.sh` → `dist/sinkswitch` (what GitHub Releases ship today). Smallest download; most sensitive to host/system library mismatch.

## Environment hints (frozen builds)

- `SINKSWITCH_USE_SOFTWARE_OPENGL=1` — if GL init or GPU stack causes issues with the UI.
- `QT_QPA_PLATFORM` — e.g. `wayland` or `xcb` if you need to force a platform (the app sets `wayland;xcb` by default when `WAYLAND_DISPLAY` is set and you did not override `QT_QPA_PLATFORM`).
