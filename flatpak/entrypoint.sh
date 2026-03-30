#!/bin/sh
# Pulse client libs (bundled pactl) live under arch-specific paths.
case "$(uname -m)" in
  x86_64)   _pl=lib/x86_64-linux-gnu ;;
  aarch64)  _pl=lib/aarch64-linux-gnu ;;
  *)        _pl=lib/x86_64-linux-gnu ;;
esac
export LD_LIBRARY_PATH="/app/${_pl}/pulseaudio:/app/${_pl}:${LD_LIBRARY_PATH}"
export PYTHONPATH="/app/lib/sinkswitch/src"
exec python3 /app/lib/sinkswitch/run_app.py "$@"
