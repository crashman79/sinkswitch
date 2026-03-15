#!/bin/bash
# Launch PipeWire Audio Router GUI

# Add logging
LOG_DIR="$HOME/.local/share/pipewire-router"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/gui.log"

{
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Audio Router GUI starting"
    echo "DISPLAY: ${DISPLAY:-unset}"
    echo "WAYLAND_DISPLAY: ${WAYLAND_DISPLAY:-unset}"
} >> "$LOG_FILE" 2>&1

if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    {
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Error: No display server found"
        echo "The GUI requires a graphical desktop environment"
    } >> "$LOG_FILE" 2>&1
    exit 1
fi

# Prefer venv if present (after install.sh)
PYTHON="python3"
[ -x "$HOME/.config/pipewire-router/venv/bin/python3" ] && PYTHON="$HOME/.config/pipewire-router/venv/bin/python3"
if ! $PYTHON -c "import PyQt6" 2>/dev/null; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Error: PyQt6 not found" >> "$LOG_FILE" 2>&1
    echo "Error: PyQt6 is required for the GUI"
    echo "Install with: sudo pacman -S python-pyqt6"
    exit 1
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting GUI" >> "$LOG_FILE" 2>&1

# Launch the GUI (run from config dir so imports find src)
cd "$HOME/.config/pipewire-router" 2>/dev/null || true
exec $PYTHON "$HOME/.config/pipewire-router/src/audio_router_gui.py" "$@" >> "$LOG_FILE" 2>&1
