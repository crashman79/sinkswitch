#!/usr/bin/env python3
"""
SinkSwitch – standalone GUI app for per-app audio routing.
Device monitoring and routing run inside this app; no systemd or install script required.

Requirements: Python 3.8+, PyQt6, PyYAML (pip install -r requirements.txt)
Run: python3 run_app.py   (from the audio-router directory)
"""

import sys
import os
import fcntl
import json
import logging
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# GitHub repo for update check (same as Releases link in README)
GITHUB_RELEASES_API = "https://api.github.com/repos/crashman79/sinkswitch/releases/latest"
UPDATES_CACHE_DIR = Path.home() / ".cache" / "sinkswitch"
UPDATES_NEW_BINARY = UPDATES_CACHE_DIR / "sinkswitch.new"
_SINGLE_INSTANCE_LOCK_FILE = None  # hold open for process lifetime

# Bump when tagging a release
__version__ = "0.7.3"

# Config base: set by run_app.py or default
def _acquire_single_instance_lock() -> bool:
    """Acquire an exclusive lock so only one instance runs. Returns True if we got the lock."""
    global _SINGLE_INSTANCE_LOCK_FILE
    if "--replace-and-run" in sys.argv:
        return True
    lock_path = UPDATES_CACHE_DIR / ".lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _SINGLE_INSTANCE_LOCK_FILE = open(lock_path, "w")
        fcntl.flock(_SINGLE_INSTANCE_LOCK_FILE.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (BlockingIOError, OSError):
        if _SINGLE_INSTANCE_LOCK_FILE is not None:
            try:
                _SINGLE_INSTANCE_LOCK_FILE.close()
            except Exception:
                pass
            _SINGLE_INSTANCE_LOCK_FILE = None
        return False


def _config_base() -> Path:
    p = os.environ.get("AUDIO_ROUTER_CONFIG")
    return Path(p) if p else Path.home() / ".config" / "sinkswitch"

# In-memory log capture for standalone (no journal)
_log_buffer: List[str] = []
_log_buffer_max = 500

class BufferHandler(logging.Handler):
    def emit(self, record):
        try:
            _log_buffer.append(self.format(record))
            while len(_log_buffer) > _log_buffer_max:
                _log_buffer.pop(0)
        except Exception:
            pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
_root_logger = logging.getLogger()
_handler = BufferHandler()
_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
_root_logger.addHandler(_handler)

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
        QDialog, QDialogButtonBox, QCheckBox, QScrollArea, QRadioButton, QButtonGroup
    )
    from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QAction
    from PyQt6.QtCore import QTimer, Qt, QSize, pyqtSignal, QThread
    from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
except ImportError as e:
    logger.error(f"PyQt6 not available: {e}")
    logger.error("Install with: sudo pacman -S python-pyqt6")
    sys.exit(1)

# Import audio router modules
sys.path.insert(0, str(Path(__file__).parent))
try:
    from device_monitor import DeviceMonitor
    from config_parser import ConfigParser
    from audio_router_engine import AudioRouterEngine
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
        """Get list of active audio streams (pactl: colon and key=value props)."""
        try:
            result = subprocess.run(
                ['pactl', 'list', 'sink-inputs'],
                capture_output=True, text=True, timeout=3
            )
            streams = []
            current_stream = {}
            for line in result.stdout.split('\n'):
                line_stripped = line.strip()
                if line_stripped.startswith('Sink Input #'):
                    if current_stream:
                        streams.append(current_stream)
                    current_stream = {'id': line_stripped.split('#')[1].strip()}
                elif not current_stream:
                    continue
                elif '=' in line_stripped:
                    # Properties: application.name = "Vivaldi"
                    parts = line_stripped.split('=', 1)
                    if len(parts) == 2:
                        key = parts[0].strip().lower()
                        value = parts[1].strip().strip('"').strip("'")
                        current_stream[key] = value
                        if key == 'application.name' and value:
                            current_stream['application_name'] = value
                elif ':' in line_stripped:
                    key, value = line_stripped.split(':', 1)
                    key = key.strip().lower().replace(' ', '_')
                    current_stream[key] = value.strip().strip('"')
            if current_stream:
                # Prefer application.name / application_name for display
                if 'application_name' not in current_stream and current_stream.get('application.name'):
                    current_stream['application_name'] = current_stream['application.name']
                streams.append(current_stream)
            return streams
        except Exception as e:
            logger.error(f"Error getting streams: {e}")
            return []
    
    def stop(self):
        self.running = False


class MonitorThread(QThread):
    """Runs the audio router monitor loop in the background (in-app mode)."""
    routing_notification = pyqtSignal(str, str)  # title, message

    def __init__(self, config_file: Path):
        super().__init__()
        self.config_file = config_file
        self.stop_event = threading.Event()

    def run(self):
        try:
            rules_ref: List[Dict] = []
            parser = ConfigParser(str(self.config_file))
            rules_ref[:] = parser.parse()
            monitor = DeviceMonitor()
            engine = AudioRouterEngine()

            def regenerate_and_reload():
                try:
                    logger.info("Regenerating routing configuration...")
                    router = IntelligentAudioRouter()
                    config = router.generate_routing_config()
                    self.config_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.config_file, 'w') as f:
                        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
                    rules_ref[:] = ConfigParser(str(self.config_file)).parse()
                    engine.apply_rules(rules_ref)
                except Exception as e:
                    logger.error(f"Failed to regenerate config: {e}")

            def apply_rules():
                results = engine.apply_rules(rules_ref)
                for r in results:
                    if r.get('success') and r.get('routed_count', 0) > 0:
                        self.routing_notification.emit(
                            "Audio Router",
                            f"{r.get('rule_name', 'Route')}: {r.get('message', '')}",
                        )

            monitor.watch_devices(
                apply_rules,
                config_regen_callback=regenerate_and_reload,
                stop_event=self.stop_event,
                rules_ref=rules_ref,
            )
        except Exception as e:
            logger.error(f"Monitor error: {e}")

    def stop(self):
        self.stop_event.set()


class UpdateCheckThread(QThread):
    """Background thread for update check or download."""
    result = pyqtSignal(object)  # (ok, message, tag, url) for check; (ok, message) for download

    def __init__(self, mode: str, download_url: Optional[str] = None):
        super().__init__()
        self.mode = mode  # "check" or "download"
        self.download_url = download_url

    def run(self):
        if self.mode == "check":
            self.result.emit(_update_check())
        elif self.mode == "download" and self.download_url:
            self.result.emit(_update_download(self.download_url))


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
            friendly = device.get('friendly_name') or device.get('name', '')
            dtype = device.get('device_type', '')
            display_name = f"{friendly} ({dtype})" if dtype else friendly
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


def _app_settings_path() -> Path:
    return _config_base() / 'app_settings.json'


def _load_app_settings() -> Dict[str, Any]:
    path = _app_settings_path()
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_app_settings(data: Dict[str, Any]) -> None:
    path = _app_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def _applications_dir() -> Path:
    """User application menu directory (~/.local/share/applications)."""
    return Path.home() / ".local" / "share" / "applications"


def _get_installable_binary_path() -> Optional[Path]:
    """Path to the running binary when built as standalone (frozen). None when running from source or not a single file."""
    launch = os.environ.get("AUDIO_ROUTER_LAUNCH_CMD", "").strip()
    if not launch or " " in launch:
        return None
    p = Path(launch).resolve()
    return p if p.is_file() and os.access(p, os.X_OK) else None


def _install_binary_to_local_bin() -> tuple:
    """Copy the current binary to ~/.local/bin/sinkswitch. Returns (success, message)."""
    src = _get_installable_binary_path()
    if not src:
        return False, "Only available when running the built binary (e.g. ./dist/sinkswitch)."
    dest_dir = Path.home() / ".local" / "bin"
    dest = dest_dir / "sinkswitch"
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        dest.chmod(0o755)
        return True, f"Installed to {dest}\n\nIf ~/.local/bin is on your PATH, you can run 'sinkswitch' from anywhere."
    except Exception as e:
        logger.exception("Install to ~/.local/bin failed")
        return False, str(e)


def _version_tuple(version_str: str) -> Tuple[int, ...]:
    """Parse '0.7.1' or 'v0.7.1' to (0, 7, 1) for comparison."""
    s = version_str.strip().lstrip("v")
    parts = []
    for x in s.split("."):
        try:
            parts.append(int(x))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def _update_check() -> Tuple[bool, str, Optional[str], Optional[str]]:
    """Check for updates. Returns (ok, message, latest_tag, download_url). Only for frozen builds."""
    if not _get_installable_binary_path():
        return False, "Update check is only available when running the built binary.", None, None
    try:
        req = urllib.request.Request(GITHUB_RELEASES_API, headers={"Accept": "application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        tag = data.get("tag_name", "").strip()
        if not tag:
            return False, "No release tag found.", None, None
        latest = _version_tuple(tag)
        current = _version_tuple(__version__)
        if latest <= current:
            return True, f"You have the latest version ({__version__}).", tag, None
        asset_name = "sinkswitch"
        url = None
        for a in data.get("assets", []):
            if a.get("name") == asset_name:
                url = a.get("browser_download_url")
                break
        if not url:
            return False, f"New version {tag} exists but no '{asset_name}' asset found.", tag, None
        return True, f"Update available: {tag}", tag, url
    except urllib.error.HTTPError as e:
        return False, f"Update check failed: HTTP {e.code}", None, None
    except Exception as e:
        logger.debug("Update check failed: %s", e)
        return False, f"Update check failed: {e}", None, None


def _update_download(download_url: str) -> Tuple[bool, str]:
    """Download update to UPDATES_NEW_BINARY. Returns (success, message)."""
    try:
        UPDATES_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(download_url, headers={"Accept": "application/octet-stream"})
        with urllib.request.urlopen(req, timeout=60) as r:
            with open(UPDATES_NEW_BINARY, "wb") as f:
                f.write(r.read())
        UPDATES_NEW_BINARY.chmod(0o755)
        return True, "Update downloaded. Click 'Restart to apply' to use the new version."
    except Exception as e:
        logger.exception("Update download failed")
        return False, str(e)


def _update_restart_to_apply() -> Tuple[bool, str]:
    """Exec the .new binary with --replace-and-run and exit. Returns (True, '') if we're about to exit; (False, error) otherwise."""
    if not UPDATES_NEW_BINARY.exists():
        return False, "No downloaded update found."
    current = _get_installable_binary_path()
    if not current:
        return False, "Restart is only available when running the built binary."
    try:
        os.execv(str(UPDATES_NEW_BINARY), [str(UPDATES_NEW_BINARY), "--replace-and-run", str(current)])
    except Exception as e:
        return False, str(e)
    return True, ""


def _create_app_menu_shortcut() -> Optional[Path]:
    """Add a .desktop entry to the application menu. Returns path or None on failure."""
    app_dir = _applications_dir()
    app_dir.mkdir(parents=True, exist_ok=True)
    path = app_dir / "sinkswitch.desktop"
    exec_cmd = os.environ.get("AUDIO_ROUTER_LAUNCH_CMD", f"{sys.executable} -m run_app")
    work_dir = os.environ.get("AUDIO_ROUTER_WORKING_DIR", str(Path.home()))
    path_line = f"Path={work_dir}\n" if work_dir else ""
    content = f"""[Desktop Entry]
Type=Application
Name=SinkSwitch
Comment=Automatic audio routing for PipeWire/PulseAudio
Exec={exec_cmd}
{path_line}Icon=audio-card
Terminal=false
Categories=AudioVideo;Audio;Settings;
Keywords=audio;routing;pipewire;pulseaudio;
StartupNotify=true
"""
    try:
        path.write_text(content)
        path.chmod(0o644)
        return path
    except Exception as e:
        logger.error("Failed to create application menu shortcut: %s", e)
        return None


def _autostart_desktop_path() -> Path:
    return Path.home() / '.config/autostart/sinkswitch.desktop'


def _is_autostart_enabled() -> bool:
    return _autostart_desktop_path().exists()


def _set_autostart_enabled(enabled: bool, exec_cmd: str, start_minimized: bool = False) -> None:
    path = _autostart_desktop_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        if start_minimized:
            exec_cmd = f"{exec_cmd} --minimized"
        content = f"""[Desktop Entry]
Type=Application
Name=SinkSwitch
Comment=Automatic audio routing (launched at login)
Exec={exec_cmd}
Icon=audio-card
Terminal=false
Categories=AudioVideo;Audio;
X-GNOME-Autostart-enabled=true
"""
        path.write_text(content)
    elif path.exists():
        path.unlink()


class AudioRouterGUI(QMainWindow):
    """Main GUI window for audio router"""

    def __init__(self):
        super().__init__()
        self.config_base = _config_base()
        self.config_file = self.config_base / 'config' / 'routing_rules.yaml'
        self.devices: List[Dict] = []
        self.rules: List[Dict] = []

        # Bootstrap config on first run
        if not self.config_file.exists():
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                router = IntelligentAudioRouter()
                cfg = router.generate_routing_config()
                with open(self.config_file, 'w') as f:
                    yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
            except Exception as e:
                logger.warning("Could not generate initial config: %s", e)
                self.config_file.write_text('routing_rules: []\n')

        settings = _load_app_settings()
        self.start_on_login = settings.get('start_on_login', 'none')
        self.start_routing_on_launch = settings.get('start_routing_on_launch', True)
        self.close_to_tray = settings.get('close_to_tray', False)
        self.start_minimized = settings.get('start_minimized', False)
        self.offer_install_to_bin = settings.get('offer_install_to_bin', True)
        self.monitor_thread: Optional[MonitorThread] = None
        self.device_thread = None
        self.stream_thread = None

        self.init_ui()
        self._setup_tray()
        self.load_config()
        self.start_background_updates()
        self.update_service_status()
        if self.start_routing_on_launch and self.config_file.exists():
            self._start_in_app_monitor()
        QTimer.singleShot(500, self._maybe_offer_install_to_bin)

    def _maybe_offer_install_to_bin(self):
        """Once per install: offer to copy binary to ~/.local/bin if not already there."""
        if not self.offer_install_to_bin:
            return
        src = _get_installable_binary_path()
        if not src:
            return
        local_bin = Path.home() / ".local" / "bin" / "sinkswitch"
        if src.resolve() == local_bin.resolve():
            return
        msg = QMessageBox(self)
        msg.setWindowTitle("Install SinkSwitch")
        msg.setText("Copy SinkSwitch to ~/.local/bin so you can run it from anywhere?")
        msg.setInformativeText("If ~/.local/bin is on your PATH, you can run 'sinkswitch' from the terminal or app launcher.")
        copy_btn = msg.addButton("Copy to ~/.local/bin", QMessageBox.ButtonRole.AcceptRole)
        later_btn = msg.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        dont_btn = msg.addButton("Don't ask again", QMessageBox.ButtonRole.ActionRole)
        msg.setDefaultButton(copy_btn)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == dont_btn:
            self.offer_install_to_bin = False
            _save_app_settings({**_load_app_settings(), 'offer_install_to_bin': False})
        elif clicked == copy_btn:
            ok, text = _install_binary_to_local_bin()
            self.offer_install_to_bin = False
            _save_app_settings({**_load_app_settings(), 'offer_install_to_bin': False})
            if ok:
                QMessageBox.information(self, "Installed", text)
                self.statusBar().showMessage("Binary installed to ~/.local/bin/sinkswitch", 5000)
            else:
                QMessageBox.warning(self, "Install failed", text)

    def _setup_tray(self):
        """Create system tray icon if available."""
        self.tray_icon: Optional[QSystemTrayIcon] = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray_icon = QSystemTrayIcon(QApplication.instance())
        self.tray_icon.setIcon(self._tray_icon_pixmap())
        self.tray_icon.setToolTip("SinkSwitch")
        self.tray_menu = QMenu()
        show_act = self.tray_menu.addAction("Show")
        show_act.triggered.connect(self._show_from_tray)
        self.tray_menu.addSeparator()
        self.tray_start_act = self.tray_menu.addAction("▶ Start router")
        self.tray_start_act.triggered.connect(self.start_service)
        self.tray_stop_act = self.tray_menu.addAction("⏸ Stop router")
        self.tray_stop_act.triggered.connect(self.stop_service)
        self.tray_restart_act = self.tray_menu.addAction("🔄 Restart router")
        self.tray_restart_act.triggered.connect(self.restart_service)
        self.tray_menu.addSeparator()
        quit_act = self.tray_menu.addAction("Quit")
        quit_act.triggered.connect(self._quit_from_tray)
        self.tray_menu.aboutToShow.connect(self._update_tray_menu_state)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _update_tray_menu_state(self):
        """Set Start/Stop/Restart enabled based on router state."""
        if not hasattr(self, 'tray_start_act'):
            return
        running = self._router_running()
        self.tray_start_act.setEnabled(not running)
        self.tray_stop_act.setEnabled(running)
        self.tray_restart_act.setEnabled(running)

    def _tray_icon_pixmap(self) -> QIcon:
        size = QSize(22, 22)
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(76, 175, 80))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 18, 18)
        painter.end()
        return QIcon(pixmap)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger or reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _show_tray_attention(self, message: str, title: str = "SinkSwitch"):
        """Show a brief tray balloon to draw attention when app is in tray."""
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 2500)

    def _show_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self):
        self._cleanup()
        QApplication.instance().quit()

    def _cleanup(self):
        """Stop router and background threads (before quit or real close)."""
        self._stop_in_app_monitor()
        if self.device_thread:
            self.device_thread.stop()
            self.device_thread.wait(2000)
        if self.stream_thread:
            self.stream_thread.stop()
            self.stream_thread.wait(2000)
        if self.tray_icon:
            self.tray_icon.hide()
    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("SinkSwitch")
        self.setMinimumSize(960, 560)
        self.resize(1000, 620)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Top toolbar
        toolbar_layout = QHBoxLayout()
        
        # Router status
        self.status_label = QLabel("Router: Unknown")
        self.status_label.setStyleSheet("font-weight: bold; padding: 5px;")
        toolbar_layout.addWidget(self.status_label)
        
        toolbar_layout.addSpacing(20)
        
        # Default (fallback) output: where unmatched audio goes
        toolbar_layout.addWidget(QLabel("Default output:"))
        self.default_sink_combo = QComboBox()
        self.default_sink_combo.setMinimumWidth(200)
        self.default_sink_combo.setToolTip("Sink used for apps that don't match any rule. New streams go here.")
        self.default_sink_combo.currentIndexChanged.connect(self._on_default_sink_changed)
        toolbar_layout.addWidget(self.default_sink_combo)
        
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

        # Tab 5: Settings
        settings_tab = self.create_settings_tab()
        tabs.addTab(settings_tab, "⚙️ Settings")

        # Tab 6: About
        about_tab = self.create_about_tab()
        tabs.addTab(about_tab, "ℹ️ About")

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
        self.devices_table.setToolTip("Name = friendly name; Device ID = internal sink name used for routing")
        self.devices_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.devices_table.setColumnWidth(0, 56)
        self.devices_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.devices_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.devices_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
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
        self.streams_table.setHorizontalHeaderLabels(['Application', 'Output device', 'Route'])
        self.streams_table.setToolTip("Route = matching rule name, or Default when no rule applies")
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

    def create_settings_tab(self) -> QWidget:
        """Create the Settings tab (start on login, auto-start routing)."""
        widget = QWidget()
        main_layout = QHBoxLayout()
        widget.setLayout(main_layout)

        left_col = QVBoxLayout()
        login_group = QGroupBox("Start on login (Linux desktop)")
        login_layout = QVBoxLayout()
        self.login_none_radio = QRadioButton("None – start manually")
        self.login_xdg_radio = QRadioButton("Launch app at login – XDG Autostart (~/.config/autostart); works on GNOME, KDE, XFCE, MATE, etc.")
        self.login_none_radio.setChecked(self.start_on_login == 'none')
        self.login_xdg_radio.setChecked(self.start_on_login == 'xdg')
        login_layout.addWidget(self.login_none_radio)
        login_layout.addWidget(self.login_xdg_radio)
        self.start_minimized_check = QCheckBox("Start minimized when launched at login")
        self.start_minimized_check.setChecked(self.start_minimized)
        self.start_minimized_check.setToolTip("When enabled, the window stays hidden (tray only) or minimized when the app is started at login.")
        login_layout.addWidget(self.start_minimized_check)
        login_group.setLayout(login_layout)
        left_col.addWidget(login_group)

        self.start_routing_check = QCheckBox("Start routing automatically when app opens")
        self.start_routing_check.setChecked(self.start_routing_on_launch)
        left_col.addWidget(self.start_routing_check)

        self.close_to_tray_check = QCheckBox("Close to tray (minimize to system tray instead of quitting)")
        self.close_to_tray_check.setChecked(self.close_to_tray)
        self.close_to_tray_check.setToolTip("When enabled, closing the window hides the app to the tray; use tray menu to Show or Quit.")
        left_col.addWidget(self.close_to_tray_check)
        left_col.addStretch()
        main_layout.addLayout(left_col)

        right_col = QVBoxLayout()
        install_group = QGroupBox("Install binary to a standard location")
        install_layout = QVBoxLayout()
        install_layout.addWidget(QLabel("Copy the app binary to ~/.local/bin so you can run 'sinkswitch' from anywhere (if that directory is on your PATH). Overwrites existing file if present."))
        self.install_bin_btn = QPushButton("Copy to ~/.local/bin")
        self.install_bin_btn.setMaximumWidth(180)
        self.install_bin_btn.setToolTip("Only available when running the built binary. Overwrites ~/.local/bin/sinkswitch if it already exists.")
        self.install_bin_btn.clicked.connect(self._on_install_to_local_bin)
        if not _get_installable_binary_path():
            self.install_bin_btn.setEnabled(False)
        install_layout.addWidget(self.install_bin_btn)
        install_group.setLayout(install_layout)
        right_col.addWidget(install_group)

        btn_row = QHBoxLayout()
        shortcut_btn = QPushButton("Add to application menu")
        shortcut_btn.setMaximumWidth(220)
        shortcut_btn.setToolTip("Adds or updates a launcher in your application menu. Overwrites the existing launcher if present.")
        shortcut_btn.clicked.connect(self._on_create_app_menu_shortcut)
        btn_row.addWidget(shortcut_btn)
        apply_btn = QPushButton("Apply and save")
        apply_btn.setMaximumWidth(140)
        apply_btn.clicked.connect(self.apply_settings)
        btn_row.addWidget(apply_btn)
        btn_row.addStretch()
        right_col.addLayout(btn_row)
        right_col.addStretch()
        main_layout.addLayout(right_col)
        return widget

    def create_about_tab(self) -> QWidget:
        """Create the About tab with version, technology, and stats."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        layout.addWidget(QLabel("<b>SinkSwitch</b>"))
        layout.addWidget(QLabel(f"Version {__version__}"))
        layout.addSpacing(12)
        layout.addWidget(QLabel("<b>Default routing (out of the box)</b>"))
        layout.addWidget(QLabel(
            "On first run, SinkSwitch creates a config and may auto-generate routing rules from your connected devices "
            "(e.g. browsers, meetings, media → Bluetooth or USB headset). You can edit or remove these in the Routing Rules tab. "
            "Until you click <b>Start</b>, the router does nothing. Once running, matched streams follow rules; "
            "everything else goes to the <b>Default output</b> in the toolbar."
        ))
        layout.addSpacing(12)
        layout.addWidget(QLabel("<b>Technology</b>"))
        layout.addWidget(QLabel("• Python 3, PyQt6 (GUI)"))
        layout.addWidget(QLabel("• PipeWire / PulseAudio (pactl)"))
        layout.addWidget(QLabel("• YAML config, XDG autostart"))
        layout.addSpacing(8)
        layout.addWidget(QLabel("<b>Config and routing rules</b>"))
        layout.addWidget(QLabel("All settings and the rules file are stored under the config directory. Override with the environment variable AUDIO_ROUTER_CONFIG if needed."))
        layout.addWidget(QLabel(f"Config directory: {self.config_base}"))
        layout.addWidget(QLabel(f"Routing rules file: {self.config_file}"))
        layout.addSpacing(8)
        self.about_rules_count_label = QLabel(f"<b>Routing rules</b>: {len(self.rules)}")
        layout.addWidget(self.about_rules_count_label)
        layout.addSpacing(12)
        layout.addWidget(QLabel("<b>Updates</b>"))
        update_row = QHBoxLayout()
        self.update_check_btn = QPushButton("Check for updates")
        self.update_check_btn.clicked.connect(self._on_check_for_updates)
        self.update_status_label = QLabel("")
        self.update_status_label.setWordWrap(True)
        self.update_download_btn = QPushButton("Download update")
        self.update_download_btn.clicked.connect(self._on_download_update)
        self.update_download_btn.hide()
        self.update_restart_btn = QPushButton("Restart to apply update")
        self.update_restart_btn.clicked.connect(self._on_restart_to_apply)
        self.update_restart_btn.hide()
        update_row.addWidget(self.update_check_btn)
        update_row.addWidget(self.update_status_label)
        update_row.addStretch()
        layout.addLayout(update_row)
        update_btn_row = QHBoxLayout()
        update_btn_row.addWidget(self.update_download_btn)
        update_btn_row.addWidget(self.update_restart_btn)
        update_btn_row.addStretch()
        layout.addLayout(update_btn_row)
        self._update_download_url = None
        self._update_check_thread = None
        self._update_download_thread = None
        layout.addSpacing(8)
        layout.addWidget(QLabel("<b>Feedback</b>"))
        feedback_label = QLabel('<a href="mailto:githubfeedback.manger043@simplelogin.com">githubfeedback.manger043@simplelogin.com</a>')
        feedback_label.setOpenExternalLinks(True)
        layout.addWidget(feedback_label)
        layout.addStretch()
        return widget

    def _on_check_for_updates(self):
        self.update_check_btn.setEnabled(False)
        self.update_status_label.setText("Checking...")
        self.update_download_btn.hide()
        self.update_restart_btn.hide()
        self._update_download_url = None
        self._update_check_thread = UpdateCheckThread("check")
        self._update_check_thread.result.connect(self._on_update_check_result)
        self._update_check_thread.finished.connect(lambda: self.update_check_btn.setEnabled(True))
        self._update_check_thread.start()

    def _on_update_check_result(self, result):
        ok, message, tag, url = result
        self.update_status_label.setText(message)
        if ok and url:
            self._update_download_url = url
            self.update_download_btn.show()
        else:
            self._update_download_url = None
            self.update_download_btn.hide()
        self.update_restart_btn.hide()

    def _on_download_update(self):
        if not self._update_download_url:
            return
        self.update_download_btn.setEnabled(False)
        self.update_status_label.setText("Downloading...")
        self._update_download_thread = UpdateCheckThread("download", self._update_download_url)
        self._update_download_thread.result.connect(self._on_update_download_result)
        self._update_download_thread.finished.connect(lambda: self.update_download_btn.setEnabled(True))
        self._update_download_thread.start()

    def _on_update_download_result(self, result):
        ok, message = result
        self.update_status_label.setText(message)
        if ok:
            self.update_download_btn.hide()
            self.update_restart_btn.show()
        else:
            QMessageBox.warning(self, "Download failed", message)

    def _on_restart_to_apply(self):
        ok, err = _update_restart_to_apply()
        if not ok:
            QMessageBox.warning(self, "Restart failed", err)
        # else: we exec and exit

    def _on_install_to_local_bin(self):
        ok, msg = _install_binary_to_local_bin()
        if ok:
            QMessageBox.information(self, "Installed", msg)
            self.statusBar().showMessage("Binary installed to ~/.local/bin/sinkswitch", 5000)
        else:
            QMessageBox.warning(self, "Install failed", msg)

    def _on_create_app_menu_shortcut(self):
        p = _create_app_menu_shortcut()
        if p:
            QMessageBox.information(
                self,
                "Added to application menu",
                "SinkSwitch has been added to your application menu.\n\nYou can launch it from your app launcher (e.g. Activities, application grid) without using a terminal."
            )
            self.statusBar().showMessage("Added to application menu", 3000)
        else:
            QMessageBox.warning(
                self,
                "Could not add to menu",
                "Failed to write the menu shortcut. Check that ~/.local/share/applications is writable."
            )

    def apply_settings(self):
        """Save settings and apply autostart."""
        start_on_login = 'xdg' if self.login_xdg_radio.isChecked() else 'none'
        start_routing = self.start_routing_check.isChecked()
        close_to_tray = self.close_to_tray_check.isChecked()
        start_minimized = self.start_minimized_check.isChecked()
        self.start_on_login = start_on_login
        self.start_routing_on_launch = start_routing
        self.close_to_tray = close_to_tray
        self.start_minimized = start_minimized
        _save_app_settings({
            'start_on_login': start_on_login,
            'start_routing_on_launch': start_routing,
            'close_to_tray': close_to_tray,
            'start_minimized': start_minimized,
            'offer_install_to_bin': getattr(self, 'offer_install_to_bin', True),
        })
        exec_cmd = os.environ.get('AUDIO_ROUTER_LAUNCH_CMD', f'{sys.executable} -m run_app')
        if start_on_login == 'xdg':
            _set_autostart_enabled(True, exec_cmd, start_minimized=start_minimized)
        else:
            _set_autostart_enabled(False, exec_cmd)
        self.update_service_status()
        self.statusBar().showMessage("Settings saved", 2000)

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
    
    def _refresh_default_sink_combo(self):
        """Refresh default-sink dropdown from current devices and pactl default."""
        self.default_sink_combo.blockSignals(True)
        self.default_sink_combo.clear()
        try:
            default_id = DeviceMonitor().get_default_sink()
        except Exception:
            default_id = None
        for d in self.devices:
            friendly = d.get('friendly_name') or d.get('name') or d.get('id', '')
            self.default_sink_combo.addItem(friendly, d['id'])
        idx = next((i for i in range(self.default_sink_combo.count()) if self.default_sink_combo.itemData(i) == default_id), 0)
        self.default_sink_combo.setCurrentIndex(idx)
        self.default_sink_combo.blockSignals(False)

    def _on_default_sink_changed(self):
        """User selected a new default (fallback) output; restart router to reapply rules immediately."""
        sink_id = self.default_sink_combo.currentData()
        if not sink_id:
            return
        if not DeviceMonitor().set_default_sink(sink_id):
            self.statusBar().showMessage("Failed to set default output", 3000)
            return
        self.statusBar().showMessage("Default output updated", 2000)
        if self._router_running():
            self.restart_service()
            self.statusBar().showMessage("Default output updated; router restarted", 2000)

    def update_devices(self, devices: List[Dict]):
        """Update devices table and default-sink combo"""
        self.devices = devices
        self.devices_table.setRowCount(len(devices))
        self._refresh_default_sink_combo()
        # Refresh rules table so Target Device column shows friendly names now that we have devices
        self.update_rules_table()
        
        for i, device in enumerate(devices):
            # Status indicator
            status_icon = "🟢" if device.get('connected') else "🔴"
            self.devices_table.setItem(i, 0, QTableWidgetItem(status_icon))
            # Friendly name (fallback to name/id)
            display_name = device.get('friendly_name') or device.get('name') or device.get('id', '')
            self.devices_table.setItem(i, 1, QTableWidgetItem(display_name))
            # Device type
            device_type = device.get('device_type', 'unknown')
            type_icon = self.get_device_type_icon(device_type)
            self.devices_table.setItem(i, 2, QTableWidgetItem(f"{type_icon} {device_type}"))
            # Device ID (internal sink name)
            device_id = device['id'][:50] + '...' if len(device['id']) > 50 else device['id']
            self.devices_table.setItem(i, 3, QTableWidgetItem(device_id))
    
    def _get_sink_index_to_name(self) -> Dict[str, str]:
        """Return dict sink_index -> sink_name from pactl list sinks short."""
        out: Dict[str, str] = {}
        try:
            r = subprocess.run(
                ['pactl', 'list', 'sinks', 'short'],
                capture_output=True, text=True, timeout=2
            )
            if r.returncode != 0:
                return out
            for line in r.stdout.strip().split('\n'):
                parts = line.split('\t')
                if len(parts) >= 2:
                    out[parts[0].strip()] = parts[1].strip()
        except Exception:
            pass
        return out

    def _rule_for_app(self, app_name: str) -> Optional[Dict]:
        """Return the first routing rule that matches this application, or None (Default)."""
        if not app_name or not self.rules:
            return None
        app_lower = app_name.lower()
        for rule in self.rules:
            apps = rule.get('applications', [])
            keywords = rule.get('application_keywords', [])
            for a in apps:
                if a.lower() in app_lower or app_lower in a.lower():
                    return rule
            for kw in keywords:
                if kw.lower() in app_lower:
                    return rule
        return None

    def update_streams(self, streams: List[Dict]):
        """Update active streams table: app, output device (friendly), route (rule or Default)."""
        sink_index_to_name = self._get_sink_index_to_name()
        self.streams_table.setRowCount(len(streams))
        for i, stream in enumerate(streams):
            app_name = (
                stream.get('application_name')
                or stream.get('application.name')
                or stream.get('media.name')
                or stream.get('node.name')
                or 'Unknown'
            )
            self.streams_table.setItem(i, 0, QTableWidgetItem(app_name))
            # Output device: resolve sink index -> name -> friendly
            sink_idx = stream.get('sink', '')
            sink_name = sink_index_to_name.get(sink_idx, sink_idx)
            device = next((d for d in self.devices if d.get('id') == sink_name), None)
            out_label = (device.get('friendly_name') or device.get('name')) if device else sink_name
            if not out_label:
                out_label = sink_name or 'Unknown'
            self.streams_table.setItem(i, 1, QTableWidgetItem(out_label))
            # Route: matching rule name or Default
            rule = self._rule_for_app(app_name)
            route_label = rule.get('name', 'Default') if rule else 'Default'
            self.streams_table.setItem(i, 2, QTableWidgetItem(route_label))
    
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
    
    def _router_running(self) -> bool:
        return self.monitor_thread is not None and self.monitor_thread.isRunning()

    def update_service_status(self):
        """Update router status and Start/Stop/Restart button states."""
        running = self._router_running()
        if running:
            self.status_label.setText("Router: 🟢 Running")
            self.status_label.setStyleSheet("color: green; font-weight: bold; padding: 5px;")
        else:
            self.status_label.setText("Router: 🔴 Stopped")
            self.status_label.setStyleSheet("color: red; font-weight: bold; padding: 5px;")
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.restart_btn.setEnabled(running)
    
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
        if getattr(self, 'about_rules_count_label', None):
            self.about_rules_count_label.setText(f"<b>Routing rules</b>: {len(self.rules)}")
        for i, rule in enumerate(self.rules):
            # Rule name
            self.rules_table.setItem(i, 0, QTableWidgetItem(rule.get('name', 'Unnamed')))
            
            # Applications
            apps = rule.get('applications', [])
            apps_text = ', '.join(apps[:3])
            if len(apps) > 3:
                apps_text += f' (+{len(apps)-3} more)'
            self.rules_table.setItem(i, 1, QTableWidgetItem(apps_text))
            
            # Target device (show friendly name if known)
            target_id = rule.get('target_device', '')
            target = next((d.get('friendly_name') or d.get('name') for d in self.devices if d.get('id') == target_id), target_id or 'Unknown')
            if len(target) > 40:
                target = target[:37] + '...'
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
    
    def _start_in_app_monitor(self):
        """Start the router in-app (background thread)."""
        if self.monitor_thread and self.monitor_thread.isRunning():
            return
        self.monitor_thread = MonitorThread(self.config_file)
        self.monitor_thread.routing_notification.connect(self._on_routing_notification)
        self.monitor_thread.start()
        self.update_service_status()

    def _on_routing_notification(self, title: str, message: str):
        """Show a tray balloon when the router moves a stream."""
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)

    def _stop_in_app_monitor(self):
        """Stop the in-app router thread."""
        if not self.monitor_thread:
            return
        self.monitor_thread.stop()
        self.monitor_thread.wait(10000)
        self.monitor_thread = None
        self.update_service_status()

    def start_service(self):
        """Start the router (in-app)."""
        self._start_in_app_monitor()
        self.statusBar().showMessage("Router started", 2000)

    def stop_service(self):
        """Stop the router."""
        self._stop_in_app_monitor()
        self.statusBar().showMessage("Router stopped", 2000)

    def restart_service(self):
        """Restart the router."""
        self._stop_in_app_monitor()
        self._start_in_app_monitor()
        self.statusBar().showMessage("Router restarted", 2000)
    
    def refresh_logs(self):
        """Refresh log view (in-app buffer)."""
        self.logs_text.setPlainText("\n".join(_log_buffer) if _log_buffer else "No log entries yet.")
        cursor = self.logs_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.logs_text.setTextCursor(cursor)
    
    def closeEvent(self, event):
        """Close or hide to tray depending on preference."""
        if self.close_to_tray and self.tray_icon and self.tray_icon.isVisible():
            self.hide()
            self._show_tray_attention("Running in the system tray. Click the icon to open.")
            event.accept()
            return
        self._cleanup()
        event.accept()
        # Actually quit when user closed the window (not hiding to tray)
        QApplication.instance().quit()


def main():
    """Main entry point"""
    logger.info("Starting Audio Router GUI")
    
    app = QApplication(sys.argv)
    app.setApplicationName("SinkSwitch")
    # Don't quit when window is closed; we hide to tray or quit explicitly
    app.setQuitOnLastWindowClosed(False)
    
    if not _acquire_single_instance_lock():
        QMessageBox.warning(
            None,
            "SinkSwitch",
            "Another instance of SinkSwitch is already running.\nUse the system tray icon or application menu to open it.",
        )
        sys.exit(1)
    
    window = AudioRouterGUI()
    if '--minimized' in sys.argv:
        if window.tray_icon and window.tray_icon.isVisible():
            window.hide()
            window._show_tray_attention("Running in the system tray. Click the icon to open.")
        else:
            window.showMinimized()
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
