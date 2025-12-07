#!/bin/sh
set -e

# PipeWire/PulseAudio Audio Router Installation Script

CONFIG_DIR="$HOME/.config/pipewire-router"
# Get the directory where this script is located (portable way)
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$CONFIG_DIR/venv"

echo "Installing PipeWire/PulseAudio Audio Router..."
echo "=============================================="
echo ""

# Check Python version
echo "Checking Python version..."
if ! command -v python3 > /dev/null 2>&1; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "Found Python $python_version"

# Create config directory
echo "Creating configuration directory..."
mkdir -p "$CONFIG_DIR"

# Copy project files
echo "Copying project files..."
cp -r "$PROJECT_DIR"/src "$CONFIG_DIR/"
cp -r "$PROJECT_DIR"/config "$CONFIG_DIR/"
cp "$PROJECT_DIR"/README.md "$CONFIG_DIR/"
cp "$PROJECT_DIR"/requirements.txt "$CONFIG_DIR/"
cp "$PROJECT_DIR"/launch-tray-icon.sh "$CONFIG_DIR/" 2>/dev/null || true
chmod +x "$CONFIG_DIR/launch-tray-icon.sh" 2>/dev/null || true

# Create virtual environment
echo "Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"

# Activate virtual environment and install dependencies
echo "Installing Python dependencies..."
. "$VENV_DIR/bin/activate"
pip install -r "$CONFIG_DIR/requirements.txt"
deactivate

# Make scripts executable
chmod +x "$CONFIG_DIR"/src/audio_router.py

# Generate initial routing configuration based on connected devices
echo "Generating initial routing configuration..."
"$VENV_DIR"/bin/python3 "$CONFIG_DIR"/src/audio_router.py generate-config --output "$CONFIG_DIR"/config/routing_rules.yaml

# Create startup script for systemd
echo "Creating systemd startup script..."
printf '#!/bin/bash\n# Startup script to generate routing config\nVENV_DIR="$HOME/.config/pipewire-router/venv"\nPYTHON="$VENV_DIR/bin/python3"\nAUDIO_ROUTER="$VENV_DIR/../src/audio_router.py"\nCONFIG_FILE="$VENV_DIR/../config/routing_rules.yaml"\n\n"$PYTHON" "$AUDIO_ROUTER" generate-config --output "$CONFIG_FILE" 2>&1 | logger -t pipewire-router-startup\nexit 0\n' > "$CONFIG_DIR/generate-config-startup.sh"

chmod +x "$CONFIG_DIR/generate-config-startup.sh"
mkdir -p "$HOME/.config/systemd/user"

# Create systemd service file
echo "Installing systemd service..."
SERVICE_FILE="$HOME/.config/systemd/user/pipewire-router.service"

printf '[Unit]\nDescription=PipeWire/PulseAudio Automatic Audio Stream Router\nAfter=pipewire.service\n\n[Service]\nType=simple\nExecStartPre=%s/generate-config-startup.sh\nExecStart=%s/bin/python3 %s/src/audio_router.py monitor %s/config/routing_rules.yaml\nRestart=on-failure\nRestartSec=5\nStandardOutput=journal\nStandardError=journal\nEnvironment="PYTHONUNBUFFERED=1"\n\n[Install]\nWantedBy=default.target\n' "$CONFIG_DIR" "$VENV_DIR" "$CONFIG_DIR" "$CONFIG_DIR" > "$SERVICE_FILE"

# Reload systemd
echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

# Install tray icon desktop entry (optional, for GUI users)
echo "Installing tray icon (optional)..."
mkdir -p "$HOME/.config/autostart"
cp "$PROJECT_DIR/audio-router-tray.desktop" "$HOME/.config/autostart/" 2>/dev/null || true

echo ""
echo "Installation complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "1. Start the service: systemctl --user start pipewire-router"
echo "2. Enable on boot: systemctl --user enable pipewire-router"
echo "3. Check status: systemctl --user status pipewire-router --no-pager"
echo ""
echo "Routing rules auto-generate based on connected devices on every startup."
echo ""
echo "Optional - System Tray Icon:"
echo "  The tray icon is optional. The audio router works perfectly without it."
echo ""
echo "  Requirements:"
echo "  - Desktop environment with system tray support (KDE, Gnome, XFCE, etc.)"
echo "  - python-gobject: sudo pacman -S python-gobject"
echo ""
echo "  Launch:"
echo "  - Manual: ~/.config/pipewire-router/launch-tray-icon.sh"
echo "  - Auto-launch on login (installed to ~/.config/autostart/)"
echo ""
echo "Helpful Commands:"
echo "  View logs:        journalctl --user -u pipewire-router --no-pager"
echo "  List devices:     ~/.config/pipewire-router/venv/bin/python3 -c 'import sys; sys.path.insert(0, \"~/.config/pipewire-router/src\"); from device_monitor import DeviceMonitor; m = DeviceMonitor(); print(\"\\n\".join(f\"{d['name']} ({d['type']})\" for d in m.get_all_devices()))'"
echo "  Regenerate rules: ~/.config/pipewire-router/venv/bin/python3 ~/.config/pipewire-router/src/audio_router.py generate-config --output ~/.config/pipewire-router/config/routing_rules.yaml"
echo ""
