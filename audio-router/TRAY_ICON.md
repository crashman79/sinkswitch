# System Tray (Integrated in the App)

## Overview

The main app (`audio_router_gui.py`) includes an **integrated system tray icon** when the desktop provides a system tray (e.g. GNOME, KDE, XFCE, MATE).

### Behavior

- **Icon**: Green circle in the system tray when the app is running.
- **Left-click / double-click**: Restore the main window (Show).
- **Right-click menu**:
  - **Show** – Restore and focus the main window.
  - **▶ Start router** – Start the in-app router.
  - **⏸ Stop router** – Stop the in-app router.
  - **Quit** – Exit the application (stops the router and background threads).

### Close to tray

In **Settings** you can enable **Close to tray**. When enabled:

- Closing the main window **hides** the app instead of quitting.
- The app and router keep running; the tray icon stays visible.
- Use **Show** from the tray to open the window again, or **Quit** to exit.

When “Close to tray” is disabled, closing the window quits the app as usual.

### Requirements

- Desktop with system tray support (StatusNotifierItem / legacy systray).
- PyQt6 (same as the rest of the GUI). No separate tray process or script.

### Legacy: standalone tray script

If you use `install.sh`, the repo still includes `tray_icon.py` and `audio-router-tray.desktop`, which control the **systemd** service (start/stop, regenerate config, view logs). That flow is optional and separate from the standalone app; the app’s built-in tray does not use `tray_icon.py`.
