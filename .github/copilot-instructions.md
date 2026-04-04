# SinkSwitch – contributor notes

- **App**: Standalone GUI for per-app audio routing (PipeWire/PulseAudio). Primary distribution: **Flatpak** from GitHub Releases (`*.flatpak`). Optional local dev: `./build.sh` → `dist/sinkswitch`. Config: `~/.config/sinkswitch/` (Flatpak: app sandbox).
- **Shell**: Use bash for commands/scripts (not fish). For systemd/journal use `--no-pager`.
- **Python**: Use a venv for deps (PEP 668). `build.sh` uses `.venv-build` for optional PyInstaller builds. CI: `.github/workflows/release.yml` builds Flatpak only.
- **Layout**: Repo root has `run_app.py`, `build.sh`, `run_app.spec`, `src/` (GUI, device_monitor, engine, config_parser, intelligent_audio_router), `config/`, `examples/`, `tests/`. Standalone only (no install script or systemd service).
