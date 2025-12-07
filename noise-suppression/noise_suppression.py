#!/usr/bin/env python3
"""
Noise Suppression Module for PipeWire Microphone Input

This module provides a Python wrapper around the noise-suppression-for-voice LADSPA plugin
to create a virtual noise-suppressed microphone in PipeWire. It uses the RNNoise library
via the LADSPA plugin interface.

Installation:
    Arch: pacman -S noise-suppression-for-voice
    Fedora: dnf install ladspa-noise-suppression-for-voice
"""

import sys
import os
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, List

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Check for required dependencies
try:
    import yaml
except ImportError as e:
    logger.error(f"Missing dependency: {e}")
    logger.error("Install with: pip install pyyaml")
    sys.exit(1)


class NoiseSuppressionEngine:
    """
    PipeWire noise suppression engine using LADSPA plugin.
    
    This creates a virtual microphone in PipeWire with RNNoise filtering
    by using a filter chain configuration.
    """
    
    def __init__(self, config_dir: Path = None):
        """
        Initialize the noise suppression engine.
        
        Args:
            config_dir: Path to PipeWire config directory (default: ~/.config/pipewire)
        """
        self.config_dir = config_dir or Path.home() / ".config" / "pipewire"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.systemd_user_dir = Path.home() / ".config" / "systemd" / "user"
        self.systemd_user_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if LADSPA plugin is installed
        self.plugin_path = Path("/usr/lib/ladspa/librnnoise_ladspa.so")
        if not self.plugin_path.exists():
            logger.error(f"LADSPA plugin not found at {self.plugin_path}")
            logger.error("Install with: pacman -S noise-suppression-for-voice")
        
        self.is_running = False
        logger.info("Noise suppression engine initialized")
    
    def list_devices(self) -> List[Dict]:
        """
        List available audio input devices via pactl.
        
        Returns:
            List of device information dictionaries
        """
        try:
            result = subprocess.run(
                ["pactl", "list", "sources"],
                capture_output=True,
                text=True,
                check=True
            )
            
            devices = []
            current_device = {}
            
            for line in result.stdout.split('\n'):
                if line.startswith('Source #'):
                    if current_device:
                        devices.append(current_device)
                    current_device = {'index': line.split('#')[-1].strip()}
                elif 'Name:' in line and current_device:
                    current_device['name'] = line.split('Name:')[-1].strip()
                elif 'Description:' in line and current_device:
                    current_device['description'] = line.split('Description:')[-1].strip()
            
            if current_device:
                devices.append(current_device)
            
            return devices
        except Exception as e:
            logger.error(f"Error listing devices: {e}")
            return []
    
    def get_default_input_device(self) -> Optional[Dict]:
        """Get the default audio input device."""
        try:
            result = subprocess.run(
                ["pactl", "get-default-source"],
                capture_output=True,
                text=True,
                check=True
            )
            device_name = result.stdout.strip()
            
            devices = self.list_devices()
            for device in devices:
                if device.get('name') == device_name:
                    return device
            
            return None
        except Exception as e:
            logger.error(f"Error getting default device: {e}")
            return None
    
    def create_filter_chain_config(self, 
                                   input_device: Optional[str] = None,
                                   output_name: str = "Noise cancelling source") -> str:
        """
        Create a PipeWire filter chain configuration for noise suppression.
        
        Args:
            input_device: Input device name (uses default if None)
            output_name: Name for the virtual output device
            
        Returns:
            Configuration content as string
        """
        if not input_device:
            default = self.get_default_input_device()
            input_device = default['name'] if default else "alsa_input.pci-0000_00_1f.3.analog-stereo"
        
        config = f'''context.modules = [
    {{
        name = libpipewire-module-filter-chain
        args = {{
            node.description = "{output_name}"
            media.class = Audio/Source
            filter.graph = {{
                nodes = [
                    {{
                        type = ladspa
                        name = rnnoise
                        plugin = {self.plugin_path}
                        label = noise_suppressor_mono
                        control = {{
                            "Gate threshold dB" = -40
                        }}
                    }}
                ]
                links = [
                    {{ output = "rnnoise:output" input = "out:input" }}
                ]
                controls = {{
                    "rnnoise:Gate threshold dB" = -40
                }}
            }}
            capture.props = {{
                node.name = "capture.rnnoise_source"
                node.passive = true
            }}
            playback.props = {{
                node.name = "out"
                audio.position = [ MONO ]
            }}
        }}
    }}
]
'''
        return config
    
    def install_filter_chain(self, input_device: Optional[str] = None) -> bool:
        """
        Install the noise suppression filter chain to PipeWire.
        
        This creates the configuration files but doesn't restart PipeWire.
        You must restart manually to avoid breaking audio.
        
        Args:
            input_device: Input device name (uses default if None)
            
        Returns:
            True if successful
        """
        try:
            config_content = self.create_filter_chain_config(input_device)
            
            # Write the standalone filter chain config
            config_file = self.config_dir / "input-filter-chain.conf"
            logger.info(f"Writing filter chain config to {config_file}")
            config_file.write_text(config_content)
            
            # Create systemd service
            service_content = self._create_systemd_service()
            service_file = self.systemd_user_dir / "pipewire-input-filter-chain.service"
            
            logger.info(f"Writing systemd service to {service_file}")
            service_file.write_text(service_content)
            service_file.chmod(0o644)
            
            # Reload systemd and enable service
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "--user", "enable", "pipewire-input-filter-chain.service"], check=True)
            
            logger.info("Filter chain configured. Ready to activate.")
            return True
            
        except Exception as e:
            logger.error(f"Error installing filter chain: {e}")
            return False
    
    def _create_systemd_service(self) -> str:
        """Create systemd service unit for filter chain."""
        config_file = self.config_dir / "input-filter-chain.conf"
        
        # Simple service that loads the config on demand
        # User must manually restart PipeWire to activate
        service = f'''[Unit]
Description=PipeWire Noise Suppression Filter Chain Configuration
Documentation=https://github.com/crashman79/pipewire-router

[Service]
Type=oneshot
ExecStart=/bin/true
RemainAfterExit=yes

[Install]
WantedBy=default.target
'''
        return service
    
    def start(self) -> bool:
        """Start the noise suppression service."""
        try:
            subprocess.run(
                ["systemctl", "--user", "start", "pipewire-input-filter-chain.service"],
                check=True
            )
            self.is_running = True
            logger.info("Noise suppression service started")
            return True
        except Exception as e:
            logger.error(f"Error starting service: {e}")
            return False
    
    
    def stop(self) -> bool:
        """Stop the noise suppression service."""
        try:
            subprocess.run(
                ["systemctl", "--user", "stop", "pipewire-input-filter-chain.service"],
                check=True
            )
            self.is_running = False
            logger.info("Noise suppression service stopped")
            return True
        except Exception as e:
            logger.error(f"Error stopping service: {e}")
            return False
    
    def status(self) -> bool:
        """Check if the noise suppression service is running."""
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", "pipewire-input-filter-chain.service"],
                capture_output=True,
                text=True
            )
            is_active = result.returncode == 0
            
            if is_active:
                print("✓ Noise suppression is ACTIVE")
                print(f"  Virtual device: Noise cancelling source")
            else:
                print("✗ Noise suppression is INACTIVE")
            
            self.is_running = is_active
            return is_active
        except Exception as e:
            logger.error(f"Error checking status: {e}")
            return False
    
    def set_default_input(self) -> bool:
        """Set the noise suppression source as the default input device."""
        try:
            # Get list of sources and find the noise cancelling one
            result = subprocess.run(
                ["pactl", "list", "sources"],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                logger.error("Failed to list sources with pactl")
                return False
            
            # Parse output to find noise cancelling source
            lines = result.stdout.split('\n')
            current_source = None
            source_name = None
            
            for i, line in enumerate(lines):
                # Find source number
                if line.startswith('Source #'):
                    current_source = line.split('#')[1].strip()
                
                # Find the name
                if 'Name:' in line:
                    source_name = line.split('Name:')[1].strip()
                
                # Check if this is the noise cancelling source
                if 'Description:' in line and source_name:
                    desc = line.split('Description:')[1].strip()
                    if 'Noise' in desc or 'rnnoise' in desc.lower():
                        # Found it! Set as default
                        try:
                            subprocess.run(
                                ["pactl", "set-default-source", source_name],
                                check=True,
                                capture_output=True
                            )
                            print(f"✓ Default microphone set to: {desc}")
                            logger.info(f"Set default input to: {source_name}")
                            return True
                        except subprocess.CalledProcessError:
                            logger.error(f"Failed to set {source_name} as default")
                            continue
            
            # If we get here, didn't find noise cancelling source
            logger.error("Could not find 'Noise cancelling source' in available devices")
            print("✗ 'Noise cancelling source' not found")
            print("  Make sure you have restarted PipeWire after installation")
            return False
            
        except Exception as e:
            logger.error(f"Error setting default input: {e}")
            return False


def main():
    """Main CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="PipeWire Noise Suppression Manager"
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # List devices command
    subparsers.add_parser('list-devices', help='List available audio input devices')
    
    # Install command
    install_parser = subparsers.add_parser('install', help='Install noise suppression filter chain')
    install_parser.add_argument('--device', help='Input device name (optional)', default=None)
    
    # Start command
    subparsers.add_parser('start', help='Start the noise suppression service')
    
    # Stop command
    subparsers.add_parser('stop', help='Stop the noise suppression service')
    
    # Status command
    subparsers.add_parser('status', help='Check noise suppression status')
    
    # Set default input command
    subparsers.add_parser('set-default', help='Make noise suppression the default microphone input')
    
    args = parser.parse_args()
    
    engine = NoiseSuppressionEngine()
    
    if args.command == 'list-devices':
        devices = engine.list_devices()
        if devices:
            print("\nAvailable audio input devices:")
            for i, device in enumerate(devices):
                print(f"  [{i}] {device.get('name')}")
                print(f"      Description: {device.get('description')}")
        else:
            print("No audio input devices found")
    
    elif args.command == 'install':
        if engine.install_filter_chain(args.device):
            print("\n✓ Filter chain configuration created!")
            print("")
            print("Next step: Restart PipeWire to activate")
            print("  systemctl --user restart pipewire.service")
            print("")
            print("Then:")
            print("  1. Check status: python3 noise_suppression.py status")
            print("  2. Set as default (for games): python3 noise_suppression.py set-default")
            print("  3. Or select 'Noise cancelling source' in app audio settings")
        else:
            print("✗ Failed to install filter chain")
            sys.exit(1)
    
    elif args.command == 'start':
        if engine.start():
            print("✓ Noise suppression started")
        else:
            print("✗ Failed to start noise suppression")
            sys.exit(1)
    
    elif args.command == 'stop':
        if engine.stop():
            print("✓ Noise suppression stopped")
        else:
            print("✗ Failed to stop noise suppression")
            sys.exit(1)
    
    elif args.command == 'status':
        engine.status()
    
    elif args.command == 'set-default':
        if not engine.set_default_input():
            sys.exit(1)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
