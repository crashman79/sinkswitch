#!/bin/sh
# Launch tray icon helper
# This script launches the tray icon from a desktop environment

if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    echo "Error: No display server found"
    echo "The tray icon requires a graphical desktop environment (KDE Plasma or Gnome)"
    echo ""
    echo "The audio router works fine without the tray icon:"
    echo "  systemctl --user status pipewire-router"
    echo "  journalctl --user -u pipewire-router --no-pager"
    exit 1
fi

# Try to use system Python which has GTK/GLib available
if command -v python3 > /dev/null 2>&1; then
    exec python3 ~/.config/pipewire-router/src/tray_icon.py "$@"
else
    echo "Error: python3 not found"
    exit 1
fi
