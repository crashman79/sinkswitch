#!/usr/bin/env python3
"""
PipeWire/PulseAudio Automatic Audio Stream Switching Tool
Handles routing audio streams based on application class and device availability
"""

import argparse
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional
import os

from config_parser import ConfigParser
from device_monitor import DeviceMonitor
from audio_router_engine import AudioRouterEngine
from intelligent_audio_router import IntelligentAudioRouter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def list_devices():
    """List all available audio output devices"""
    try:
        monitor = DeviceMonitor()
        devices = monitor.get_devices()
        
        if not devices:
            print("No audio output devices found")
            return 0
        
        print("\nAvailable Audio Devices:")
        print("-" * 80)
        for i, device in enumerate(devices, 1):
            print(f"\n{i}. {device['name']}")
            print(f"   Device ID: {device['id']}")
            print(f"   Type: {device['device_type']}")
            print(f"   Connected: {device['connected']}")
            if device.get('description'):
                print(f"   Description: {device['description']}")
        
        print("\n" + "-" * 80)
        return 0
        
    except Exception as e:
        logger.error(f"Failed to list devices: {e}")
        return 1


def apply_rules(config_file: str):
    """Apply routing rules from configuration file once"""
    try:
        parser = ConfigParser(config_file)
        rules = parser.parse()
        
        engine = AudioRouterEngine()
        results = engine.apply_rules(rules)
        
        print("\nRouting Results:")
        print("-" * 80)
        for result in results:
            status = "✓" if result['success'] else "✗"
            print(f"{status} {result['rule_name']}: {result['message']}")
        
        print("-" * 80)
        return 0
        
    except Exception as e:
        logger.error(f"Failed to apply rules: {e}")
        return 1


def generate_config(config_file: str):
    """Automatically generate routing configuration based on connected devices"""
    try:
        import yaml
        
        router = IntelligentAudioRouter()
        router.print_device_info()
        
        config = router.generate_routing_config()
        
        print("\nGenerated Routing Rules:")
        print("=" * 80)
        print(yaml.dump(config, default_flow_style=False, sort_keys=False))
        print("=" * 80)
        
        # Save to file
        Path(config_file).parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        
        print(f"\n✓ Routing rules saved to {config_file}")
        return 0
        
    except Exception as e:
        logger.error(f"Failed to generate config: {e}")
        return 1


def monitor_devices(config_file: str):
    """Monitor devices and continuously apply routing rules"""
    try:
        parser = ConfigParser(config_file)
        rules = parser.parse()
        
        monitor = DeviceMonitor()
        engine = AudioRouterEngine()
        
        print(f"Starting device monitoring with config: {config_file}")
        print("Press Ctrl+C to stop\n")
        
        monitor.watch_devices(lambda: engine.apply_rules(rules))
        
    except KeyboardInterrupt:
        print("\nMonitoring stopped")
        return 0
    except Exception as e:
        logger.error(f"Monitoring error: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="PipeWire/PulseAudio Automatic Audio Stream Switching"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # List devices command
    subparsers.add_parser('list-devices', help='List available audio devices')
    
    # Generate config command
    gen_parser = subparsers.add_parser('generate-config', help='Auto-generate routing rules based on connected devices')
    gen_parser.add_argument('--output', '-o', default='config/routing_rules.yaml', help='Output config file path')
    
    # Apply rules command
    apply_parser = subparsers.add_parser('apply-rules', help='Apply routing rules once')
    apply_parser.add_argument('config', help='Configuration file path')
    
    # Monitor command
    monitor_parser = subparsers.add_parser('monitor', help='Monitor devices and apply rules')
    monitor_parser.add_argument('config', help='Configuration file path')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    if args.command == 'list-devices':
        return list_devices()
    elif args.command == 'generate-config':
        return generate_config(args.output)
    elif args.command == 'apply-rules':
        return apply_rules(args.config)
    elif args.command == 'monitor':
        return monitor_devices(args.config)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
