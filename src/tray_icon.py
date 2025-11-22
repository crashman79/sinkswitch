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
    from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor
    from PyQt6.QtCore import QTimer, Qt, QSize
except ImportError as e:
    logger.error(f"PyQt6 not available: {e}")
    logger.error("Install with: sudo pacman -S python-pyqt6")
    sys.exit(1)


class AudioRouterTrayIcon(QSystemTrayIcon):
    """PyQt6-based system tray icon for audio router with proper Wayland support"""
    
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.paused = False
        self.config_file = Path.home() / '.config/pipewire-router/config/routing_rules.yaml'
        self.last_status = "unknown"
        
        # Set icon
        self.setIcon(self.get_icon_for_status("active"))
        
        # Create context menu
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self.build_menu)
        self.setContextMenu(self.menu)
        
        # Connect left-click to show status popup
        self.activated.connect(self._on_tray_activated)
        
        # Update icon status every 3 seconds
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_icon_status)
        self.timer.start(3000)
        
        # Update tooltip every 3 seconds
        self.tooltip_timer = QTimer()
        self.tooltip_timer.timeout.connect(self._update_tooltip)
        self.tooltip_timer.start(3000)
        
        logger.info("Tray icon initialized")
    
    def build_menu(self):
        """Build the context menu dynamically"""
        self.menu.clear()
        
        # Pause/Resume
        if self.paused:
            pause_action = self.menu.addAction("▶ Resume Auto-Routing")
        else:
            pause_action = self.menu.addAction("⏸ Pause Auto-Routing")
        pause_action.triggered.connect(self.toggle_pause)
        
        # Regenerate config
        regen_action = self.menu.addAction("🔄 Regenerate Config")
        regen_action.triggered.connect(self.regenerate_config)
        
        self.menu.addSeparator()
        
        # View logs
        logs_action = self.menu.addAction("📋 View Logs")
        logs_action.triggered.connect(self.view_logs)
        
        self.menu.addSeparator()
        
        # Quit
        quit_action = self.menu.addAction("❌ Quit Tray Icon")
        quit_action.triggered.connect(self.app.quit)
    
    def _on_tray_activated(self, reason):
        """Handle tray icon activation (left-click toggles pause)"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger or reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_pause()
    
    def _get_status_summary(self) -> str:
        """Get current routing status as plain text"""
        try:
            # Get service status
            result = subprocess.run(
                ['systemctl', '--user', 'is-active', 'pipewire-router'],
                capture_output=True, text=True, timeout=2
            )
            service_status = "Running" if result.returncode == 0 else "Stopped"
            
            # Get connected devices
            connected_devices = self._get_connected_devices()
            
            # Build status text
            status_lines = [
                "🔊 Audio Router Status",
                "",
                f"Service: {service_status}",
            ]
            
            if self.paused:
                status_lines.append("Status: ⏸ PAUSED")
            elif result.returncode == 0:
                # Check if target devices available
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
                except Exception:
                    pass
                
                if target_available:
                    status_lines.append("Status: ✓ Active")
                else:
                    status_lines.append("Status: ⚠ Limited (no target devices)")
            
            # Add routing rules
            try:
                if self.config_file.exists():
                    import yaml
                    with open(self.config_file) as f:
                        config = yaml.safe_load(f)
                    if config and 'routing_rules' in config:
                        status_lines.append("")
                        status_lines.append("Routing Rules:")
                        rules = config['routing_rules']
                        for rule in rules:
                            rule_name = rule.get('name', 'Unknown')
                            apps = rule.get('applications', [])
                            target_device = rule.get('target_device', 'Unknown')
                            target_display = self._normalize_device_name(target_device)
                            
                            # Check if target device is connected
                            is_connected = target_device in connected_devices
                            status_icon = "✓" if is_connected else "✗"
                            
                            status_lines.append(f"  • {rule_name} {status_icon}")
                            if apps:
                                status_lines.append(f"    Apps: {', '.join(apps)}")
                            status_lines.append(f"    → {target_display}")
            except Exception as e:
                logger.debug(f"Error reading config: {e}")
            
            return "\n".join(status_lines)
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return f"Status Error\n\n{str(e)[:100]}"
    
    def get_icon_for_status(self, status):
        """Get colored circle icon based on service status"""
        size = QSize(24, 24)
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Choose color based on status
        if status == "active":
            color = QColor(76, 175, 80)  # Green
        elif status == "limited":
            color = QColor(255, 193, 7)  # Yellow
        elif status == "paused":
            color = QColor(156, 39, 176)  # Purple
        else:
            color = QColor(244, 67, 54)  # Red
        
        # Draw circle
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 20, 20)
        painter.end()
        
        return QIcon(pixmap)
    
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
    
    def _update_icon_status(self):
        """Update icon appearance based on service status"""
        try:
            # Check service status
            result = subprocess.run(
                ['systemctl', '--user', 'is-active', 'pipewire-router'],
                capture_output=True, text=True, timeout=2
            )
            
            if self.paused:
                status = "paused"
            elif result.returncode == 0:
                # Check if target devices are connected
                connected_devices = self._get_connected_devices()
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
                except Exception:
                    pass
                
                status = "active" if target_available else "limited"
            else:
                status = "stopped"
            
            # Update icon if status changed
            if status != self.last_status:
                self.setIcon(self.get_icon_for_status(status))
                self.last_status = status
                
        except Exception as e:
            logger.debug(f"Error updating icon status: {e}")
    
    def _update_tooltip(self):
        """Update the tooltip with current status information"""
        try:
            # Get service status
            result = subprocess.run(
                ['systemctl', '--user', 'is-active', 'pipewire-router'],
                capture_output=True, text=True, timeout=2
            )
            service_status = "Running" if result.returncode == 0 else "Stopped"
            
            # Get connected devices
            connected_devices = self._get_connected_devices()
            
            # Build tooltip text
            tooltip_lines = [
                "🔊 Audio Router",
                "",
                f"Service: {service_status}",
            ]
            
            if self.paused:
                tooltip_lines.append("Status: ⏸ PAUSED")
            elif result.returncode == 0:
                # Check if target devices available
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
                except Exception:
                    pass
                
                if target_available:
                    tooltip_lines.append("Status: 🟢 Active")
                else:
                    tooltip_lines.append("Status: 🟡 Limited (no target devices)")
            
            # Add routing rules
            try:
                if self.config_file.exists():
                    import yaml
                    with open(self.config_file) as f:
                        config = yaml.safe_load(f)
                    if config and 'routing_rules' in config:
                        tooltip_lines.append("")
                        tooltip_lines.append("Routing Rules:")
                        rules = config['routing_rules']
                        for rule in rules:
                            rule_name = rule.get('name', 'Unknown')
                            apps = rule.get('applications', [])
                            target_device = rule.get('target_device', 'Unknown')
                            target_display = self._normalize_device_name(target_device)
                            
                            # Check if target device is connected
                            is_connected = target_device in connected_devices
                            
                            if is_connected:
                                # Show full rule info for connected devices
                                tooltip_lines.append(f"  ✅ {rule_name}")
                                if apps:
                                    tooltip_lines.append(f"     Apps: {', '.join(apps)}")
                                tooltip_lines.append(f"     → {target_display}")
                            else:
                                # Only show rule name for disconnected devices
                                tooltip_lines.append(f"  ❌ {rule_name} (not available)")
            except Exception as e:
                logger.debug(f"Error reading config: {e}")
            
            tooltip_lines.extend(["", "Left-click: Toggle pause/resume", "Right-click: Menu"])
            
            tooltip_text = "\n".join(tooltip_lines)
            self.setToolTip(tooltip_text)
            
        except Exception as e:
            logger.debug(f"Error updating tooltip: {e}")
    
    def toggle_pause(self):
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
            
            self.build_menu()
            self._update_icon_status()
        except Exception as e:
            logger.error(f"Error toggling pause: {e}")
    
    def regenerate_config(self):
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
            logger.info("Config regenerated and service restarted")
            subprocess.run(['systemctl', '--user', 'restart', 'pipewire-router'], check=True)
        except Exception as e:
            logger.error(f"Error regenerating config: {e}")
    
    def view_logs(self):
        """View service logs"""
        try:
            subprocess.Popen([
                'journalctl', '--user', '-u', 'pipewire-router',
                '--no-pager', '-n', '50', '-f'
            ])
        except Exception as e:
            logger.error(f"Error viewing logs: {e}")


def main():
    """Main entry point"""
    logger.info("Starting Audio Router Tray Icon (PyQt6)")
    
    # Create QApplication
    app = QApplication(sys.argv)
    
    # Create tray icon
    tray_icon = AudioRouterTrayIcon(app)
    tray_icon.show()
    
    # Run event loop
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
