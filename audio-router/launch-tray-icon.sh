#!/bin/bash
# Launch tray icon helper
# This script launches the tray icon from a desktop environment

# Add logging for debugging
LOG_DIR="$HOME/.local/share/pipewire-router"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/tray-icon.log"

{
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Tray icon launch script started"
    echo "DISPLAY: ${DISPLAY:-unset}"
    echo "WAYLAND_DISPLAY: ${WAYLAND_DISPLAY:-unset}"
    echo "XDG_CURRENT_DESKTOP: ${XDG_CURRENT_DESKTOP:-unset}"
} >> "$LOG_FILE" 2>&1

if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    {
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Error: No display server found"
        echo "The tray icon requires a graphical desktop environment (KDE Plasma or Gnome)"
    } >> "$LOG_FILE" 2>&1
    exit 1
fi

# Add delay to ensure display is ready (useful for autostart)
sleep 2

# Try to use system Python which has PyQt6 available
if command -v python3 > /dev/null 2>&1; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting tray icon" >> "$LOG_FILE" 2>&1
    exec python3 ~/.config/pipewire-router/src/tray_icon.py "$@" >> "$LOG_FILE" 2>&1
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Error: python3 not found" >> "$LOG_FILE" 2>&1
    exit 1
fi
