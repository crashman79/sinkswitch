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
cp "$PROJECT_DIR"/launch-gui.sh "$CONFIG_DIR/" 2>/dev/null || true
chmod +x "$CONFIG_DIR/launch-gui.sh" 2>/dev/null || true

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

# Install GUI desktop entry
echo "Installing GUI application launcher..."
mkdir -p "$HOME/.local/share/applications"
cp "$PROJECT_DIR/audio-router-gui.desktop" "$HOME/.local/share/applications/" 2>/dev/null || true

echo ""
echo "Installation complete. Optional systemd user service is installed."
echo ""
echo "Start router (runs without GUI):"
echo "  systemctl --user start pipewire-router"
echo "  systemctl --user enable pipewire-router   # start at session login"
echo ""
echo "Or run the GUI app: ~/.config/pipewire-router/launch-gui.sh"
echo "  (Requires PyQt6; see README for standalone binary from Releases.)"
echo ""
