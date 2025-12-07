#!/usr/bin/env fish
# Noise Suppression Setup Script for PipeWire
# Sets up RNNoise-based microphone noise suppression using LADSPA plugin

set -l script_dir (dirname (status -f))
set -l project_root (dirname "$script_dir")

echo "🔧 Noise Suppression Setup"
echo "=========================="
echo ""

# Check if noise-suppression-for-voice is installed
echo "Checking for LADSPA plugin..."
if test -f /usr/lib/ladspa/librnnoise_ladspa.so
    echo "✓ LADSPA plugin found"
else
    echo "✗ LADSPA plugin not found"
    echo "Install with: pacman -S noise-suppression-for-voice"
    exit 1
end

echo ""
echo "Setting up Python environment..."

# Create virtual environment
if not test -d venv
    echo "Creating virtual environment..."
    python3 -m venv venv
end

# Activate venv and install requirements
echo "Installing Python dependencies..."
set -l python_exe "$script_dir/venv/bin/python3"
$python_exe -m pip install -q -r requirements.txt

echo ""
echo "✓ Setup complete!"
echo ""
echo "Next steps:"
echo "1. List available devices:"
echo "   $python_exe noise_suppression.py list-devices"
echo ""
echo "2. Install noise suppression filter chain:"
echo "   $python_exe noise_suppression.py install --device <device_name>"
echo ""
echo "3. After installation, restart PipeWire or log out/in to activate"
echo ""
echo "4. Select 'Noise cancelling source' in your application audio settings"
