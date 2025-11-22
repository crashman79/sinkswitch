#!/usr/bin/env python3
"""
Simple system tray icon for PipeWire/PulseAudio Audio Router
For KDE Plasma and Gnome (using PyQt6 for proper Wayland support)

IMPORTANT: Run this ONLY from a desktop environment
The audio router service works fine without this - the tray icon is optional!

Usage:
  python3 ~/.config/pipewire-router/src/tray_icon.py

Install dependencies:
  sudo pacman -S python-pyqt6  # For PyQt6 system tray
"""

import sys
import os
import logging
import subprocess
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Check for display server
if not os.getenv('DISPLAY') and not os.getenv('WAYLAND_DISPLAY'):
    logger.error("No display server found (DISPLAY or WAYLAND_DISPLAY not set)")
    logger.error("Run this script from a graphical desktop environment only.")
    sys.exit(1)

# Try to import PyQt6
try:
    from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
    from PyQt6.QtGui import QIcon, QAction
    from PyQt6.QtCore import QTimer, Qt
except ImportError as e:
    logger.error(f"PyQt6 not available: {e}")
    logger.error("Install with: sudo pacman -S python-pyqt6")
    sys.exit(1)


class StatusWindow(Gtk.Window):
    """Popup window to display status"""
    
    def __init__(self, status_text):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_decorated(True)
        self.set_keep_above(True)
        self.set_border_width(0)
        self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        
        # Detect display server for appropriate positioning
        is_wayland = os.getenv('WAYLAND_DISPLAY') is not None
        
        if is_wayland:
            # Wayland: use absolute positioning near bottom-right
            self.set_position(Gtk.WindowPosition.CENTER)
        else:
            # X11: use mouse position positioning
            self.set_position(Gtk.WindowPosition.MOUSE)
        
        # Create layout with absolute minimal padding
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_margin_top(2)
        box.set_margin_bottom(0)  # No bottom margin
        box.set_margin_start(4)
        box.set_margin_end(4)
        box.set_homogeneous(False)
        
        # Status label - don't expand, minimal size
        label = Gtk.Label()
        label.set_markup(status_text)
        label.set_selectable(False)  # Don't allow text selection
        label.set_line_wrap(True)
        label.set_max_width_chars(45)
        label.set_valign(Gtk.Align.START)
        label.set_halign(Gtk.Align.START)
        label.set_justify(Gtk.Justification.LEFT)
        label.set_size_request(300, -1)  # Fixed width, natural height
        box.pack_start(label, False, False, 0)
        
        # Close button - minimal size
        close_btn = Gtk.Button(label="Close")
        close_btn.set_relief(Gtk.ReliefStyle.NORMAL)
        close_btn.set_hexpand(False)
        close_btn.set_vexpand(False)
        close_btn.set_size_request(-1, 24)  # Standard button height
        box.pack_start(close_btn, False, False, 0)
        close_btn.connect('clicked', lambda w: self.close())
        close_btn.connect('clicked', lambda w: self.close())
        
        self.add(box)
        self.show_all()
        
        # For Wayland: use explicit positioning after showing window
        if is_wayland:
            GLib.idle_add(self._position_for_wayland)
        
        # Auto-close after 10 seconds
        GLib.timeout_add_seconds(10, lambda: self.close() if self.get_visible() else False)
        
        # Close on focus-out
        self.connect('focus-out-event', lambda w, e: (self.close(), False)[1])
    
    def _position_for_wayland(self) -> bool:
        """Position window appropriately for Wayland after window is realized"""
        try:
            # Get screen dimensions
            screen = self.get_screen()
            if screen:
                width = screen.get_width()
                height = screen.get_height()
                # Get window dimensions
                win_width, win_height = self.get_size()
                # Position near bottom-right, above taskbar (typically 40-50px)
                x = max(10, width - win_width - 20)
                y = max(10, height - win_height - 60)
                self.move(x, y)
        except Exception as e:
            logger.debug(f"Error positioning for Wayland: {e}")
        return False  # Don't repeat


class AudioRouterTrayIcon(Gtk.StatusIcon):
    """Simple GTK-based tray icon for audio router"""
    
    def __init__(self):
        super().__init__()
        self.paused = False
        self.config_file = Path.home() / '.config/pipewire-router/config/routing_rules.yaml'
        self.status_window = None
        self.last_status = "unknown"
        
        # Setup icon - use audio-input-microphone as base, we'll update it based on status
        self.set_from_icon_name('audio-input-microphone')
        self.set_tooltip_text("Audio Router")
        self.connect('activate', self.on_click)
        self.connect('popup-menu', self.on_right_click)
        
        # Update icon appearance periodically
        GLib.timeout_add_seconds(3, self._update_icon_status)
        
        logger.info("Tray icon initialized")
    
    def get_status_summary(self) -> str:
        """Get current routing status as HTML markup"""
        try:
            # Get default sink and service status
            result = subprocess.run(
                ['pactl', 'info'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            default_sink = "Unknown"
            for line in result.stdout.split('\n'):
                if 'Default Sink:' in line:
                    default_sink = line.split(':', 1)[1].strip()
                    break
            
            # Normalize sink name for display
            default_sink_display = self._normalize_device_name(default_sink)
            
            # Get service status
            service_status = "Running"
            try:
                status_result = subprocess.run(
                    ['systemctl', '--user', 'is-active', 'pipewire-router'],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                service_status = status_result.stdout.strip().title()
            except:
                service_status = "Unknown"
            
            # Get all connected devices
            connected_devices = self._get_connected_devices()
            
            # Get routing rules with details
            rules_html = ""
            try:
                if self.config_file.exists():
                    import yaml
                    with open(self.config_file) as f:
                        config = yaml.safe_load(f)
                    
                    if config and 'routing_rules' in config:
                        rules = config['routing_rules']
                        rules_html = "<b>Routing Rules:</b>\n"
                        
                        for rule in rules:
                            rule_name = rule.get('name', 'Unknown')
                            apps = rule.get('applications', [])
                            target_device = rule.get('target_device', 'Unknown')
                            target_display = self._normalize_device_name(target_device)
                            
                            # Check if target device is connected
                            is_connected = target_device in connected_devices
                            status_icon = "✓" if is_connected else "✗"
                            
                            # Format app list - show all apps
                            if apps:
                                app_list = ", ".join(apps)
                            else:
                                app_list = "none"
                            
                            rules_html += f"  • <b>{rule_name}</b> {status_icon}\n"
                            rules_html += f"    Apps: {app_list}\n"
                            rules_html += f"    → {target_display}\n"
            except Exception as e:
                logger.debug(f"Error reading config: {e}")
                rules_html = f"<span foreground='#ff6b6b'>Error reading config: {e}</span>"
            
            # Build status message with HTML markup
            status = f"""<b>🔊 Audio Router Status</b>

<b>Service:</b> {service_status}
<b>Default Output:</b> {default_sink_display}

{rules_html}"""
            
            # Determine overall routing health
            if self.paused:
                status += "\n<span foreground='#ff6b6b'><b>⏸️ ROUTING PAUSED</b></span>"
            else:
                # Check if any target devices in rules are connected
                rules_active = False
                try:
                    if self.config_file.exists():
                        import yaml
                        with open(self.config_file) as f:
                            config = yaml.safe_load(f)
                        if config and 'routing_rules' in config:
                            rules = config['routing_rules']
                            for rule in rules:
                                target_device = rule.get('target_device', '')
                                if target_device in connected_devices:
                                    rules_active = True
                                    break
                except:
                    pass
                
                if rules_active:
                    status += "\n<span foreground='#51cf66'><b>✓ Active</b> (devices connected)</span>"
                else:
                    status += "\n<span foreground='#ffa94d'><b>⚠️ Limited</b> (no target devices)</span>"
            
            return status
            
        except Exception as e:
            logger.debug(f"Error getting status: {e}")
            return f"<b>⚠️ Status Error</b>\n\n{str(e)[:100]}"
    
    def _get_connected_devices(self) -> set:
        """Get list of currently connected audio devices"""
        try:
            result = subprocess.run(
                ['pactl', 'list', 'sinks'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            devices = set()
            for line in result.stdout.split('\n'):
                if line.strip().startswith('Name:'):
                    device_name = line.split(':', 1)[1].strip()
                    devices.add(device_name)
            
            return devices
        except Exception as e:
            logger.debug(f"Error getting devices: {e}")
            return set()
    
    def _normalize_device_name(self, device_id: str) -> str:
        """Convert device ID to human-readable name"""
        if not device_id or device_id == "Unknown":
            return "Unknown"
        
        # Common device patterns
        if 'bluez' in device_id:
            return "🔵 Bluetooth Device"
        elif 'usb' in device_id.lower() and ('headset' in device_id.lower() or 'earbuds' in device_id.lower()):
            # Extract USB device name if available
            if '-' in device_id:
                name = device_id.split('-')[1].split('_')[0].title()
                return f"🎧 USB: {name}"
            return "🎧 USB Headset"
        elif 'hdmi' in device_id.lower():
            return "📺 HDMI"
        elif 'usb' in device_id.lower():
            return "🔌 USB Device"
        elif 'alsa' in device_id:
            # Extract analog speaker info
            if 'analog' in device_id:
                return "🔊 Analog Speakers"
            elif 'digital' in device_id:
                return "📢 Digital Output"
            return "🔊 Audio Device"
        else:
            # Generic fallback
            parts = device_id.split('.')
            if len(parts) > 0:
                name = parts[0].replace('_', ' ').title()
                return name
            return device_id[:30]
    
    def on_click(self, icon):
        """Left-click: show status in popup window"""
        try:
            status_html = self.get_status_summary()
            
            # Close existing window if open
            if self.status_window and self.status_window.get_visible():
                self.status_window.close()
            
            # Create new status window
            self.status_window = StatusWindow(status_html)
            logger.info("Status window opened")
        except Exception as e:
            logger.error(f"Error showing status: {e}")
    
    def _update_icon_status(self) -> bool:
        """Update icon appearance based on current status"""
        try:
            # Get connected devices
            connected_devices = self._get_connected_devices()
            
            # Get service status
            service_running = False
            try:
                result = subprocess.run(
                    ['systemctl', '--user', 'is-active', 'pipewire-router'],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                service_running = result.returncode == 0
            except:
                pass
            
            # Determine status
            if self.paused:
                status = "paused"
                icon_name = "media-playback-pause"
            elif not service_running:
                status = "stopped"
                icon_name = "media-playback-stop"
            else:
                # Check if target devices are available
                target_available = False
                try:
                    if self.config_file.exists():
                        import yaml
                        with open(self.config_file) as f:
                            config = yaml.safe_load(f)
                        if config and 'routing_rules' in config:
                            rules = config['routing_rules']
                            for rule in rules:
                                target_device = rule.get('target_device', '')
                                if target_device in connected_devices:
                                    target_available = True
                                    break
                except:
                    pass
                
                if target_available:
                    status = "active"
                    icon_name = "emblem-ok-symbolic"  # Green checkmark
                else:
                    status = "limited"
                    icon_name = "dialog-warning-symbolic"  # Warning triangle
            
            # Update icon if status changed
            if status != self.last_status:
                self.set_from_icon_name(icon_name)
                self.last_status = status
                
        except Exception as e:
            logger.debug(f"Error updating icon status: {e}")
        
        return True  # Continue running timeout
    
    def on_right_click(self, icon, button, time):
        """Right-click: show context menu"""
        menu = Gtk.Menu()
        
        # Pause/Resume
        if self.paused:
            pause_label = "▶ Resume Auto-Routing"
        else:
            pause_label = "⏸ Pause Auto-Routing"
        
        pause_item = Gtk.MenuItem(label=pause_label)
        pause_item.connect('activate', self.toggle_pause)
        menu.append(pause_item)
        
        # Regenerate config
        regen_item = Gtk.MenuItem(label="🔄 Regenerate Config")
        regen_item.connect('activate', self.regenerate_config)
        menu.append(regen_item)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # View logs
        logs_item = Gtk.MenuItem(label="📋 View Logs")
        logs_item.connect('activate', self.view_logs)
        menu.append(logs_item)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # Quit
        quit_item = Gtk.MenuItem(label="❌ Quit Tray Icon")
        quit_item.connect('activate', lambda w: Gtk.main_quit())
        menu.append(quit_item)
        
        menu.show_all()
        
        # Try the older popup() method with positioning function
        # This mimics how other tray applications handle menus
        def position_func(menu, x, y, user_data):
            # Return the pointer position - let the WM handle the rest
            return (x, y, True)
        
        try:
            # Try popup() with position function (GTK 3.22+)
            menu.popup(None, None, position_func, button, time)
        except TypeError:
            # Fallback to popup_at_pointer if popup() fails
            menu.popup_at_pointer(None)
    
    def toggle_pause(self, widget):
        """Pause or resume the service"""
        try:
            if self.paused:
                subprocess.run(['systemctl', '--user', 'start', 'pipewire-router'], check=True)
                self.paused = False
                logger.info("Service resumed")
            else:
                subprocess.run(['systemctl', '--user', 'stop', 'pipewire-router'], check=True)
                self.paused = True
                logger.info("Service paused")
            
            # Update tooltip
            self.set_tooltip_text(self.get_status_summary())
        except Exception as e:
            logger.error(f"Error toggling pause: {e}")
    
    def regenerate_config(self, widget):
        """Regenerate routing config"""
        try:
            venv_python = Path.home() / '.config/pipewire-router/venv/bin/python3'
            audio_router = Path.home() / '.config/pipewire-router/src/audio_router.py'
            
            subprocess.run(
                [str(venv_python), str(audio_router), 'generate-config',
                 '--output', str(self.config_file)],
                check=True,
                timeout=10
            )
            logger.info("Config regenerated")
            self.set_tooltip_text("Config regenerated!")
        except Exception as e:
            logger.error(f"Error regenerating config: {e}")
            self.set_tooltip_text(f"Regen failed: {str(e)[:40]}")
    
    def view_logs(self, widget):
        """Open logs in terminal"""
        try:
            # Try to open in terminal
            subprocess.Popen(
                ['journalctl', '--user', '-u', 'pipewire-router', '--no-pager', '-n', '50']
            )
        except Exception as e:
            logger.error(f"Error opening logs: {e}")


def main():
    """Main entry point"""
    logger.info("Starting Audio Router Tray Icon")
    
    try:
        icon = AudioRouterTrayIcon()
        Gtk.main()
    except KeyboardInterrupt:
        logger.info("Tray icon closed")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
