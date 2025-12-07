#!/usr/bin/env python3
"""
Audio routing engine - applies routing rules to audio streams
"""

import subprocess
import logging
from typing import Dict, List, Optional
from device_monitor import DeviceMonitor

logger = logging.getLogger(__name__)


class AudioRouterEngine:
    """Engine for applying audio routing rules"""
    
    def __init__(self):
        self.device_monitor = DeviceMonitor()
    
    def apply_rules(self, rules: List[Dict]) -> List[Dict]:
        """Apply routing rules to audio streams
        
        Args:
            rules: List of routing rules
            
        Returns:
            List of result dictionaries with success status and messages
        """
        results = []
        
        for rule in rules:
            result = self._apply_rule(rule)
            results.append(result)
        
        return results
    
    def _apply_rule(self, rule: Dict) -> Dict:
        """Apply a single routing rule
        
        Args:
            rule: Single routing rule dictionary
            
        Returns:
            Result dictionary with success status and message
        """
        rule_name = rule.get('name', 'Unknown')
        target_device = rule.get('target_device')
        
        try:
            # Check if target device is connected
            if not self.device_monitor.device_connected(target_device):
                return {
                    'rule_name': rule_name,
                    'success': False,
                    'message': f"Target device not connected: {target_device}"
                }
            
            # Get applications to match
            applications = rule.get('applications', [])
            keywords = rule.get('application_keywords', [])
            
            # Route matching applications to target device
            routed = self._route_applications(
                applications,
                keywords,
                target_device
            )
            
            return {
                'rule_name': rule_name,
                'success': True,
                'message': f"Successfully routed {routed} stream(s) to {target_device}"
            }
        
        except Exception as e:
            logger.error(f"Error applying rule '{rule_name}': {e}")
            return {
                'rule_name': rule_name,
                'success': False,
                'message': f"Error: {str(e)}"
            }
    
    def _route_applications(self,
                           applications: List[str],
                           keywords: List[str],
                           target_device: str) -> int:
        """Route matching applications to target device
        
        Args:
            applications: List of application names to match
            keywords: List of keywords to search in window titles
            target_device: Target device name
            
        Returns:
            Number of streams routed
        """
        routed_count = 0
        
        try:
            # Get list of running applications
            running_apps = self._get_running_applications()
            
            # Find matching applications
            for app_name in running_apps:
                if self._matches_rule(app_name, applications, keywords):
                    logger.debug(f"App '{app_name}' matches rule, routing to {target_device}")
                    if self._route_stream(app_name, target_device):
                        routed_count += 1
                else:
                    logger.debug(f"App '{app_name}' does NOT match rule")
            
            return routed_count
        
        except Exception as e:
            logger.debug(f"Error routing applications: {e}")
            return routed_count
    
    def _matches_rule(self,
                     app_name: str,
                     applications: List[str],
                     keywords: List[str]) -> bool:
        """Check if application matches rule criteria
        
        Args:
            app_name: Application name to check
            applications: List of exact application names to match
            keywords: List of keywords to match in app name
            
        Returns:
            True if application matches rule
        """
        app_lower = app_name.lower()
        
        # Check exact matches
        for app in applications:
            if app.lower() in app_lower or app_lower in app.lower():
                return True
        
        # Check keyword matches
        for keyword in keywords:
            if keyword.lower() in app_lower:
                return True
        
        return False
    
    def _get_running_applications(self) -> List[str]:
        """Get list of currently running applications
        
        Returns:
            List of application names
        """
        try:
            if self.device_monitor.backend == 'pipewire':
                return self._get_pw_applications()
            else:
                return self._get_pa_applications()
        except Exception as e:
            logger.debug(f"Error getting running applications: {e}")
            return []
    
    def _get_pw_applications(self) -> List[str]:
        """Get running applications from PipeWire
        
        Note: Even though we're on PipeWire, we use pactl for compatibility
        since PipeWire runs a PulseAudio compatibility layer
        """
        try:
            result = subprocess.run(
                ['pactl', 'list', 'sink-inputs'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            apps = []
            for line in result.stdout.split('\n'):
                if 'application.name' in line:
                    # Extract application name from line like:
                    # application.name = "World of Warcraft"
                    parts = line.split('=')
                    if len(parts) > 1:
                        app_name = parts[1].strip().strip('"')
                        apps.append(app_name)
            
            return list(set(apps))  # Remove duplicates
        except Exception as e:
            logger.debug(f"Failed to get PipeWire applications: {e}")
            return []
    
    def _get_pa_applications(self) -> List[str]:
        """Get running applications from PulseAudio"""
        try:
            result = subprocess.run(
                ['pactl', 'list', 'sink-inputs'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            apps = []
            for line in result.stdout.split('\n'):
                if 'application.name' in line:
                    # Extract application name
                    parts = line.split('=')
                    if len(parts) > 1:
                        app_name = parts[1].strip().strip('"')
                        apps.append(app_name)
            
            return list(set(apps))  # Remove duplicates
        except Exception as e:
            logger.debug(f"Failed to get PulseAudio applications: {e}")
            return []
    
    def _route_stream(self, app_name: str, target_device: str) -> bool:
        """Route an application's audio stream to target device
        
        Args:
            app_name: Application name
            target_device: Target device name
            
        Returns:
            True if routing was successful
        """
        try:
            # Always use PulseAudio routing since PipeWire runs a PA compatibility layer
            # and pactl move-sink-input is the most reliable way to route streams
            return self._route_pa_stream(app_name, target_device)
        except Exception as e:
            logger.debug(f"Failed to route stream for {app_name}: {e}")
            return False
    
    def _route_pw_stream(self, app_name: str, target_device: str) -> bool:
        """Route stream in PipeWire"""
        try:
            # Using PipeWire's link creation
            # This is a simplified example - real implementation would need
            # to properly identify node IDs and create links
            subprocess.run(
                ['pw-cli', 'set', app_name, 'target.object', target_device],
                capture_output=True,
                timeout=5,
                check=False
            )
            return True
        except Exception as e:
            logger.debug(f"PipeWire routing failed: {e}")
            return False
    
    def _get_sink_number(self, device_name: str) -> Optional[str]:
        """Convert device name to sink number
        
        Args:
            device_name: Device name (e.g., alsa_output.pci-0000_0e_00.4.analog-stereo)
            
        Returns:
            Sink number (e.g., "54") or None if not found
        """
        try:
            result = subprocess.run(
                ['pactl', 'list', 'sinks'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            current_sink_id = None
            for line in result.stdout.split('\n'):
                if 'Sink #' in line:
                    current_sink_id = line.split('#')[1].strip()
                elif 'Name:' in line:
                    # Extract the name value
                    name_value = line.split('Name:')[1].strip()
                    if device_name in line or name_value == device_name:
                        return current_sink_id
            return None
        except Exception as e:
            logger.debug(f"Failed to get sink number for {device_name}: {e}")
            return None
    
    def _route_pa_stream(self, app_name: str, target_device: str) -> bool:
        """Route stream in PulseAudio"""
        try:
            # Get sink number for target device
            target_sink = self._get_sink_number(target_device)
            if not target_sink:
                logger.debug(f"Could not find sink number for device {target_device}")
                return False
            
            logger.debug(f"Looking for app '{app_name}', target sink: {target_sink}")
            
            # Get sink input index for the application
            result = subprocess.run(
                ['pactl', 'list', 'sink-inputs'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            sink_input_id = None
            current_sink_input = None
            
            for line in result.stdout.split('\n'):
                if 'Sink Input #' in line:
                    current_sink_input = line.split('#')[1].strip()
                elif 'application.name' in line:
                    if app_name in line:
                        # Found matching application
                        sink_input_id = current_sink_input
                        break
            
            if sink_input_id:
                # Move sink input to target sink (by number, not device name)
                result = subprocess.run(
                    ['pactl', 'move-sink-input', sink_input_id, target_sink],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False
                )
                if result.returncode == 0:
                    logger.debug(f"Moved sink input {sink_input_id} ({app_name}) to sink #{target_sink}")
                    return True
                else:
                    logger.debug(f"Failed to move sink input {sink_input_id}: {result.stderr}")
                    return False
            
            logger.debug(f"Could not find sink input for {app_name}")
            return False
        except Exception as e:
            logger.debug(f"PulseAudio routing failed: {e}")
            return False
