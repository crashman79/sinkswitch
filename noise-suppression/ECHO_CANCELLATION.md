# Echo Cancellation - Quick Guide

## What is Echo Cancellation?

Echo cancellation removes the **speaker output that's being picked up by your microphone**. This happens when:
- Game/app sound plays through speakers
- Speakers are near the microphone
- Sound bounces off walls and is re-recorded by the mic

Result: Your game's audio feeds back into SCUM, creating an echo or feedback loop.

## Enable Echo Cancellation (For Your Game)

```bash
cd ~/pipewire/noise-suppression
python3 echo_cancellation.py enable --device "alsa_input.usb-Microsoft_Microsoft___LifeCam_HD-3000-02.mono-fallback"
```

That's it! The echo-cancelled microphone is now the default. Your game will automatically use it.

## Check Status

```bash
python3 echo_cancellation.py status
```

Should show:
```
✓ Echo cancellation is ACTIVE
  Source: echo_cancel_source
  Microphone feedback is being suppressed
```

## Disable (If You Want to Revert)

```bash
python3 echo_cancellation.py disable
```

## How It Works

```
Speaker Output (Game Audio)
        ↓
    [Echo Cancellation Filter]
        ↓
Microphone Input (Without Echo)
        ↓
SCUM (No Speaker Feedback!)
```

PulseAudio's `module-echo-cancel` uses WebRTC echo cancellation algorithm to detect and remove speaker output from the microphone signal in real-time.

## Interactive Menu

For a menu-driven interface:

```bash
~/pipewire/noise-suppression.fish
```

Then choose option 1 (Enable echo cancellation)
