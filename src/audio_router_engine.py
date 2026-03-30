#!/usr/bin/env python3
"""
Audio routing engine - applies routing rules to audio streams
"""

import subprocess
import logging
from typing import Dict, List, Optional, Tuple
from device_monitor import DeviceMonitor
from host_command import host_cmd

logger = logging.getLogger(__name__)


class AudioRouterEngine:
    """Engine for applying audio routing rules"""
    
    def __init__(self):
        self.device_monitor = DeviceMonitor()
    
    def _ensure_a2dp_profile(self, sink_name: str) -> bool:
        """Ensure Bluetooth device is using A2DP (high-fidelity) profile
        
        Args:
            sink_name: Bluetooth sink name (e.g., 'bluez_output.00_02_3C_AD_09_85.1')
        
        Returns:
            True if A2DP profile is active or was successfully set
        """
        try:
            # Extract MAC address from sink name
            # Format: bluez_output.00_02_3C_AD_09_85.1
            if 'bluez' not in sink_name:
                return True  # Not a Bluetooth device
            
            parts = sink_name.split('.')
            if len(parts) < 3:
                return False
            
            device_address = parts[1].replace('_', ':')  # Convert to colon format
            
            # Attempt to set A2DP profile
            return self.device_monitor.prefer_a2dp_profile(device_address)
        
        except Exception as e:
            logger.debug(f"Failed to ensure A2DP profile: {e}")
            return False
    
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
        target_variants = rule.get('target_device_variants', [])
        
        # Build list of all target devices to try
        all_targets = [target_device]
        if target_variants:
            all_targets = target_variants
        
        try:
            # Check if any target device variant is connected
            device_connected = False
            connected_target = None
            
            for target in all_targets:
                if self.device_monitor.device_connected(target):
                    device_connected = True
                    connected_target = target
                    break
            
            if not device_connected:
                target_label = target_device
                for d in self.device_monitor.get_devices():
                    if d.get('id') == target_device:
                        target_label = d.get('friendly_name') or d.get('name') or target_device
                        break
                return {
                    'rule_name': rule_name,
                    'success': False,
                    'message': f"Target device not connected: {target_label}"
                }
            
            # For Bluetooth devices, prefer A2DP profile
            if 'bluez' in connected_target:
                self._ensure_a2dp_profile(connected_target)
            
            # Get applications to match
            applications = rule.get('applications', [])
            keywords = rule.get('application_keywords', [])
            
            # Route matching applications to target device (try all variants)
            routed = self._route_applications(
                applications,
                keywords,
                all_targets
            )
            target_label = connected_target
            for d in self.device_monitor.get_devices():
                if d.get('id') == connected_target:
                    target_label = d.get('friendly_name') or d.get('name') or connected_target
                    break
            return {
                'rule_name': rule_name,
                'success': True,
                'routed_count': routed,
                'message': f"Successfully routed {routed} stream(s) to {target_label}",
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
                           target_devices: List[str]) -> int:
        """Route matching applications to target device
        
        Args:
            applications: List of application names to match
            keywords: List of keywords to search in window titles
            target_devices: List of target device names (tries each one)
            
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
                    logger.debug(f"App '{app_name}' matches rule, routing to {target_devices[0]}")
                    # Try each target device variant until one succeeds
                    for target_device in target_devices:
                        if self._route_stream(app_name, target_device):
                            routed_count += 1
                            break
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
                host_cmd(['pactl', 'list', 'sink-inputs']),
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
                host_cmd(['pactl', 'list', 'sink-inputs']),
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
                host_cmd(['pw-cli', 'set', app_name, 'target.object', target_device]),
                capture_output=True,
                timeout=5,
                check=False
            )
            return True
        except Exception as e:
            logger.debug(f"PipeWire routing failed: {e}")
            return False
    
    def _resolve_sink(self, device_name: str) -> Optional[Tuple[str, str]]:
        """Return (sink_index, sink_name); BT ids match by MAC if PipeWire renumbered suffix."""
        try:
            result = subprocess.run(
                host_cmd(['pactl', 'list', 'sinks']),
                capture_output=True,
                text=True,
                timeout=5
            )
            current_sink_id = None
            for line in result.stdout.split('\n'):
                if 'Sink #' in line:
                    current_sink_id = line.split('#')[1].strip()
                elif 'Name:' in line:
                    name_value = line.split('Name:')[1].strip()
                    if device_name in line or name_value == device_name:
                        return (current_sink_id, name_value)
                    if 'bluez' in device_name.lower() and 'bluez' in name_value.lower():
                        parts = device_name.split('.')
                        if len(parts) >= 2:
                            mac_address = parts[1]
                            if mac_address in name_value:
                                logger.debug(
                                    f"Fuzzy matched Bluetooth sink '{device_name}' to '{name_value}' (sink #{current_sink_id})"
                                )
                                return (current_sink_id, name_value)
            return None
        except Exception as e:
            logger.debug(f"Failed to resolve sink for {device_name}: {e}")
            return None

    def _get_sink_number(self, device_name: str) -> Optional[str]:
        r = self._resolve_sink(device_name)
        return r[0] if r else None
    
    def _route_pa_stream(self, app_name: str, target_device: str) -> bool:
        """Route stream in PulseAudio"""
        try:
            resolved = self._resolve_sink(target_device)
            if not resolved:
                logger.warning("Could not resolve sink for target device %r (not in pactl list sinks)", target_device)
                return False
            target_sink_id, target_sink_name = resolved
            
            logger.debug(
                "Looking for app %r, target sink #%s (%s)",
                app_name,
                target_sink_id,
                target_sink_name,
            )
            
            # Collect every sink-input for this app (browsers may open several streams).
            result = subprocess.run(
                host_cmd(['pactl', 'list', 'sink-inputs']),
                capture_output=True,
                text=True,
                timeout=5
            )
            
            to_move: List[tuple] = []
            current_sink_input = None
            current_sink_num = None
            
            for line in result.stdout.split('\n'):
                line_stripped = line.strip()
                if line_stripped.startswith('Sink Input #'):
                    current_sink_input = line_stripped.split('#')[1].strip()
                    current_sink_num = None
                elif current_sink_input and line_stripped.startswith('Sink:'):
                    parts = line_stripped.split(':', 1)
                    if len(parts) > 1:
                        current_sink_num = parts[1].strip().split()[0] if parts[1].strip() else None
                elif current_sink_input and 'application.name' in line and app_name in line:
                    if current_sink_num is None or current_sink_num != target_sink_id:
                        to_move.append((current_sink_input, current_sink_num))
            
            if not to_move:
                logger.debug(f"No sink inputs to move for {app_name} (missing or already on target)")
                return False

            any_ok = False
            for sink_input_id, _ in to_move:
                for target in (target_sink_name, target_sink_id):
                    move_res = subprocess.run(
                        host_cmd(['pactl', 'move-sink-input', sink_input_id, target]),
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False
                    )
                    if move_res.returncode == 0:
                        logger.debug(
                            "Moved sink input %s (%s) to sink %s",
                            sink_input_id,
                            app_name,
                            target,
                        )
                        any_ok = True
                        break
                else:
                    err = (move_res.stderr or move_res.stdout or "").strip()
                    logger.warning(
                        "move-sink-input failed for %s → %s / #%s: %s",
                        sink_input_id,
                        target_sink_name,
                        target_sink_id,
                        err or f"exit {move_res.returncode}",
                    )
            return any_ok
        except Exception as e:
            logger.debug(f"PulseAudio routing failed: {e}")
            return False
