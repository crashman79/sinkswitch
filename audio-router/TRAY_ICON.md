# System Tray Icon Feature

## Overview

A system tray icon has been added for KDE Plasma (primary) and Gnome (with fallback support). The tray icon provides:

- **Visual Status**: Icon shows routing status
- **Hover Tooltip**: Displays current routing rules and default audio device
- **Right-Click Menu**:
  - **Pause/Resume Auto-Routing**: Temporarily stop automatic audio routing for different use cases
  - **Regenerate Config**: Manually regenerate routing rules based on currently connected devices
  - **View Logs**: Open service logs in a viewer
  - **Quit**: Exit the tray application

## Features

### Pause/Resume Auto-Routing
When paused, the systemd service is stopped, allowing you to:
- Use different routing logic for specific tasks
- Avoid automatic switching when testing
- Resume with one click

### Current Status Display
Hovering over the tray icon shows:
- All active routing rules
- Current default audio device
- Whether auto-routing is paused (⏸ indicator)

### Flexible Launch
The tray icon can be:
- **Auto-launched** on login via desktop entry (`~/.config/autostart/audio-router-tray.desktop`)
- **Manually launched** with: `~/.config/pipewire-router/venv/bin/python3 ~/.config/pipewire-router/src/tray_icon.py`
- **Integrated into KDE Plasma** taskbar automatically

## Architecture

### KDE Plasma (Primary)
Uses **DBus StatusNotifierItem** specification for native integration:
- Appears in system tray with standard KDE styling
- Requires: `dbus-python` (usually pre-installed)
- Full menu support with actions

### Gnome (Fallback)
Uses **DBus StatusNotifierItem** first, then falls back to **GTK**:
- Works with Gnome 40+
- Requires: `python3-gi` (usually pre-installed)
- Menu support via right-click

### Other Desktops
Falls back to GTK tray icon if available

## File Structure

```
src/
├── tray_icon.py              # Main tray application (302 lines)
│   ├── AudioRouterTrayIcon   # Base class with core functionality
│   ├── DBusStatusNotifier    # KDE/Gnome DBus implementation
│   └── GtkTrayIcon           # Fallback GTK implementation

audio-router-tray.desktop     # Desktop entry for auto-launch
```

## Installation

The installation script (`install.sh`) automatically:
1. Copies `tray_icon.py` to `~/.config/pipewire-router/src/`
2. Creates `~/.config/autostart/audio-router-tray.desktop` for auto-launch
3. Updates documentation

## Usage

### Manual Launch
```bash
~/.config/pipewire-router/venv/bin/python3 ~/.config/pipewire-router/src/tray_icon.py
```

### Auto-Launch
The tray icon will automatically start on login if `~/.config/autostart/audio-router-tray.desktop` exists.

### Optional Dependencies
The tray icon works best with pre-installed packages on desktop systems:
- **KDE Plasma**: `dbus-python` (for DBus integration)
- **Gnome**: `python3-gi` and `python3-dbus` (for DBus and GTK)

If dependencies are missing, the application will fail gracefully with a helpful error message.

## Code Design

### Separation of Concerns
- **AudioRouterTrayIcon**: Core functionality (no UI dependencies)
  - Get status and routing rules
  - Toggle pause state
  - Regenerate configuration
  - Open logs
  
- **DBusStatusNotifier**: KDE/Gnome DBus interface
  - Implements StatusNotifierItem spec
  - Handles menu actions via DBus
  
- **GtkTrayIcon**: Fallback for Gnome/other desktops
  - Uses GTK3+ for UI
  - Context menu handling
  - Tooltip display

### Error Handling
- Graceful degradation: if DBus unavailable, tries GTK
- If no UI available, exits with helpful error message
- Subprocess errors caught and logged
- File operations wrapped in try-catch

## Future Enhancements

Possible improvements:
1. **Config editor** - Edit routing rules via GUI dialog
2. **Device quick-switch** - Menu items to manually switch devices
3. **Statistics** - Show how many streams routed today
4. **Notifications** - Pop-ups when devices connect/disconnect
5. **Color themes** - Match system dark/light mode
6. **Multi-language** - i18n support

## Testing

To test the tray icon without installing:
```bash
python3 src/tray_icon.py
```

You should see:
- (KDE) Icon appears in system tray
- (Gnome) Icon appears in top bar or notification area
- Hover shows routing rules
- Right-click shows menu options
- Menu actions work (check with `journalctl`)
