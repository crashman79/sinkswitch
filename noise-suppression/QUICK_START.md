# Noise Suppression - Quick Start Guide

## Setup (One Time)

```bash
cd ~/pipewire/noise-suppression
./setup.fish
```

## Installation

### Step 1: List Your Microphones

```bash
./venv/bin/python3 noise_suppression.py list-devices
```

Find your microphone device name (e.g., `alsa_input.usb-Microsoft_Microsoft___LifeCam_HD-3000-02.mono-fallback`)

### Step 2: Install Filter Chain

```bash
./venv/bin/python3 noise_suppression.py install \
  --device "alsa_input.usb-Microsoft_Microsoft___LifeCam_HD-3000-02.mono-fallback"
```

### Step 3: Restart PipeWire

**Important**: This step is required to activate the virtual microphone:

```bash
systemctl --user restart pipewire.service
```

Wait a few seconds for PipeWire to restart.

### Step 4: Verify Installation

```bash
./venv/bin/python3 noise_suppression.py status
```

Should show: ✓ Noise suppression is ACTIVE

## Using Noise Suppression

### Option A: For Games/Apps That Auto-Grab Microphone

Set noise suppression as the default microphone:

```bash
./venv/bin/python3 noise_suppression.py set-default
```

The game will automatically use "Noise cancelling source" without you having to configure anything.

### Option B: For Apps with Audio Settings

Open the app's audio settings and select:
- Microphone: **"Noise cancelling source"**

## Manage It

```bash
# Check if it's working
./venv/bin/python3 noise_suppression.py status

# Temporarily stop
./venv/bin/python3 noise_suppression.py stop

# Start again
./venv/bin/python3 noise_suppression.py start
```

## Adjust Noise Suppression Strength

Edit `~/.config/pipewire/input-filter-chain.conf` and find this line:

```
"Gate threshold dB" = -40
```

Change the value:
- `-60` = Maximum suppression (aggressive, may affect voice)
- `-40` = Balanced (default, recommended)
- `-20` = Minimal suppression (cleaner voice, less noise reduction)

Then restart PipeWire: `systemctl --user restart pipewire.service`

## Troubleshooting

### "Noise cancelling source" doesn't appear

1. Check if PipeWire restarted properly:
   ```bash
   systemctl --user status pipewire.service --no-pager | head -5
   ```

2. Try restarting again:
   ```bash
   systemctl --user restart pipewire.service
   ```

3. Wait 2-3 seconds and check status again:
   ```bash
   ./venv/bin/python3 noise_suppression.py status
   ```

### Game still using default microphone after set-default

Some apps cache audio settings. Try:
1. Close and restart the app
2. Check app audio settings - "Noise cancelling source" should be there
3. Make sure it's selected in the app settings

### Sound quality issues

- Adjust the gate threshold (see "Adjust Noise Suppression Strength" above)
- Try `-20` for better voice clarity
- Try `-60` for more aggressive noise removal

