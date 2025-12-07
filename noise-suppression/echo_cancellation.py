#!/usr/bin/env python3
"""
Echo Cancellation for PipeWire/PulseAudio Microphone Input

Prevents speaker output from being picked up by the microphone.
Uses PulseAudio's echo-cancel module for real-time processing.
"""

import sys
import os
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, List

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EchoCancellationEngine:
    """
    PulseAudio echo cancellation engine.
    
    Prevents speaker output (from games, apps, etc.) from feeding back
    into the microphone input.
    """
    
    def __init__(self):
        """Initialize the echo cancellation engine."""
        self.is_running = False
        logger.info("Echo cancellation engine initialized")
    
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
    
    def enable_echo_cancellation(self, input_device: Optional[str] = None) -> bool:
        """
        Enable echo cancellation for the microphone input.
        
        Args:
            input_device: Input device name (uses default if None)
            
        Returns:
            True if successful
        """
        try:
            if not input_device:
                # Get default source
                result = subprocess.run(
                    ["pactl", "get-default-source"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                input_device = result.stdout.strip()
            
            logger.info(f"Enabling echo cancellation for: {input_device}")
            
            # Load the echo-cancel module
            # This creates a filtered source with echo cancellation enabled
            result = subprocess.run(
                [
                    "pactl", "load-module", "module-echo-cancel",
                    f"source_name=echo_cancel_source",
                    f"source_master={input_device}",
                    "aec_method=webrtc",
                    "use_volume_sharing=yes"
                ],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                module_id = result.stdout.strip()
                logger.info(f"Echo cancellation module loaded (ID: {module_id})")
                
                # Set the echo-cancelled source as default
                subprocess.run(
                    ["pactl", "set-default-source", "echo_cancel_source"],
                    check=True,
                    capture_output=True
                )
                
                print(f"✓ Echo cancellation enabled")
                print(f"  Microphone: {input_device}")
                print(f"  Echo-cancelled source: echo_cancel_source")
                print(f"  Games will automatically use the echo-cancelled input")
                
                self.is_running = True
                return True
            else:
                logger.error(f"Failed to load echo-cancel module: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error enabling echo cancellation: {e}")
            return False
    
    def disable_echo_cancellation(self) -> bool:
        """Disable echo cancellation and restore original microphone."""
        try:
            # Find and unload the echo-cancel module
            result = subprocess.run(
                ["pactl", "list", "modules"],
                capture_output=True,
                text=True,
                check=True
            )
            
            module_id = None
            for line in result.stdout.split('\n'):
                if 'module-echo-cancel' in line:
                    # Extract module ID
                    parts = line.split('#')
                    if len(parts) > 1:
                        module_id = parts[1].split()[0]
                        break
            
            if module_id:
                subprocess.run(
                    ["pactl", "unload-module", module_id],
                    check=True,
                    capture_output=True
                )
                logger.info(f"Echo cancellation module unloaded")
                print("✓ Echo cancellation disabled")
                self.is_running = False
                return True
            else:
                logger.warning("Echo cancellation module not found")
                return False
                
        except Exception as e:
            logger.error(f"Error disabling echo cancellation: {e}")
            return False
    
    def status(self) -> bool:
        """Check if echo cancellation is active."""
        try:
            result = subprocess.run(
                ["pactl", "list", "modules"],
                capture_output=True,
                text=True,
                check=True
            )
            
            is_active = 'module-echo-cancel' in result.stdout
            
            if is_active:
                print("✓ Echo cancellation is ACTIVE")
                print("  Source: echo_cancel_source")
                print("  Microphone feedback is being suppressed")
            else:
                print("✗ Echo cancellation is INACTIVE")
            
            self.is_running = is_active
            return is_active
        except Exception as e:
            logger.error(f"Error checking status: {e}")
            return False


def main():
    """Main CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="PulseAudio Echo Cancellation Manager"
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # List devices command
    subparsers.add_parser('list-devices', help='List available audio input devices')
    
    # Enable command
    enable_parser = subparsers.add_parser('enable', help='Enable echo cancellation')
    enable_parser.add_argument('--device', help='Input device name (optional)', default=None)
    
    # Disable command
    subparsers.add_parser('disable', help='Disable echo cancellation')
    
    # Status command
    subparsers.add_parser('status', help='Check echo cancellation status')
    
    args = parser.parse_args()
    
    engine = EchoCancellationEngine()
    
    if args.command == 'list-devices':
        devices = engine.list_devices()
        if devices:
            print("\nAvailable audio input devices:")
            for i, device in enumerate(devices):
                print(f"  [{i}] {device.get('name')}")
                print(f"      Description: {device.get('description')}")
        else:
            print("No audio input devices found")
    
    elif args.command == 'enable':
        if engine.enable_echo_cancellation(args.device):
            print("")
            print("Next steps:")
            print("  1. Restart your game/app")
            print("  2. It will now automatically use the echo-cancelled microphone")
            print("  3. Speaker feedback should be suppressed")
        else:
            print("✗ Failed to enable echo cancellation")
            sys.exit(1)
    
    elif args.command == 'disable':
        if engine.disable_echo_cancellation():
            pass
        else:
            print("✗ Failed to disable echo cancellation")
            sys.exit(1)
    
    elif args.command == 'status':
        engine.status()
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
