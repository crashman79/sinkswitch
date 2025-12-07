# Noise Suppression for Microphone Input

Real-time noise suppression for microphone input in PipeWire using RNNoise.

## Status

🔄 **In Development**

This module is planned to provide:
- Real-time noise suppression for microphone input
- RNNoise-based processing for low CPU usage
- Optional system tray integration with audio router
- Configuration GUI for control

## Planned Features

- **Real-time Processing**: Low-latency noise suppression
- **Multiple Microphones**: Support for selecting input device
- **Toggle Control**: Easy on/off switching
- **System Tray Integration**: Combined control with audio router
- **Bypass Option**: When not needed (e.g., in gaming)

## Architecture

The noise suppression module will:
1. Capture audio from selected microphone
2. Process through RNNoise filter
3. Output to virtual device for applications to use
4. Provide tray icon control and configuration UI

## Coming Soon

More details will be added as the module is developed.
