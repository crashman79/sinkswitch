#!/usr/bin/env python3
"""
System tray icon for PipeWire/PulseAudio Audio Router
Supports KDE Plasma and Gnome (via StatusNotifierItem spec)
"""

import sys
import logging
from pathlib import Path
import subprocess
from typing import Optional, List, Dict

# Try to import dbus and Qt
try:
    from dbus.service import Object, method, signal
    from dbus.mainloop.glib import DBusGMainLoop
    import dbus
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False

try:
    from gi.repository import Gtk, GLib, GdkPixbuf
    GTK_AVAILABLE = True
except ImportError:
    GTK_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AudioRouterTrayIcon:
    """System tray icon for audio router with KDE/Gnome support"""
    
    def __init__(self):
        self.paused = False
        self.config_file = Path.home() / '.config/pipewire-router/config/routing_rules.yaml'
        self.monitoring_enabled = True
        
    def get_status_summary(self) -> str:
        """Get summary of current routing rules and default device"""
        try:
            # Get current default sink
            result = subprocess.run(
                ['pactl', 'info'],
                capture_output=True,
                text=True
            )
            
            default_sink = None
            for line in result.stdout.split('\n'):
                if 'Default Sink:' in line:
                    default_sink = line.split(':', 1)[1].strip()
                    break
            
            # Parse routing rules
            import yaml
            if self.config_file.exists():
                with open(self.config_file) as f:
                    config = yaml.safe_load(f)
                
                rules_summary = "Current Routing Rules:\n"
                if config and 'routing_rules' in config:
                    for rule in config['routing_rules']:
                        name = rule.get('name', 'Unknown')
                        apps = ', '.join(rule.get('applications', [])[:3])
                        if len(rule.get('applications', [])) > 3:
                            apps += ", ..."
                        rules_summary += f"\n• {name}\n  Apps: {apps}"
                else:
                    rules_summary = "No routing rules configured"
            else:
                rules_summary = "Config not found"
            
            status = rules_summary + f"\n\nDefault Device:\n{default_sink if default_sink else 'Unknown'}"
            
            if self.paused:
                status += "\n\n⏸ Auto-routing PAUSED"
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return f"Status unavailable\n{str(e)}"
    
    def toggle_pause(self) -> bool:
        """Pause/resume auto-routing by stopping/starting systemd service"""
        try:
            if self.paused:
                # Resume
                subprocess.run(
                    ['systemctl', '--user', 'start', 'pipewire-router'],
                    check=True
                )
                self.paused = False
                logger.info("Auto-routing resumed")
            else:
                # Pause
                subprocess.run(
                    ['systemctl', '--user', 'stop', 'pipewire-router'],
                    check=True
                )
                self.paused = True
                logger.info("Auto-routing paused")
            
            return self.paused
        except Exception as e:
            logger.error(f"Error toggling pause: {e}")
            return self.paused
    
    def regenerate_config(self) -> bool:
        """Regenerate routing configuration based on current devices"""
        try:
            venv_python = Path.home() / '.config/pipewire-router/venv/bin/python3'
            audio_router = Path.home() / '.config/pipewire-router/src/audio_router.py'
            
            subprocess.run(
                [str(venv_python), str(audio_router), 'generate-config', 
                 '--output', str(self.config_file)],
                check=True
            )
            logger.info("Config regenerated successfully")
            return True
        except Exception as e:
            logger.error(f"Error regenerating config: {e}")
            return False
    
    def open_logs(self) -> None:
        """Open service logs in a text viewer"""
        try:
            subprocess.Popen(
                ['journalctl', '--user', '-u', 'pipewire-router', '--no-pager', '-n', '50']
            )
        except Exception as e:
            logger.error(f"Error opening logs: {e}")


class DBusStatusNotifier(Object, AudioRouterTrayIcon):
    """DBus-based StatusNotifierItem for KDE Plasma and Gnome"""
    
    DBUS_INTERFACE = 'org.kde.StatusNotifierItem'
    
    def __init__(self, bus_name: str = 'org.kde.PipeWireRouter'):
        super().__init__()
        
        DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SessionBus()
        self.bus_name = dbus.service.BusName(bus_name, bus=self.bus)
        self.object_path = '/PipeWireRouter/StatusNotifier'
        
        Object.__init__(self, self.bus, self.object_path)
        
        logger.info("DBus StatusNotifier initialized")
    
    @method(DBUS_INTERFACE, in_signature='', out_signature='s')
    def GetTitle(self):
        return "Audio Router"
    
    @method(DBUS_INTERFACE, in_signature='', out_signature='s')
    def GetStatus(self):
        return "Active" if not self.paused else "Paused"
    
    @method(DBUS_INTERFACE, in_signature='', out_signature='s')
    def GetToolTip(self):
        return self.get_status_summary()
    
    @method(DBUS_INTERFACE, in_signature='', out_signature='as')
    def GetMenu(self):
        """Return menu items as action strings"""
        return [
            "Pause Auto-Routing" if not self.paused else "Resume Auto-Routing",
            "Regenerate Config",
            "View Logs",
            "Quit"
        ]
    
    @method(DBUS_INTERFACE, in_signature='is', out_signature='')
    def MenuAction(self, index: int, action: str):
        """Handle menu action from tray"""
        if index == 0:  # Pause/Resume
            self.toggle_pause()
        elif index == 1:  # Regenerate
            self.regenerate_config()
        elif index == 2:  # Logs
            self.open_logs()
        elif index == 3:  # Quit
            sys.exit(0)


class GtkTrayIcon(AudioRouterTrayIcon):
    """GTK-based tray icon for Gnome and other desktops"""
    
    def __init__(self):
        super().__init__()
        
        if not GTK_AVAILABLE:
            logger.error("GTK not available, cannot create tray icon")
            sys.exit(1)
        
        # Create application
        self.app = Gtk.Application()
        self.app.connect('activate', self.on_activate)
        
        # Create status icon (for legacy support)
        self.status_icon = Gtk.StatusIcon()
        self.status_icon.set_from_icon_name('audio-card')
        self.status_icon.set_tooltip_text("Audio Router")
        self.status_icon.connect('activate', self.on_icon_activate)
        self.status_icon.connect('popup-menu', self.on_popup_menu)
        
        logger.info("GTK tray icon initialized")
    
    def on_activate(self, app):
        """Called when application is activated"""
        pass
    
    def on_icon_activate(self, icon):
        """Handle icon click"""
        self.show_tooltip()
    
    def on_popup_menu(self, icon, button, time):
        """Show context menu on right-click"""
        menu = Gtk.Menu()
        
        # Pause/Resume
        pause_item = Gtk.MenuItem(
            label="Pause Auto-Routing" if not self.paused else "Resume Auto-Routing"
        )
        pause_item.connect('activate', lambda w: self.toggle_pause())
        menu.append(pause_item)
        
        # Regenerate config
        regen_item = Gtk.MenuItem(label="Regenerate Config")
        regen_item.connect('activate', lambda w: self.regenerate_config())
        menu.append(regen_item)
        
        # Separator
        menu.append(Gtk.SeparatorMenuItem())
        
        # View logs
        logs_item = Gtk.MenuItem(label="View Logs")
        logs_item.connect('activate', lambda w: self.open_logs())
        menu.append(logs_item)
        
        # Separator
        menu.append(Gtk.SeparatorMenuItem())
        
        # Quit
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect('activate', lambda w: Gtk.main_quit())
        menu.append(quit_item)
        
        menu.show_all()
        menu.popup(None, None, None, button, time)
    
    def show_tooltip(self):
        """Show tooltip with current status"""
        tooltip = self.get_status_summary()
        self.status_icon.set_tooltip_text(tooltip)
    
    def run(self):
        """Run the GTK application"""
        Gtk.main()


def main():
    """Main entry point - chooses best backend based on availability"""
    
    # Prefer DBus (KDE + Gnome support)
    if DBUS_AVAILABLE:
        try:
            notifier = DBusStatusNotifier()
            logger.info("Starting with DBus StatusNotifier (KDE Plasma/Gnome)")
            
            # Run main loop
            from gi.repository import GLib
            loop = GLib.MainLoop()
            loop.run()
        except Exception as e:
            logger.warning(f"DBus failed: {e}, falling back to GTK")
            if GTK_AVAILABLE:
                icon = GtkTrayIcon()
                icon.run()
            else:
                logger.error("No display server available")
                sys.exit(1)
    elif GTK_AVAILABLE:
        logger.info("Starting with GTK tray icon (Gnome/fallback)")
        icon = GtkTrayIcon()
        icon.run()
    else:
        logger.error("Neither DBus nor GTK available. Install python3-gi and python3-dbus")
        sys.exit(1)


if __name__ == '__main__':
    main()
