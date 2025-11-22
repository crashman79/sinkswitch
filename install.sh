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
cat > "$CONFIG_DIR/generate-config-startup.sh" << 'SCRIPT_EOF'
#!/bin/bash
# Startup script to generate routing config
VENV_DIR="$HOME/.config/pipewire-router/venv"
PYTHON="$VENV_DIR/bin/python3"
AUDIO_ROUTER="$VENV_DIR/../src/audio_router.py"
CONFIG_FILE="$VENV_DIR/../config/routing_rules.yaml"

"$PYTHON" "$AUDIO_ROUTER" generate-config --output "$CONFIG_FILE" 2>&1 | logger -t pipewire-router-startup
exit 0
SCRIPT_EOF

chmod +x "$CONFIG_DIR/generate-config-startup.sh"
mkdir -p "$HOME/.config/systemd/user"

# Create systemd service file
echo "Installing systemd service..."
SERVICE_FILE="$HOME/.config/systemd/user/pipewire-router.service"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=PipeWire/PulseAudio Automatic Audio Stream Router
After=pipewire.service

[Service]
Type=simple
ExecStartPre=$CONFIG_DIR/generate-config-startup.sh
ExecStart=$VENV_DIR/bin/python3 $CONFIG_DIR/src/audio_router.py monitor $CONFIG_DIR/config/routing_rules.yaml
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=default.target
EOF

# Reload systemd
echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

echo ""
echo "Installation complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "1. Start the service: systemctl --user start pipewire-router"
echo "2. Enable on boot: systemctl --user enable pipewire-router"
echo "3. Routing rules auto-generate based on connected devices on every startup"
echo "4. To manually regenerate: $VENV_DIR/bin/python3 $CONFIG_DIR/src/audio_router.py generate-config $CONFIG_DIR/config/routing_rules.yaml"
echo "5. View logs: journalctl --user -u pipewire-router --no-pager"
echo ""
