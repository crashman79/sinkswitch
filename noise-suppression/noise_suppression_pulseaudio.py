#!/usr/bin/env python3
"""
Noise Suppression for PulseAudio Microphone Input

Removes background noise (TV, fan, traffic, etc.) from microphone.
Uses PulseAudio's noise suppression module.

Works alongside echo cancellation for complete microphone cleanup.
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


class NoiseSuppressionEngine:
    """
    PulseAudio noise suppression engine.
    
    Removes background noise (TV, fan, traffic, etc.) from microphone input.
    Can work with or without echo cancellation.
    """
    
    def __init__(self):
        """Initialize the noise suppression engine."""
        self.is_running = False
        logger.info("Noise suppression engine initialized")
    
    def list_devices(self) -> List[Dict]:
        """List available audio input devices."""
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
    
    def _get_source_for_suppression(self) -> Optional[str]:
        """
        Get the best source to apply noise suppression to.
        
        If echo cancellation is active, use its output (echo_cancel_source).
        Otherwise, use the default source.
        """
        try:
            # Check if echo cancellation is active
            result = subprocess.run(
                ["pactl", "list", "modules"],
                capture_output=True,
                text=True,
                check=True
            )
            
            if 'module-echo-cancel' in result.stdout:
                logger.info("Echo cancellation detected, chaining with noise suppression")
                return "echo_cancel_source"
            
            # Fall back to default source
            result = subprocess.run(
                ["pactl", "get-default-source"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
            
        except Exception as e:
            logger.error(f"Error getting source: {e}")
            return None
    
    def enable_noise_suppression(self, input_device: Optional[str] = None) -> bool:
        """
        Enable noise suppression for the microphone input.
        
        Since module-noise-suppress isn't available, we'll use a companding approach
        or recommend the RNNoise LADSPA plugin method.
        
        Args:
            input_device: Input device name (auto-detects if None)
            
        Returns:
            True if successful
        """
        try:
            if not input_device:
                input_device = self._get_source_for_suppression()
            
            if not input_device:
                logger.error("Could not determine input device")
                return False
            
            logger.info(f"Setting up noise suppression for: {input_device}")
            
            # Try to load noise suppression with different parameters
            # Some PulseAudio builds have it as part of echo-cancel
            result = subprocess.run(
                [
                    "pactl", "load-module", "module-echo-cancel",
                    f"source_name=noise_suppress_source",
                    f"source_master={input_device}",
                    "aec_method=webrtc",
                    "aec_args='denoise=1'",
                    "use_volume_sharing=yes"
                ],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                module_id = result.stdout.strip()
                logger.info(f"Noise suppression module loaded (ID: {module_id})")
                
                # Set as default
                subprocess.run(
                    ["pactl", "set-default-source", "noise_suppress_source"],
                    check=True,
                    capture_output=True
                )
                
                print(f"✓ Noise suppression enabled (using WebRTC denoise)")
                print(f"  Source: {input_device}")
                print(f"  Output: noise_suppress_source")
                print(f"  Background noise (TV, fan, etc.) will be suppressed")
                
                self.is_running = True
                return True
            else:
                logger.error(f"Could not load noise suppression: {result.stderr}")
                print("✗ Noise suppression module not available in this build")
                print("")
                print("Alternative: Use the RNNoise LADSPA method")
                print("  cd ~/pipewire/noise-suppression")
                print("  python3 noise_suppression.py install --device <your_mic>")
                return False
                
        except Exception as e:
            logger.error(f"Error enabling noise suppression: {e}")
            return False
    
    def disable_noise_suppression(self) -> bool:
        """Disable noise suppression and restore original microphone."""
        try:
            # Find and unload the noise suppression module
            result = subprocess.run(
                ["pactl", "list", "modules"],
                capture_output=True,
                text=True,
                check=True
            )
            
            module_id = None
            for line in result.stdout.split('\n'):
                if 'module-noise-suppress' in line:
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
                logger.info(f"Noise suppression module unloaded")
                print("✓ Noise suppression disabled")
                self.is_running = False
                return True
            else:
                logger.warning("Noise suppression module not found")
                print("✗ Noise suppression not currently active")
                return False
                
        except Exception as e:
            logger.error(f"Error disabling noise suppression: {e}")
            return False
    
    def status(self) -> bool:
        """Check if noise suppression is active."""
        try:
            result = subprocess.run(
                ["pactl", "list", "modules"],
                capture_output=True,
                text=True,
                check=True
            )
            
            has_echo_cancel = result.stdout.count('module-echo-cancel') >= 1
            has_double_ec = result.stdout.count('module-echo-cancel') >= 2
            has_noise_suppress = 'noise_suppress_source' in subprocess.run(
                ["pactl", "list", "sources", "short"],
                capture_output=True,
                text=True,
                check=True
            ).stdout
            
            print("\n📊 Audio Processing Status")
            print("==========================")
            
            if has_echo_cancel:
                print("✓ Echo Cancellation: ACTIVE")
                print("  (Removes speaker feedback)")
            else:
                print("✗ Echo Cancellation: OFF")
            
            if has_double_ec or has_noise_suppress:
                print("✓ Noise Suppression: ACTIVE")
                print("  (Removes background noise like TV/fan)")
                self.is_running = True
            else:
                print("✗ Noise Suppression: OFF")
                self.is_running = False
            
            print("")
            return has_noise_suppress or has_double_ec
            
        except Exception as e:
            logger.error(f"Error checking status: {e}")
            return False


def main():
    """Main CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="PulseAudio Noise Suppression Manager"
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # List devices command
    subparsers.add_parser('list-devices', help='List available audio input devices')
    
    # Enable command
    enable_parser = subparsers.add_parser('enable', help='Enable noise suppression')
    enable_parser.add_argument('--device', help='Input device name (optional)', default=None)
    
    # Disable command
    subparsers.add_parser('disable', help='Disable noise suppression')
    
    # Status command
    subparsers.add_parser('status', help='Check noise suppression status')
    
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
    
    elif args.command == 'enable':
        if engine.enable_noise_suppression(args.device):
            print("")
            print("Next step: Restart your game/app")
            print("  It will now use the noise-suppressed microphone")
        else:
            sys.exit(1)
    
    elif args.command == 'disable':
        if not engine.disable_noise_suppression():
            sys.exit(1)
    
    elif args.command == 'status':
        engine.status()
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
