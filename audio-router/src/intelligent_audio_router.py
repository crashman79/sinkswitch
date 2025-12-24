#!/usr/bin/env python3
"""
Intelligent audio routing engine that automatically detects device types
and routes audio based on device capabilities and priorities
"""

import subprocess
import logging
from typing import Dict, List, Optional
from device_monitor import DeviceMonitor

logger = logging.getLogger(__name__)


class DeviceClassifier:
    """Classify audio devices by type (speaker, headset, earbuds, etc.)"""
    
    @staticmethod
    def classify_device(device: Dict) -> str:
        """Classify a device based on its name and description
        
        Args:
            device: Device dictionary with 'id', 'name', 'description'
            
        Returns:
            Device type: 'bluetooth', 'usb_headset', 'usb_speakers', 'analog_speakers', 'hdmi', 'unknown'
        """
        full_text = f"{device.get('id', '')} {device.get('name', '')} {device.get('description', '')}".lower()
        
        # Bluetooth devices
        if 'bluez' in full_text or 'bluetooth' in full_text:
            return 'bluetooth'
        
        # USB devices
        if 'usb' in full_text:
            if 'headset' in full_text or 'headphones' in full_text or 'gaming' in full_text:
                return 'usb_headset'
            elif 'speaker' in full_text:
                return 'usb_speakers'
            else:
                return 'usb_headset'  # Default USB audio to headset category
        
        # HDMI/DisplayPort
        if 'hdmi' in full_text or 'displayport' in full_text:
            return 'hdmi'
        
        # Analog speakers
        if 'analog' in full_text or 'line out' in full_text or 'audio controller' in full_text:
            return 'analog_speakers'
        
        return 'unknown'


class IntelligentAudioRouter:
    """Route audio intelligently based on device types and app categories"""
    
    # Application categories
    APP_CATEGORIES = {
        'browsers': ['firefox', 'chrome', 'chromium', 'opera', 'edge', 'brave', 'vivaldi'],
        'meetings': ['zoom', 'teams', 'meet', 'discord', 'skype', 'slack'],
        'music': ['spotify', 'vlc', 'rhythmbox', 'cmus', 'mpv', 'audacious'],
        'games': ['steam', 'lutris', 'wine', 'proton', 'wow', 'world of warcraft'],
    }
    
    # Device type priority for different app categories
    ROUTING_PRIORITIES = {
        'browsers': ['bluetooth_earbuds', 'usb_headset', 'default'],
        'meetings': ['bluetooth_earbuds', 'usb_headset', 'default'],
        'music': ['bluetooth_earbuds', 'usb_headset', 'default'],
        'games': ['default'],  # Use whatever is default
    }
    
    def __init__(self):
        self.device_monitor = DeviceMonitor()
        self.classifier = DeviceClassifier()
    
    def get_device_map(self) -> Dict[str, List[Dict]]:
        """Get all devices organized by type
        
        Returns:
            Dictionary mapping device types to lists of devices
        """
        devices = self.device_monitor.get_devices()
        device_map = {}
        
        for device in devices:
            if not device.get('connected'):
                continue
            
            dev_type = self.classifier.classify_device(device)
            if dev_type not in device_map:
                device_map[dev_type] = []
            device_map[dev_type].append(device)
        
        return device_map
    
    def get_app_category(self, app_name: str) -> Optional[str]:
        """Determine which category an app falls into
        
        Args:
            app_name: Application name
            
        Returns:
            Category name or None if no match
        """
        app_lower = app_name.lower()
        
        for category, app_list in self.APP_CATEGORIES.items():
            for app in app_list:
                if app.lower() in app_lower or app_lower in app.lower():
                    return category
        
        return None
    
    def get_routing_target(self, app_category: str, device_map: Dict) -> Optional[str]:
        """Determine the best routing target for an app category
        
        Args:
            app_category: Application category
            device_map: Dictionary of available devices by type
            
        Returns:
            Device ID to route to, or None to use default
        """
        if app_category not in self.ROUTING_PRIORITIES:
            return None  # Use default
        
        priorities = self.ROUTING_PRIORITIES[app_category]
        
        for priority in priorities:
            if priority == 'default':
                return None  # Use default sink
            elif priority == 'bluetooth_earbuds':
                # Look for Bluetooth devices that aren't speakers
                if 'bluetooth' in device_map:
                    return device_map['bluetooth'][0]['id']
            elif priority == 'usb_headset':
                if 'usb_headset' in device_map:
                    return device_map['usb_headset'][0]['id']
            elif priority == 'usb_speakers':
                if 'usb_speakers' in device_map:
                    return device_map['usb_speakers'][0]['id']
            elif priority == 'analog_speakers':
                if 'analog_speakers' in device_map:
                    return device_map['analog_speakers'][0]['id']
        
        return None
    
    def generate_routing_config(self) -> Dict:
        """Generate routing configuration based on connected devices
        
        Returns:
            Dictionary suitable for YAML serialization
        """
        device_map = self.get_device_map()
        config = {'routing_rules': []}
        
        logger.info(f"Detected devices: {device_map}")
        
        # Generate rules for each category that has a routing target
        for category, priorities in self.ROUTING_PRIORITIES.items():
            for priority in priorities:
                if priority == 'default':
                    continue
                
                priority_map = {
                    'bluetooth_earbuds': 'bluetooth',
                    'usb_headset': 'usb_headset',
                    'usb_speakers': 'usb_speakers',
                    'analog_speakers': 'analog_speakers',
                }
                
                device_type = priority_map.get(priority)
                if device_type and device_type in device_map:
                    device = device_map[device_type][0]
                    
                    # For Bluetooth devices, get all profile sinks and prefer A2DP
                    target_device = device['id']
                    all_sinks = [target_device]
                    
                    if device_type == 'bluetooth':
                        # Extract MAC address from device ID
                        # Format: bluez_output.00_02_3C_AD_09_85.1
                        if 'bluez' in target_device:
                            parts = target_device.split('.')
                            if len(parts) >= 3:
                                device_address = parts[1]  # 00_02_3C_AD_09_85
                                device_address_colon = device_address.replace('_', ':')  # 00:02:3C:AD:09:85
                                
                                # Get all sinks for this Bluetooth device
                                all_sinks = self.device_monitor.get_all_bluetooth_sinks(device_address)
                                if not all_sinks:
                                    all_sinks = [target_device]
                                
                                # Force A2DP profile for high-fidelity audio
                                self.device_monitor.prefer_a2dp_profile(device_address_colon)
                                logger.info(f"Bluetooth device has {len(all_sinks)} sink(s): {all_sinks}")
                    
                    # Create rule with all sink variants
                    rule = {
                        'name': f"{category.title()} Apps to {device_type.replace('_', ' ').title()}",
                        'applications': self.APP_CATEGORIES.get(category, []),
                        'target_device': target_device,
                        'target_device_variants': all_sinks if len(all_sinks) > 1 else None,
                        'enable_default_fallback': True
                    }
                    config['routing_rules'].append(rule)
                    break  # Only add one rule per category
        
        return config
    
    def print_device_info(self):
        """Print information about detected devices"""
        device_map = self.get_device_map()
        
        print("\n" + "="*80)
        print("DETECTED AUDIO DEVICES:")
        print("="*80)
        
        for dev_type, devices in device_map.items():
            print(f"\n{dev_type.upper().replace('_', ' ')}:")
            for device in devices:
                print(f"  - {device.get('description', device['name'])}")
                print(f"    ID: {device['id']}")
        
        print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    router = IntelligentAudioRouter()
    router.print_device_info()
    
    # Optionally generate config
    # import yaml
    # config = router.generate_routing_config()
    # print(yaml.dump(config, default_flow_style=False))
