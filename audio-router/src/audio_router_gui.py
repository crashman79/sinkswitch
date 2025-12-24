#!/usr/bin/env python3
"""
PipeWire Audio Router GUI Application
Full-featured graphical interface for managing audio routing rules

Features:
- Visual device list with real-time connection status
- Drag-and-drop rule creation
- Live audio stream monitoring
- Service control (start/stop/restart)
- Configuration editor
- Log viewer

Requirements:
  sudo pacman -S python-pyqt6
"""

import sys
import os
import logging
import subprocess
import yaml
from pathlib import Path
from typing import Dict, List, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Check for display server
if not os.getenv('DISPLAY') and not os.getenv('WAYLAND_DISPLAY'):
    logger.error("No display server found. Run from a graphical desktop environment.")
    sys.exit(1)

# Try to import PyQt6
try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QListWidget, QListWidgetItem, QTextEdit,
        QSplitter, QGroupBox, QTabWidget, QTableWidget, QTableWidgetItem,
        QHeaderView, QMessageBox, QFileDialog, QComboBox, QLineEdit,
        QDialog, QDialogButtonBox, QCheckBox, QScrollArea
    )
    from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QAction
    from PyQt6.QtCore import QTimer, Qt, QSize, pyqtSignal, QThread
except ImportError as e:
    logger.error(f"PyQt6 not available: {e}")
    logger.error("Install with: sudo pacman -S python-pyqt6")
    sys.exit(1)

# Import audio router modules
sys.path.insert(0, str(Path(__file__).parent))
try:
    from device_monitor import DeviceMonitor
    from config_parser import ConfigParser
    from intelligent_audio_router import IntelligentAudioRouter
except ImportError as e:
    logger.error(f"Failed to import audio router modules: {e}")
    sys.exit(1)


class DeviceUpdateThread(QThread):
    """Background thread for updating device list"""
    devices_updated = pyqtSignal(list)
    
    def __init__(self):
        super().__init__()
        self.running = True
    
    def run(self):
        while self.running:
            try:
                monitor = DeviceMonitor()
                devices = monitor.get_devices()
                self.devices_updated.emit(devices)
            except Exception as e:
                logger.error(f"Error updating devices: {e}")
            
            self.msleep(3000)  # Update every 3 seconds
    
    def stop(self):
        self.running = False


class StreamMonitorThread(QThread):
    """Background thread for monitoring active audio streams"""
    streams_updated = pyqtSignal(list)
    
    def __init__(self):
        super().__init__()
        self.running = True
    
    def run(self):
        while self.running:
            try:
                streams = self._get_active_streams()
                self.streams_updated.emit(streams)
            except Exception as e:
                logger.error(f"Error monitoring streams: {e}")
            
            self.msleep(2000)  # Update every 2 seconds
    
    def _get_active_streams(self) -> List[Dict]:
        """Get list of active audio streams"""
        try:
            result = subprocess.run(
                ['pactl', 'list', 'sink-inputs'],
                capture_output=True, text=True, timeout=3
            )
            
            streams = []
            current_stream = {}
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                
                if line.startswith('Sink Input #'):
                    if current_stream:
                        streams.append(current_stream)
                    current_stream = {'id': line.split('#')[1]}
                elif ':' in line and current_stream:
                    key, value = line.split(':', 1)
                    key = key.strip().lower().replace(' ', '_')
                    current_stream[key] = value.strip().strip('"')
            
            if current_stream:
                streams.append(current_stream)
            
            return streams
        except Exception as e:
            logger.error(f"Error getting streams: {e}")
            return []
    
    def stop(self):
        self.running = False


class RuleEditorDialog(QDialog):
    """Dialog for creating/editing routing rules"""
    
    def __init__(self, parent=None, rule=None, devices=None):
        super().__init__(parent)
        self.rule = rule or {}
        self.devices = devices or []
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Edit Routing Rule")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout()
        
        # Rule name
        layout.addWidget(QLabel("Rule Name:"))
        self.name_input = QLineEdit()
        self.name_input.setText(self.rule.get('name', ''))
        self.name_input.setPlaceholderText("e.g., Browser to Bluetooth")
        layout.addWidget(self.name_input)
        
        layout.addSpacing(10)
        
        # Applications
        layout.addWidget(QLabel("Applications (one per line):"))
        self.apps_input = QTextEdit()
        self.apps_input.setMaximumHeight(100)
        apps = self.rule.get('applications', [])
        self.apps_input.setText('\n'.join(apps))
        self.apps_input.setPlaceholderText("firefox\nchrome\nspotify")
        layout.addWidget(self.apps_input)
        
        layout.addSpacing(10)
        
        # Keywords
        layout.addWidget(QLabel("Application Keywords (optional, one per line):"))
        self.keywords_input = QTextEdit()
        self.keywords_input.setMaximumHeight(80)
        keywords = self.rule.get('application_keywords', [])
        self.keywords_input.setText('\n'.join(keywords))
        self.keywords_input.setPlaceholderText("browser\nvideo")
        layout.addWidget(self.keywords_input)
        
        layout.addSpacing(10)
        
        # Target device
        layout.addWidget(QLabel("Target Device:"))
        self.device_combo = QComboBox()
        for device in self.devices:
            display_name = f"{device['name']} ({device['device_type']})"
            self.device_combo.addItem(display_name, device['id'])
        
        # Select current device if editing
        current_target = self.rule.get('target_device', '')
        for i in range(self.device_combo.count()):
            if self.device_combo.itemData(i) == current_target:
                self.device_combo.setCurrentIndex(i)
                break
        
        layout.addWidget(self.device_combo)
        
        layout.addSpacing(10)
        
        # Fallback option
        self.fallback_check = QCheckBox("Enable default fallback")
        self.fallback_check.setChecked(self.rule.get('enable_default_fallback', True))
        self.fallback_check.setToolTip("Use default device if target device is not available")
        layout.addWidget(self.fallback_check)
        
        layout.addStretch()
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    def get_rule(self) -> Dict:
        """Get the configured rule"""
        apps = [app.strip() for app in self.apps_input.toPlainText().split('\n') if app.strip()]
        keywords = [kw.strip() for kw in self.keywords_input.toPlainText().split('\n') if kw.strip()]
        
        rule = {
            'name': self.name_input.text() or 'Unnamed Rule',
            'applications': apps,
            'application_keywords': keywords,
            'target_device': self.device_combo.currentData(),
            'enable_default_fallback': self.fallback_check.isChecked()
        }
        
        # Remove empty lists
        if not rule['application_keywords']:
            del rule['application_keywords']
        
        return rule


class AudioRouterGUI(QMainWindow):
    """Main GUI window for audio router"""
    
    def __init__(self):
        super().__init__()
        self.config_file = Path.home() / '.config/pipewire-router/config/routing_rules.yaml'
        self.devices = []
        self.rules = []
        
        # Background update threads
        self.device_thread = None
        self.stream_thread = None
        
        self.init_ui()
        self.load_config()
        self.start_background_updates()
        self.update_service_status()
    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("PipeWire Audio Router")
        self.setMinimumSize(1000, 700)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Top toolbar
        toolbar_layout = QHBoxLayout()
        
        # Service status indicator
        self.status_label = QLabel("Service: Unknown")
        self.status_label.setStyleSheet("font-weight: bold; padding: 5px;")
        toolbar_layout.addWidget(self.status_label)
        
        toolbar_layout.addStretch()
        
        # Service control buttons
        self.start_btn = QPushButton("▶ Start")
        self.start_btn.clicked.connect(self.start_service)
        toolbar_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("⏸ Stop")
        self.stop_btn.clicked.connect(self.stop_service)
        toolbar_layout.addWidget(self.stop_btn)
        
        self.restart_btn = QPushButton("🔄 Restart")
        self.restart_btn.clicked.connect(self.restart_service)
        toolbar_layout.addWidget(self.restart_btn)
        
        main_layout.addLayout(toolbar_layout)
        
        # Tab widget for different sections
        tabs = QTabWidget()
        main_layout.addWidget(tabs)
        
        # Tab 1: Devices
        devices_tab = self.create_devices_tab()
        tabs.addTab(devices_tab, "🎧 Devices")
        
        # Tab 2: Routing Rules
        rules_tab = self.create_rules_tab()
        tabs.addTab(rules_tab, "🔀 Routing Rules")
        
        # Tab 3: Active Streams
        streams_tab = self.create_streams_tab()
        tabs.addTab(streams_tab, "📊 Active Streams")
        
        # Tab 4: Logs
        logs_tab = self.create_logs_tab()
        tabs.addTab(logs_tab, "📋 Logs")
        
        # Status bar
        self.statusBar().showMessage("Ready")
    
    def create_devices_tab(self) -> QWidget:
        """Create the devices tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh Devices")
        refresh_btn.clicked.connect(self.refresh_devices)
        layout.addWidget(refresh_btn)
        
        # Devices table
        self.devices_table = QTableWidget()
        self.devices_table.setColumnCount(4)
        self.devices_table.setHorizontalHeaderLabels(['Status', 'Name', 'Type', 'Device ID'])
        self.devices_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.devices_table.setAlternatingRowColors(True)
        self.devices_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.devices_table)
        
        return widget
    
    def create_rules_tab(self) -> QWidget:
        """Create the routing rules tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        add_btn = QPushButton("➕ Add Rule")
        add_btn.clicked.connect(self.add_rule)
        button_layout.addWidget(add_btn)
        
        edit_btn = QPushButton("✏️ Edit Rule")
        edit_btn.clicked.connect(self.edit_rule)
        button_layout.addWidget(edit_btn)
        
        delete_btn = QPushButton("🗑️ Delete Rule")
        delete_btn.clicked.connect(self.delete_rule)
        button_layout.addWidget(delete_btn)
        
        button_layout.addStretch()
        
        auto_gen_btn = QPushButton("🤖 Auto-Generate Rules")
        auto_gen_btn.clicked.connect(self.auto_generate_rules)
        button_layout.addWidget(auto_gen_btn)
        
        save_btn = QPushButton("💾 Save Config")
        save_btn.clicked.connect(self.save_config)
        button_layout.addWidget(save_btn)
        
        layout.addLayout(button_layout)
        
        # Rules table
        self.rules_table = QTableWidget()
        self.rules_table.setColumnCount(4)
        self.rules_table.setHorizontalHeaderLabels(['Rule Name', 'Applications', 'Target Device', 'Fallback'])
        self.rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rules_table.setAlternatingRowColors(True)
        self.rules_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.rules_table.itemDoubleClicked.connect(self.edit_rule)
        layout.addWidget(self.rules_table)
        
        return widget
    
    def create_streams_tab(self) -> QWidget:
        """Create the active streams monitoring tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        layout.addWidget(QLabel("Active audio streams:"))
        
        # Streams table
        self.streams_table = QTableWidget()
        self.streams_table.setColumnCount(3)
        self.streams_table.setHorizontalHeaderLabels(['Application', 'Current Output', 'Volume'])
        self.streams_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.streams_table.setAlternatingRowColors(True)
        self.streams_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.streams_table)
        
        return widget
    
    def create_logs_tab(self) -> QWidget:
        """Create the logs viewer tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        refresh_logs_btn = QPushButton("🔄 Refresh")
        refresh_logs_btn.clicked.connect(self.refresh_logs)
        button_layout.addWidget(refresh_logs_btn)
        
        clear_logs_btn = QPushButton("🗑️ Clear")
        clear_logs_btn.clicked.connect(lambda: self.logs_text.clear())
        button_layout.addWidget(clear_logs_btn)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # Log viewer
        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setFont(QFont("Monospace", 9))
        layout.addWidget(self.logs_text)
        
        # Auto-refresh logs
        self.refresh_logs()
        
        return widget
    
    def start_background_updates(self):
        """Start background update threads"""
        # Device monitoring
        self.device_thread = DeviceUpdateThread()
        self.device_thread.devices_updated.connect(self.update_devices)
        self.device_thread.start()
        
        # Stream monitoring
        self.stream_thread = StreamMonitorThread()
        self.stream_thread.streams_updated.connect(self.update_streams)
        self.stream_thread.start()
        
        # Service status timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_service_status)
        self.status_timer.start(3000)  # Update every 3 seconds
    
    def update_devices(self, devices: List[Dict]):
        """Update devices table"""
        self.devices = devices
        
        self.devices_table.setRowCount(len(devices))
        
        for i, device in enumerate(devices):
            # Status indicator
            status_icon = "🟢" if device.get('connected') else "🔴"
            self.devices_table.setItem(i, 0, QTableWidgetItem(status_icon))
            
            # Device name
            self.devices_table.setItem(i, 1, QTableWidgetItem(device['name']))
            
            # Device type
            device_type = device.get('device_type', 'unknown')
            type_icon = self.get_device_type_icon(device_type)
            self.devices_table.setItem(i, 2, QTableWidgetItem(f"{type_icon} {device_type}"))
            
            # Device ID
            device_id = device['id'][:50] + '...' if len(device['id']) > 50 else device['id']
            self.devices_table.setItem(i, 3, QTableWidgetItem(device_id))
    
    def update_streams(self, streams: List[Dict]):
        """Update active streams table"""
        self.streams_table.setRowCount(len(streams))
        
        for i, stream in enumerate(streams):
            # Application name
            app_name = stream.get('application.name', 'Unknown')
            self.streams_table.setItem(i, 0, QTableWidgetItem(app_name))
            
            # Current output device
            sink = stream.get('sink', 'Unknown')
            # Simplify sink name
            if '.' in sink:
                sink = sink.split('.')[-1]
            self.streams_table.setItem(i, 1, QTableWidgetItem(sink))
            
            # Volume
            volume = stream.get('volume', 'N/A')
            if volume != 'N/A' and '%' in volume:
                # Extract first percentage
                volume = volume.split('/')[0].strip()
            self.streams_table.setItem(i, 2, QTableWidgetItem(volume))
    
    def get_device_type_icon(self, device_type: str) -> str:
        """Get emoji icon for device type"""
        icons = {
            'bluetooth': '🔵',
            'bluetooth_earbuds': '🎧',
            'usb_headset': '🎧',
            'usb_speakers': '🔊',
            'analog_speakers': '🔊',
            'hdmi': '📺',
            'unknown': '❓'
        }
        return icons.get(device_type, '🔊')
    
    def update_service_status(self):
        """Update service status indicator"""
        try:
            result = subprocess.run(
                ['systemctl', '--user', 'is-active', 'pipewire-router'],
                capture_output=True, text=True, timeout=2
            )
            
            if result.returncode == 0:
                self.status_label.setText("Service: 🟢 Running")
                self.status_label.setStyleSheet("color: green; font-weight: bold; padding: 5px;")
            else:
                self.status_label.setText("Service: 🔴 Stopped")
                self.status_label.setStyleSheet("color: red; font-weight: bold; padding: 5px;")
        except Exception as e:
            self.status_label.setText("Service: ⚠️ Unknown")
            self.status_label.setStyleSheet("color: orange; font-weight: bold; padding: 5px;")
    
    def refresh_devices(self):
        """Manually refresh device list"""
        try:
            monitor = DeviceMonitor()
            devices = monitor.get_devices()
            self.update_devices(devices)
            self.statusBar().showMessage("Devices refreshed", 2000)
        except Exception as e:
            logger.error(f"Error refreshing devices: {e}")
            QMessageBox.warning(self, "Error", f"Failed to refresh devices: {e}")
    
    def load_config(self):
        """Load routing rules from config file"""
        try:
            if not self.config_file.exists():
                logger.info("No config file found")
                return
            
            with open(self.config_file) as f:
                config = yaml.safe_load(f)
            
            if config and 'routing_rules' in config:
                self.rules = config['routing_rules']
                self.update_rules_table()
            
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    
    def update_rules_table(self):
        """Update rules table with current rules"""
        self.rules_table.setRowCount(len(self.rules))
        
        for i, rule in enumerate(self.rules):
            # Rule name
            self.rules_table.setItem(i, 0, QTableWidgetItem(rule.get('name', 'Unnamed')))
            
            # Applications
            apps = rule.get('applications', [])
            apps_text = ', '.join(apps[:3])
            if len(apps) > 3:
                apps_text += f' (+{len(apps)-3} more)'
            self.rules_table.setItem(i, 1, QTableWidgetItem(apps_text))
            
            # Target device
            target = rule.get('target_device', 'Unknown')
            # Shorten device ID
            if len(target) > 30:
                target = target[:27] + '...'
            self.rules_table.setItem(i, 2, QTableWidgetItem(target))
            
            # Fallback
            fallback = "Yes" if rule.get('enable_default_fallback', True) else "No"
            self.rules_table.setItem(i, 3, QTableWidgetItem(fallback))
    
    def add_rule(self):
        """Add a new routing rule"""
        dialog = RuleEditorDialog(self, devices=self.devices)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            rule = dialog.get_rule()
            self.rules.append(rule)
            self.update_rules_table()
            self.statusBar().showMessage("Rule added (don't forget to save)", 3000)
    
    def edit_rule(self):
        """Edit selected routing rule"""
        current_row = self.rules_table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "No Selection", "Please select a rule to edit")
            return
        
        rule = self.rules[current_row]
        dialog = RuleEditorDialog(self, rule=rule, devices=self.devices)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.rules[current_row] = dialog.get_rule()
            self.update_rules_table()
            self.statusBar().showMessage("Rule updated (don't forget to save)", 3000)
    
    def delete_rule(self):
        """Delete selected routing rule"""
        current_row = self.rules_table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "No Selection", "Please select a rule to delete")
            return
        
        rule_name = self.rules[current_row].get('name', 'Unnamed')
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete rule '{rule_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            del self.rules[current_row]
            self.update_rules_table()
            self.statusBar().showMessage("Rule deleted (don't forget to save)", 3000)
    
    def auto_generate_rules(self):
        """Auto-generate routing rules based on connected devices"""
        reply = QMessageBox.question(
            self, "Auto-Generate Rules",
            "This will replace all current rules with auto-generated ones. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                router = IntelligentAudioRouter()
                config = router.generate_routing_config()
                
                if config and 'routing_rules' in config:
                    self.rules = config['routing_rules']
                    self.update_rules_table()
                    self.statusBar().showMessage("Rules auto-generated (don't forget to save)", 3000)
                else:
                    QMessageBox.warning(self, "No Rules", "Could not generate any rules")
            except Exception as e:
                logger.error(f"Error auto-generating rules: {e}")
                QMessageBox.critical(self, "Error", f"Failed to auto-generate rules: {e}")
    
    def save_config(self):
        """Save routing rules to config file"""
        try:
            config = {'routing_rules': self.rules}
            
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            
            self.statusBar().showMessage("Configuration saved", 2000)
            
            # Ask to restart service
            reply = QMessageBox.question(
                self, "Restart Service",
                "Configuration saved. Restart the audio router service to apply changes?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.restart_service()
        
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save configuration: {e}")
    
    def start_service(self):
        """Start the audio router service"""
        try:
            subprocess.run(['systemctl', '--user', 'start', 'pipewire-router'], check=True)
            self.statusBar().showMessage("Service started", 2000)
            self.update_service_status()
        except Exception as e:
            logger.error(f"Error starting service: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start service: {e}")
    
    def stop_service(self):
        """Stop the audio router service"""
        try:
            subprocess.run(['systemctl', '--user', 'stop', 'pipewire-router'], check=True)
            self.statusBar().showMessage("Service stopped", 2000)
            self.update_service_status()
        except Exception as e:
            logger.error(f"Error stopping service: {e}")
            QMessageBox.critical(self, "Error", f"Failed to stop service: {e}")
    
    def restart_service(self):
        """Restart the audio router service"""
        try:
            subprocess.run(['systemctl', '--user', 'restart', 'pipewire-router'], check=True)
            self.statusBar().showMessage("Service restarted", 2000)
            self.update_service_status()
        except Exception as e:
            logger.error(f"Error restarting service: {e}")
            QMessageBox.critical(self, "Error", f"Failed to restart service: {e}")
    
    def refresh_logs(self):
        """Refresh service logs"""
        try:
            result = subprocess.run(
                ['journalctl', '--user', '-u', 'pipewire-router', '--no-pager', '-n', '100'],
                capture_output=True, text=True, timeout=5
            )
            
            self.logs_text.setPlainText(result.stdout)
            # Scroll to bottom
            cursor = self.logs_text.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.logs_text.setTextCursor(cursor)
            
        except Exception as e:
            logger.error(f"Error refreshing logs: {e}")
            self.logs_text.setPlainText(f"Error loading logs: {e}")
    
    def closeEvent(self, event):
        """Clean up on window close"""
        if self.device_thread:
            self.device_thread.stop()
            self.device_thread.wait()
        
        if self.stream_thread:
            self.stream_thread.stop()
            self.stream_thread.wait()
        
        event.accept()


def main():
    """Main entry point"""
    logger.info("Starting Audio Router GUI")
    
    # Create QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("PipeWire Audio Router")
    
    # Create and show main window
    window = AudioRouterGUI()
    window.show()
    
    # Run event loop
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
