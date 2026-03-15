#!/usr/bin/env python3
"""
Standalone launcher for PipeWire Audio Router.
- As script:  python3 run_app.py  (from audio-router directory)
- As binary:  ./pipewire-audio-router  (after building with build.sh)

Config on first run: ~/.config/pipewire-router/ (or AUDIO_ROUTER_CONFIG).
"""
import os
import sys
from pathlib import Path

_FROZEN = getattr(sys, "frozen", False)
if _FROZEN:
    _APP_DIR = Path(sys.executable).resolve().parent
    _LAUNCH_CMD = str(Path(sys.executable).resolve())
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
    _CONFIG_DIR = Path.home() / ".config" / "pipewire-router"
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
    # Import after path and env are set
    from audio_router_gui import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
