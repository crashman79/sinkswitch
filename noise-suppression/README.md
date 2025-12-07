# Noise Suppression for Webcam Microphone

Real-time voice noise suppression for PipeWire microphone input using RNNoise LADSPA plugin.

## What Is This?

This module provides a simple Python wrapper around the `noise-suppression-for-voice` LADSPA plugin to:
- Create a virtual **"Noise cancelling source"** microphone in PipeWire
- Automatically suppress background noise from your microphone input
- Make the virtual device available to all applications (Zoom, Teams, Discord, etc.)

## Installation

### 1. Install the LADSPA Plugin

**Arch/CachyOS:**
```bash
pacman -S noise-suppression-for-voice
```

**Fedora:**
```bash
sudo dnf copr enable ycollet/linuxmao
sudo dnf install ladspa-noise-suppression-for-voice
```

Verify installation:
```bash
ls -l /usr/lib/ladspa/librnnoise_ladspa.so
```

### 2. Set Up Python Module

```bash
cd noise-suppression
./setup.fish
```

This creates a virtual environment and installs dependencies.

## Quick Start

### 1. List Available Microphones

```bash
~/.config/pipewire-router/noise-suppression-venv/bin/python3 noise_suppression.py list-devices
```

Example output:
```
Available audio input devices:
  [0] alsa_input.usb-Microsoft_Microsoft___LifeCam_HD-3000-02.mono-fallback
      Description: LifeCam HD-3000 Mono
  [1] alsa_input.pci-0000_0e_00.4.analog-stereo
      Description: Starship/Matisse HD Audio Controller Analog Stereo
```

### 2. Install Filter Chain

```bash
~/.config/pipewire-router/noise-suppression-venv/bin/python3 noise_suppression.py install \
  --device "alsa_input.pci-0000_0e_00.4.analog-stereo"
```

This:
- Creates a PipeWire filter chain config
- Creates and enables a systemd user service
- Generates the virtual "Noise cancelling source" device

### 3. Activate (Choose One)

**Option A: Restart PipeWire**
```bash
systemctl --user restart pipewire
```

**Option B: Log Out and Log In**
- Logs you out and back in to restart the session services

**Option C: Start Service Immediately**
```bash
systemctl --user start pipewire-input-filter-chain.service
```

### 4. Use in Applications

In any application (Zoom, Teams, Discord, OBS, etc.):
1. Open audio settings
2. Select **"Noise cancelling source"** as your microphone input
3. Done! Background noise is automatically suppressed

## Usage

```bash
# List available devices
python3 noise_suppression.py list-devices

# Install filter chain (creates virtual microphone)
python3 noise_suppression.py install --device "device_name"

# Check if service is running
python3 noise_suppression.py status

# Start service manually
python3 noise_suppression.py start

# Stop service
python3 noise_suppression.py stop
```

## How It Works

```
Your Microphone Input
        ↓
    [RNNoise LADSPA Plugin]
        ↓
 Virtual "Noise cancelling source"
        ↓
   Available to All Applications
   (Zoom, Teams, Discord, OBS, etc.)
```

The system uses PipeWire's **filter chain** feature to:
1. Capture audio from your selected microphone
2. Pass it through the RNNoise LADSPA plugin for noise suppression
3. Create a virtual microphone device that applications can use
4. Automatically start on login via systemd service

## Configuration

Files created during installation:

- `~/.config/pipewire/input-filter-chain.conf` - PipeWire filter chain config
- `~/.config/systemd/user/pipewire-input-filter-chain.service` - Systemd service

To modify noise suppression strength, edit `input-filter-chain.conf`:

```
control = {
    "Gate threshold dB" = -40   # Lower = more aggressive suppression
}
```

Suggested values:
- `-60`: Maximum suppression (may affect voice clarity)
- `-40`: Balanced (recommended for most users)
- `-20`: Minimal suppression (better voice clarity)

## Troubleshooting

### Virtual microphone not appearing

Check service status:
```bash
systemctl --user status pipewire-input-filter-chain.service
systemctl --user restart pipewire
```

Check PipeWire status:
```bash
systemctl --user status pipewire --no-pager
```

### High CPU usage

The RNNoise plugin uses very low CPU (~1-2%). If experiencing high CPU:
1. Check other services: `systemctl --user`
2. Verify PipeWire is running smoothly
3. Try restarting: `systemctl --user restart pipewire`

### Audio delay/latency

PipeWire filter chains are real-time capable with ~10ms latency. If experiencing delay:
1. Check `/etc/pipewire/pipewire.conf` buffer settings
2. Try: `pw-dump | grep buffer`
3. Standard latency is acceptable for most applications

### "LADSPA plugin not found"

```bash
# Verify installation
ls -l /usr/lib/ladspa/librnnoise_ladspa.so

# Reinstall if missing
pacman -S noise-suppression-for-voice
```

## Uninstall

```bash
# Stop and disable service
systemctl --user stop pipewire-input-filter-chain.service
systemctl --user disable pipewire-input-filter-chain.service

# Remove configuration
rm ~/.config/pipewire/input-filter-chain.conf
rm ~/.config/systemd/user/pipewire-input-filter-chain.service

# Reload systemd
systemctl --user daemon-reload

# Restart PipeWire
systemctl --user restart pipewire
```

## References

- [RNNoise Library](https://github.com/xiph/rnnoise)
- [noise-suppression-for-voice AUR](https://aur.archlinux.org/packages/noise-suppression-for-voice/)
- [Original Medium Article](https://medium.com/@gamunu/linux-noise-cancellation-b9f997f6764d)
- [PipeWire Filter Chain Docs](https://docs.pipewire.org/page_filters.html)

## Related Projects

- [audio-router](../audio-router/) - Output device routing for applications

