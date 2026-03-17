#!/usr/bin/env python3
"""
Standalone launcher for SinkSwitch.
- As script:  python3 run_app.py  (from audio-router directory)
- As binary:  ./sinkswitch  (after building with build.sh)

Config on first run: ~/.config/sinkswitch/ (or AUDIO_ROUTER_CONFIG).
"""
import os
import sys
from pathlib import Path

_FROZEN = getattr(sys, "frozen", False)
if _FROZEN:
    _APP_DIR = Path(sys.executable).resolve().parent
    _LAUNCH_CMD = str(Path(sys.executable).resolve())
    # Handle update replace-and-restart: we are the new binary run from cache; overwrite target and re-exec
    _argv = list(sys.argv)
    if "--replace-and-run" in _argv:
        idx = _argv.index("--replace-and-run")
        if idx + 1 < len(_argv):
            _target = Path(_argv[idx + 1]).resolve()
            _self = Path(sys.executable).resolve()
            try:
                with open(_self, "rb") as f:
                    _data = f.read()
                with open(_target, "wb") as f:
                    f.write(_data)
                    f.flush()
                    os.fsync(f.fileno())
                _target.chmod(0o755)
                # Restart without --minimized so the window appears after update
                _new_argv = [str(_target)] + [
                    a for i, a in enumerate(_argv)
                    if i != idx and i != idx + 1 and a != "--minimized"
                ]
                os.execv(str(_target), _new_argv)
            except Exception as e:
                print(f"Update apply failed: {e}", file=sys.stderr)
                sys.exit(1)
        sys.exit(0)
else:
    _APP_DIR = Path(__file__).resolve().parent
    _SRC_DIR = _APP_DIR / "src"
    if _SRC_DIR.is_dir() and str(_SRC_DIR) not in sys.path:
        sys.path.insert(0, str(_SRC_DIR))
    _LAUNCH_CMD = f"{sys.executable} {Path(__file__).resolve()}"
    os.chdir(_APP_DIR)

_CONFIG_DIR = os.environ.get("AUDIO_ROUTER_CONFIG")
if _CONFIG_DIR:
    _CONFIG_DIR = Path(_CONFIG_DIR)
else:
    _CONFIG_DIR = Path.home() / ".config" / "sinkswitch"
os.environ["AUDIO_ROUTER_CONFIG"] = str(_CONFIG_DIR)
os.environ["AUDIO_ROUTER_LAUNCH_CMD"] = _LAUNCH_CMD
os.environ["AUDIO_ROUTER_WORKING_DIR"] = str(_APP_DIR)


def _bootstrap_config():
    """Create config dir and default routing_rules.yaml if missing."""
    config_file = _CONFIG_DIR / "config" / "routing_rules.yaml"
    if config_file.exists():
        return
    config_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        from intelligent_audio_router import IntelligentAudioRouter
        import yaml
        router = IntelligentAudioRouter()
        config = router.generate_routing_config()
        with open(config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    except Exception:
        # Minimal empty config so the app can start
        config_file.write_text("routing_rules: []\n")


def main():
    _bootstrap_config()
    if _FROZEN:
        _cache_new = Path.home() / ".cache" / "sinkswitch" / "sinkswitch.new"
        if _cache_new.exists() and "--replace-and-run" not in sys.argv:
            try:
                _cache_new.unlink()
            except Exception:
                pass
    # Import after path and env are set
    from audio_router_gui import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
