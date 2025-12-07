#!/usr/bin/env python3
"""
Device monitoring module for detecting and tracking audio output devices
"""

import logging
import subprocess
import json
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)


@dataclass
class AudioDevice:
    """Represents an audio output device"""
    id: str
    name: str
    device_type: str
    connected: bool
    description: Optional[str] = None
    properties: Dict = None


class DeviceMonitor:
    """Monitor and detect audio output devices"""
    
    def __init__(self):
        self.devices = {}
        self.last_devices = {}
        self._detect_audio_backend()
    
    def _detect_audio_backend(self):
        """Detect which audio backend is available (PipeWire or PulseAudio)"""
        try:
            subprocess.run(['pw-cli', 'info'], 
                          capture_output=True, 
                          check=False,
                          timeout=2)
            self.backend = 'pipewire'
            logger.info("Detected PipeWire audio backend")
        except FileNotFoundError:
            self.backend = 'pulseaudio'
            logger.info("Detected PulseAudio audio backend")
    
    def get_devices(self) -> List[Dict]:
        """Get list of available audio output devices"""
        if self.backend == 'pipewire':
            return self._get_pipewire_devices()
        else:
            return self._get_pulseaudio_devices()
    
    def _get_pipewire_devices(self) -> List[Dict]:
        """Get devices using PipeWire"""
        try:
            # Use pactl as fallback since pw-cli output varies
            result = subprocess.run(
                ['pactl', 'list', 'sinks'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            devices = []
            current_device = {}
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                
                if line.startswith('Sink #'):
                    if current_device:
                        devices.append(current_device)
                    current_device = {
                        'device_type': 'Sink',
                        'properties': {},
                        'connected': True
                    }
                elif ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().lower()
                    value = value.strip()
                    
                    if key == 'name':
                        current_device['id'] = value
                        current_device['name'] = value
                    elif key == 'description':
                        current_device['description'] = value
                    elif key == 'state':
                        # SUSPENDED is normal (no audio playing), only treat IDLE/UNAVAILABLE as disconnected
                        state = value.lower()
                        current_device['connected'] = state not in ['idle', 'unavailable']
                    else:
                        current_device['properties'][key] = value
            
            if current_device:
                devices.append(current_device)
            
            return devices
        except Exception as e:
            logger.error(f"Failed to get PipeWire devices: {e}")
            return []
    
    def _get_pulseaudio_devices(self) -> List[Dict]:
        """Get devices using PulseAudio"""
        try:
            result = subprocess.run(
                ['pactl', 'list', 'sinks'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            devices = []
            current_device = {}
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                
                if line.startswith('Sink #'):
                    if current_device:
                        devices.append(current_device)
                    current_device = {
                        'device_type': 'Sink',
                        'properties': {},
                        'connected': True  # Default to connected
                    }
                elif ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().lower()
                    value = value.strip()
                    
                    if key == 'name':
                        current_device['id'] = value
                        current_device['name'] = value
                    elif key == 'description':
                        current_device['description'] = value
                    elif key == 'state':
                        # Only mark as disconnected if truly unavailable
                        state = value.lower()
                        current_device['connected'] = state != 'unavailable'
                    else:
                        current_device['properties'][key] = value
            
            if current_device:
                devices.append(current_device)
            
            return devices
        except Exception as e:
            logger.error(f"Failed to get PulseAudio devices: {e}")
            return []
    
    def _parse_pw_device(self, line: str) -> Optional[Dict]:
        """Parse a PipeWire device line"""
        try:
            # Extract device info from pw-cli output
            # Format varies, basic parsing for common cases
            parts = line.split()
            if len(parts) >= 3:
                return {
                    'id': parts[0],
                    'name': ' '.join(parts[2:]),
                    'device_type': 'Sink',
                    'connected': True,
                    'properties': {}
                }
        except Exception as e:
            logger.debug(f"Failed to parse PipeWire device: {e}")
        
        return None
    
    def get_device_by_name(self, name: str) -> Optional[Dict]:
        """Get a device by name"""
        devices = self.get_devices()
        for device in devices:
            if device['name'] == name or device['id'] == name:
                return device
        return None
    
    def device_connected(self, device_id: str) -> bool:
        """Check if a device is currently connected"""
        device = self.get_device_by_name(device_id)
        return device is not None and device.get('connected', False)
    
    def watch_devices(self, callback: Callable, interval: int = 5):
        """Watch for device changes and call callback when changes detected
        
        Args:
            callback: Function to call when devices change
            interval: Polling interval in seconds
        """
        logger.info(f"Starting device monitoring (interval: {interval}s)")
        
        try:
            while True:
                current_devices = self.get_devices()
                
                # Check if device list changed
                if self._devices_changed(current_devices):
                    logger.info("Device configuration changed")
                    callback()
                    self.last_devices = current_devices
                
                time.sleep(interval)
        
        except KeyboardInterrupt:
            logger.info("Device monitoring stopped")
        except Exception as e:
            logger.error(f"Error during device monitoring: {e}")
    
    def _devices_changed(self, current_devices: List[Dict]) -> bool:
        """Check if device list has changed"""
        if not self.last_devices and current_devices:
            self.last_devices = current_devices
            return True
        
        if len(current_devices) != len(self.last_devices):
            return True
        
        current_ids = {d['id'] for d in current_devices}
        last_ids = {d['id'] for d in self.last_devices}
        
        if current_ids != last_ids:
            return True
        
        # Check connection state changes
        for device in current_devices:
            last_device = next(
                (d for d in self.last_devices if d['id'] == device['id']),
                None
            )
            if last_device and device.get('connected') != last_device.get('connected'):
                return True
        
        return False
