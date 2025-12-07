# Noise Suppression - Quick Start Guide

## 1. Initial Setup (One Time)

Run the setup script:
```bash
cd ~/pipewire/noise-suppression
./setup.fish
```

## 2. List Your Microphones

```bash
./venv/bin/python3 noise_suppression.py list-devices
```

You'll see something like:
```
Available audio input devices:
  [0] alsa_input.usb-Microsoft_Microsoft___LifeCam_HD-3000-02.mono-fallback
  [1] alsa_input.pci-0000_0e_00.4.analog-stereo
```

## 3. Install Noise Suppression

Choose your microphone device name and run:
```bash
./venv/bin/python3 noise_suppression.py install \
  --device "alsa_input.pci-0000_0e_00.4.analog-stereo"
```

## 4. Activate

Either:
- **Restart PipeWire:** `systemctl --user restart pipewire`
- **Log out and back in**
- **Start service now:** `systemctl --user start pipewire-input-filter-chain.service`

## 5. Use It

In your application (Zoom, Teams, Discord, etc.), select **"Noise cancelling source"** as your microphone input.

## Verify It's Working

```bash
./venv/bin/python3 noise_suppression.py status
```

Should show: ✓ Noise suppression is ACTIVE

## Manage It

```bash
# Stop suppression
./venv/bin/python3 noise_suppression.py stop

# Start suppression
./venv/bin/python3 noise_suppression.py start

# Check status
./venv/bin/python3 noise_suppression.py status
```

## Adjust Strength

Edit `~/.config/pipewire/input-filter-chain.conf` and change:

```
"Gate threshold dB" = -40
```

Values:
- `-60` = maximum suppression
- `-40` = balanced (recommended)
- `-20` = minimal suppression
