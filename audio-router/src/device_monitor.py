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
        self.bluetooth_devices_cache = {}  # Cache of Bluetooth device info
        self.bluetooth_profile_state = {}  # Track Bluetooth device profiles
        self.last_config_regeneration = 0  # Timestamp of last config regeneration
        self.config_regeneration_cooldown = 10  # Minimum seconds between regenerations
    
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
    
    def get_bluetooth_card_info(self, device_address: str) -> Optional[Dict]:
        """Get Bluetooth card profile information
        
        Args:
            device_address: Bluetooth MAC address (e.g., 00:02:3C:AD:09:85)
        
        Returns:
            Dictionary with card info including available profiles and active profile
        """
        try:
            result = subprocess.run(
                ['pactl', 'list', 'cards'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            cards = []
            current_card = {}
            in_profiles = False
            
            for line in result.stdout.split('\n'):
                stripped = line.strip()
                
                if line.startswith('Card #'):
                    if current_card:
                        cards.append(current_card)
                    current_card = {'profiles': {}}
                    in_profiles = False
                elif stripped.startswith('Name:'):
                    current_card['name'] = stripped.split(':', 1)[1].strip()
                elif 'api.bluez5.address' in stripped:
                    addr = stripped.split('=', 1)[1].strip().strip('"')
                    current_card['address'] = addr
                elif stripped.startswith('Active Profile:'):
                    current_card['active_profile'] = stripped.split(':', 1)[1].strip()
                elif stripped == 'Profiles:':
                    in_profiles = True
                elif in_profiles:
                    if stripped.startswith('Ports:'):
                        in_profiles = False
                    elif ':' in stripped and not stripped.startswith('Part of'):
                        # Parse profile line: "a2dp-sink-sbc: High Fidelity Playback..."
                        parts = stripped.split(':', 1)
                        if len(parts) == 2:
                            profile_name = parts[0].strip()
                            profile_desc = parts[1].strip()
                            current_card['profiles'][profile_name] = profile_desc
            
            if current_card:
                cards.append(current_card)
            
            # Find matching card by address
            for card in cards:
                if card.get('address') == device_address:
                    return card
            
            return None
        except Exception as e:
            logger.debug(f"Failed to get Bluetooth card info: {e}")
            return None
    
    def get_all_bluetooth_sinks(self, device_address: str) -> List[str]:
        """Get all sink names for a Bluetooth device (all profiles)
        
        Args:
            device_address: Bluetooth MAC address without colons (e.g., 00_02_3C_AD_09_85)
        
        Returns:
            List of sink names (e.g., ['bluez_output.00_02_3C_AD_09_85.1', 'bluez_output.00_02_3C_AD_09_85.2'])
        """
        try:
            result = subprocess.run(
                ['pactl', 'list', 'sinks', 'short'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            sinks = []
            for line in result.stdout.split('\n'):
                if device_address in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        sink_name = parts[1]
                        sinks.append(sink_name)
            
            return sinks
        except Exception as e:
            logger.debug(f"Failed to get Bluetooth sinks: {e}")
            return []
    
    def set_bluetooth_profile(self, card_name: str, profile: str) -> bool:
        """Set Bluetooth card to specific profile
        
        Args:
            card_name: Card name (e.g., 'bluez_card.00_02_3C_AD_09_85')
            profile: Profile name (e.g., 'a2dp-sink', 'headset-head-unit')
        
        Returns:
            True if profile was set successfully
        """
        try:
            result = subprocess.run(
                ['pactl', 'set-card-profile', card_name, profile],
                capture_output=True,
                text=True,
                timeout=5,
                check=True
            )
            logger.info(f"Set card {card_name} to profile {profile}")
            return True
        except Exception as e:
            logger.error(f"Failed to set Bluetooth profile: {e}")
            return False
    
    def prefer_a2dp_profile(self, device_address: str) -> bool:
        """Force Bluetooth device to use A2DP (high-fidelity) profile if available
        
        Args:
            device_address: Bluetooth MAC address with colons (e.g., '00:02:3C:AD:09:85')
        
        Returns:
            True if A2DP profile was set successfully
        """
        card_info = self.get_bluetooth_card_info(device_address)
        if not card_info:
            return False
        
        # Check if already in A2DP profile
        active_profile = card_info.get('active_profile', '')
        if active_profile.startswith('a2dp'):
            logger.debug(f"Already in A2DP profile: {active_profile}")
            return True
        
        # Find best A2DP profile (prefer aptX > AAC > SBC-XQ > SBC)
        a2dp_priority = ['a2dp-sink', 'a2dp-sink-aac', 'a2dp-sink-sbc_xq', 'a2dp-sink-sbc']
        for profile in a2dp_priority:
            if profile in card_info.get('profiles', {}):
                return self.set_bluetooth_profile(card_info['name'], profile)
        
        return False
    
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
        """Get a device by name or by Bluetooth MAC address prefix
        
        For Bluetooth devices, matches by MAC address even if suffix differs.
        E.g., 'bluez_output.00_02_3C_AD_09_85.1' matches 'bluez_output.00_02_3C_AD_09_85.2'
        """
        devices = self.get_devices()
        
        # First try exact match
        for device in devices:
            if device['name'] == name or device['id'] == name:
                return device
        
        # For Bluetooth devices, try fuzzy matching by MAC address
        if 'bluez' in name.lower():
            # Extract MAC address from the requested name
            # Format: bluez_output.00_02_3C_AD_09_85.1 or bluez_card.00_02_3C_AD_09_85
            parts = name.split('.')
            if len(parts) >= 2:
                # Get the MAC address part (second component)
                mac_address = parts[1]
                
                # Find any device with matching MAC address
                for device in devices:
                    device_id = device.get('id', '')
                    if 'bluez' in device_id.lower() and mac_address in device_id:
                        logger.debug(f"Fuzzy matched Bluetooth device '{name}' to '{device_id}'")
                        return device
        
        return None
    
    def device_connected(self, device_id: str) -> bool:
        """Check if a device is currently connected"""
        device = self.get_device_by_name(device_id)
        return device is not None and device.get('connected', False)
    
    def watch_devices(self, callback: Callable, interval: int = 5, config_regen_callback: Optional[Callable] = None):
        """Watch for device changes and call callback when changes detected
        
        Args:
            callback: Function to call when devices change
            interval: Polling interval in seconds
            config_regen_callback: Optional callback to regenerate config when significant devices change
        """
        logger.info(f"Starting device monitoring (interval: {interval}s)")
        if config_regen_callback:
            logger.info("Config auto-regeneration enabled for bluetooth/USB device changes")
        
        try:
            while True:
                current_devices = self.get_devices()
                
                # Monitor Bluetooth profiles and restore A2DP when possible
                self._monitor_bluetooth_profiles(current_devices)
                
                # Check for significant device changes (bluetooth/USB connecting/disconnecting)
                if config_regen_callback and self._is_significant_device_change(current_devices):
                    # Rate limit config regeneration
                    time_since_last = time.time() - self.last_config_regeneration
                    if time_since_last >= self.config_regeneration_cooldown:
                        logger.info(f"Triggering config regeneration due to significant device change")
                        try:
                            config_regen_callback()
                            self.last_config_regeneration = time.time()
                        except Exception as e:
                            logger.error(f"Failed to regenerate config: {e}")
                    else:
                        logger.debug(f"Skipping config regeneration (cooldown: {self.config_regeneration_cooldown - time_since_last:.1f}s remaining)")
                
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
    
    def _is_significant_device_change(self, current_devices: List[Dict]) -> bool:
        """Check if device changes are significant enough to trigger config regeneration
        
        Significant changes are:
        - Bluetooth devices connecting/disconnecting
        - USB headsets connecting/disconnecting
        - Any device with 'bluez' or 'usb' in the ID
        """
        if not self.last_devices:
            return False
        
        current_ids = {d['id'] for d in current_devices}
        last_ids = {d['id'] for d in self.last_devices}
        
        # Check for new or removed devices
        added = current_ids - last_ids
        removed = last_ids - current_ids
        
        # Filter to only significant device types
        def is_significant(device_id: str) -> bool:
            return 'bluez' in device_id.lower() or 'usb' in device_id.lower()
        
        significant_added = any(is_significant(d) for d in added)
        significant_removed = any(is_significant(d) for d in removed)
        
        if significant_added or significant_removed:
            logger.info(f"Significant device change detected - Added: {[d for d in added if is_significant(d)]}, Removed: {[d for d in removed if is_significant(d)]}")
            return True
        
        return False
    
    def _monitor_bluetooth_profiles(self, current_devices: List[Dict]):
        """Monitor Bluetooth device profiles and restore A2DP when HSP/HFP is no longer needed
        
        Args:
            current_devices: List of current audio devices
        """
        try:
            # Get all Bluetooth devices
            for device in current_devices:
                device_id = device.get('id', '')
                if 'bluez' not in device_id:
                    continue
                
                # Extract MAC address
                parts = device_id.split('.')
                if len(parts) < 3:
                    continue
                
                device_address_underscore = parts[1]  # 00_02_3C_AD_09_85
                device_address_colon = device_address_underscore.replace('_', ':')
                
                # Get current profile
                card_info = self.get_bluetooth_card_info(device_address_colon)
                if not card_info:
                    continue
                
                active_profile = card_info.get('active_profile', '')
                card_name = card_info.get('name', '')
                
                # Track profile changes
                if device_address_underscore not in self.bluetooth_profile_state:
                    self.bluetooth_profile_state[device_address_underscore] = {
                        'last_profile': active_profile,
                        'profile_switch_time': time.time()
                    }
                
                last_profile = self.bluetooth_profile_state[device_address_underscore]['last_profile']
                
                # If profile changed from HSP/HFP to something else, no action needed
                # If profile is currently HSP/HFP and has been for a while with no active streams, switch back to A2DP
                if active_profile.startswith('headset'):
                    # Check if there are any active input sources (microphone in use)
                    has_active_mic = self._check_active_mic_streams()
                    
                    # If no mic is in use and we've been in headset mode for > 5 seconds, switch back to A2DP
                    time_in_headset = time.time() - self.bluetooth_profile_state[device_address_underscore].get('profile_switch_time', 0)
                    if not has_active_mic and time_in_headset > 5:
                        logger.info(f"Restoring A2DP profile for {device_address_colon} (no active mic streams)")
                        self.prefer_a2dp_profile(device_address_colon)
                        self.bluetooth_profile_state[device_address_underscore]['profile_switch_time'] = time.time()
                
                # Update state
                if active_profile != last_profile:
                    logger.info(f"Bluetooth profile changed: {last_profile} -> {active_profile} for {device_address_colon}")
                    self.bluetooth_profile_state[device_address_underscore] = {
                        'last_profile': active_profile,
                        'profile_switch_time': time.time()
                    }
        
        except Exception as e:
            logger.debug(f"Error monitoring Bluetooth profiles: {e}")
    
    def _check_active_mic_streams(self) -> bool:
        """Check if there are any active microphone/source streams
        
        Returns:
            True if there are active microphone streams
        """
        try:
            result = subprocess.run(
                ['pactl', 'list', 'source-outputs', 'short'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # If there are any source outputs (mic streams), return True
            return bool(result.stdout.strip())
        
        except Exception as e:
            logger.debug(f"Failed to check mic streams: {e}")
            return False
