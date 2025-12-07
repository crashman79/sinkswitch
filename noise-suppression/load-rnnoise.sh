#!/usr/bin/env bash
# Load RNNoise filter chain into running PipeWire instance

CONFIG_FILE="$HOME/.config/pipewire/input-filter-chain.conf"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: $CONFIG_FILE not found"
    echo "Run: python3 noise_suppression.py install --device <your_mic>"
    exit 1
fi

echo "Loading noise suppression filter chain..."

# Load using pw-cli
pw-cli load-config "$CONFIG_FILE"

if [ $? -eq 0 ]; then
    echo "✓ Filter chain loaded successfully"
    
    # Wait a moment for the virtual device to be created
    sleep 1
    
    # List sources to confirm
    echo ""
    echo "Available microphone sources:"
    pactl list sources short | grep -E 'input|RUNNING|IDLE'
else
    echo "✗ Failed to load filter chain"
    exit 1
fi
