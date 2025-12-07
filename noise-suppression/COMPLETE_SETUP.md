# Complete Audio Setup Guide

## Current Status

You have **both** active:
- ✓ **Echo Cancellation** - Removes speaker feedback from game audio
- ✓ **Noise Suppression** - Removes background noise (TV, fan, etc.)

## What This Means

Your microphone input is now cleaned with a two-stage process:

```
Raw Microphone Input
    ↓
[Stage 1: Echo Cancellation]
    ↓ Removes game audio & voices re-broadcast through speakers
    ↓
[Stage 2: Noise Suppression]  
    ↓ Removes TV noise, fan noise, etc.
    ↓
Clean Voice Input for SCUM
```

## Quick Commands

```bash
# Check status
cd ~/pipewire/noise-suppression
python3 noise_suppression_pulseaudio.py status

# Disable noise suppression only (keep echo cancel)
python3 noise_suppression_pulseaudio.py disable

# Disable echo cancel (via other script)
python3 echo_cancellation.py disable
```

## What Gets Removed

**Echo Cancellation removes:**
- Game audio coming back through the mic
- Other players' voices re-broadcast through the mic
- Your own speaker output being recorded

**Noise Suppression removes:**
- TV noise from other room
- Fan noise
- AC humming
- Traffic noise
- General background ambient noise

## What Stays Clear

✓ Your voice (unfiltered, natural)
✓ Game audio through your speakers (normal volume)
✓ Voice chat from other players (normal volume through speakers)

## Usage

Just restart SCUM (or any app) and it will automatically use:
`noise_suppress_source` ← Both stages of processing applied

## Want to Adjust?

Both modules use WebRTC algorithms which auto-tune. Generally they work well as-is, but if you experience:

- **Too much suppression** (your voice sounds muffled)
  ```bash
  python3 noise_suppression_pulseaudio.py disable
  ```
  Then restart your app

- **Not enough suppression** (still hearing TV noise)
  - Consider closing the door to the other room
  - Close windows
  - The algorithms work best with moderate noise levels

## Persistence

Both will persist across reboots because they're PulseAudio modules loaded on demand. To make them auto-start, you'd need to add them to PulseAudio's default.pa or client.conf.
