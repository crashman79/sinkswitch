#!/usr/bin/env python3
"""
Audio routing engine - applies routing rules to audio streams
"""

import subprocess
import logging
import re
from typing import Dict, List, Optional, Set, Tuple
from device_monitor import DeviceMonitor
from host_command import host_cmd, SUBPROCESS_TEXT_KW

logger = logging.getLogger(__name__)


class AudioRouterEngine:
    """Engine for applying audio routing rules"""
    MONO_REMAP_PREFIX = 'sinkswitch_mono.'
    
    def __init__(
        self,
        auto_mono_single_channel_bluetooth: bool = True,
        force_bluetooth_mono: bool = False,
    ):
        self.device_monitor = DeviceMonitor()
        self.auto_mono_single_channel_bluetooth = auto_mono_single_channel_bluetooth
        self.force_bluetooth_mono = force_bluetooth_mono
        self._mono_sink_cache: Dict[str, str] = {}
        self._required_mono_masters: Set[str] = set()
        # Clean stale remap modules from prior runs to avoid nested leftovers.
        self._cleanup_sinkswitch_remaps(startup=True)

    def _normalize_master_sink_name(self, sink_name: str) -> str:
        """Unwrap SinkSwitch mono remap sink names to their underlying master sink."""
        out = sink_name or ''
        while out.startswith(self.MONO_REMAP_PREFIX):
            out = out[len(self.MONO_REMAP_PREFIX):]
        return out

    def cleanup_managed_sinks(self) -> None:
        """Unload all SinkSwitch remap sinks created by this app session."""
        self._required_mono_masters = set()
        self._cleanup_sinkswitch_remaps(startup=True)

    def _friendly_sink_label(self, sink_name: str) -> str:
        """Return a concise human-readable label for a sink id."""
        normalized = self._normalize_master_sink_name(sink_name)
        try:
            for device in self.device_monitor.get_devices():
                if device.get('id') != normalized:
                    continue
                friendly = (
                    device.get('friendly_name')
                    or device.get('description')
                    or device.get('name')
                    or normalized
                )
                friendly = str(friendly).strip()
                return re.sub(r'\s+', ' ', friendly)[:60] if friendly else normalized[:60]
        except Exception as e:
            logger.debug("Failed to resolve friendly sink label for %s: %s", normalized, e)

        fallback = normalized.split('.')[-1].replace('_', ' ').strip()
        fallback = re.sub(r'\s+', ' ', fallback)
        return fallback[:60] if fallback else normalized[:60]

    def _list_sinkswitch_remap_modules(self) -> List[Dict[str, str]]:
        """Return remap module rows for SinkSwitch-managed mono sinks."""
        modules: List[Dict[str, str]] = []
        try:
            result = subprocess.run(
                host_cmd(['pactl', 'list', 'short', 'modules']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5,
            )
            if result.returncode != 0:
                return modules

            for raw_line in result.stdout.split('\n'):
                line = raw_line.strip()
                if not line or 'module-remap-sink' not in line:
                    continue
                parts = line.split(None, 2)
                if len(parts) < 3:
                    continue
                module_id = parts[0]
                args = parts[2]
                sink_match = re.search(r'\bsink_name=([^\s]+)', args)
                master_match = re.search(r'\bmaster=([^\s]+)', args)
                sink_name = sink_match.group(1) if sink_match else ''
                if not sink_name.startswith(self.MONO_REMAP_PREFIX):
                    continue
                modules.append(
                    {
                        'id': module_id,
                        'sink_name': sink_name,
                        'master': master_match.group(1) if master_match else '',
                    }
                )
            return modules
        except Exception as e:
            logger.debug(f"Failed to list SinkSwitch remap modules: {e}")
            return modules

    def _get_sink_states(self) -> Dict[str, str]:
        """Return mapping sink_name -> state from ``pactl list short sinks``."""
        states: Dict[str, str] = {}
        try:
            result = subprocess.run(
                host_cmd(['pactl', 'list', 'short', 'sinks']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5,
            )
            if result.returncode != 0:
                return states
            for raw_line in result.stdout.split('\n'):
                line = raw_line.strip()
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) < 5:
                    continue
                states[parts[1].strip()] = parts[4].strip()
            return states
        except Exception as e:
            logger.debug(f"Failed to read sink states: {e}")
            return states

    def _cleanup_sinkswitch_remaps(self, startup: bool = False) -> None:
        """Unload stale SinkSwitch mono remap modules.

        During runtime, only unload non-running sinks that are not currently required.
        During startup, unload all SinkSwitch remap sinks to clean previous session state.
        """
        modules = self._list_sinkswitch_remap_modules()
        if not modules:
            return

        sink_states = self._get_sink_states()
        removed = 0
        # Unload nested sinks first (longer names first).
        modules_sorted = sorted(modules, key=lambda m: len(m.get('sink_name', '')), reverse=True)

        for mod in modules_sorted:
            sink_name = mod.get('sink_name', '')
            module_id = mod.get('id', '')
            if not sink_name or not module_id:
                continue

            master = self._normalize_master_sink_name(mod.get('master', ''))
            required = master in self._required_mono_masters
            state = sink_states.get(sink_name, 'UNKNOWN')
            should_unload = startup or (not required and state != 'RUNNING')
            if not should_unload:
                continue

            unload_res = subprocess.run(
                host_cmd(['pactl', 'unload-module', module_id]),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5,
                check=False,
            )
            if unload_res.returncode == 0:
                self._mono_sink_cache.pop(master, None)
                removed += 1
            else:
                err = (unload_res.stderr or unload_res.stdout or '').strip()
                logger.debug(
                    "Failed to unload SinkSwitch remap module %s (%s): %s",
                    module_id,
                    sink_name,
                    err or f"exit {unload_res.returncode}",
                )

        if removed:
            phase = 'startup' if startup else 'runtime'
            logger.info("Cleaned %d stale SinkSwitch remap module(s) during %s", removed, phase)

    def _get_sink_channel_count(self, sink_name: str) -> Optional[int]:
        """Return sink channel count parsed from ``pactl list sinks``."""
        try:
            result = subprocess.run(
                host_cmd(['pactl', 'list', 'sinks']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5,
            )
            if result.returncode != 0:
                return None

            in_target_sink = False
            for raw_line in result.stdout.split('\n'):
                line = raw_line.strip()
                if line.startswith('Sink #'):
                    in_target_sink = False
                    continue
                if line.startswith('Name:'):
                    name_value = line.split(':', 1)[1].strip()
                    in_target_sink = (name_value == sink_name)
                    continue
                if not in_target_sink:
                    continue

                if line.startswith('Sample Specification:'):
                    sample_spec = line.split(':', 1)[1].strip()
                    match = re.search(r'(\d+)ch\b', sample_spec)
                    if match:
                        return int(match.group(1))
                elif line.startswith('Channel Map:'):
                    channel_map = line.split(':', 1)[1].strip().lower()
                    channels = [c.strip() for c in channel_map.split(',') if c.strip()]
                    if channels:
                        if len(channels) == 1 and channels[0] == 'mono':
                            return 1
                        return len(channels)
            return None
        except Exception as e:
            logger.debug(f"Failed to read channel count for sink {sink_name}: {e}")
            return None

    def _is_single_channel_bluetooth_sink(self, sink_name: str) -> bool:
        """Detect Bluetooth sinks that currently report one channel."""
        if 'bluez' not in (sink_name or '').lower():
            return False
        channel_count = self._get_sink_channel_count(sink_name)
        return channel_count == 1

    def _find_existing_mono_remap_sink(self, master_sink: str) -> Optional[str]:
        """Return existing mono remap sink name for a master sink, if present."""
        normalized_master = self._normalize_master_sink_name(master_sink)
        try:
            result = subprocess.run(
                host_cmd(['pactl', 'list', 'short', 'modules']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5,
            )
            if result.returncode != 0:
                return None

            for raw_line in result.stdout.split('\n'):
                line = raw_line.strip()
                if not line or 'module-remap-sink' not in line:
                    continue
                if 'master=' not in line:
                    continue
                master_match = re.search(r'\bmaster=([^\s]+)', line)
                if not master_match:
                    continue
                found_master = self._normalize_master_sink_name(master_match.group(1))
                if found_master != normalized_master:
                    continue
                sink_match = re.search(r'\bsink_name=([^\s]+)', line)
                if sink_match:
                    sink_name = sink_match.group(1)
                    if sink_name.startswith(self.MONO_REMAP_PREFIX):
                        return sink_name
            return None
        except Exception as e:
            logger.debug(f"Failed to list remap sinks for {master_sink}: {e}")
            return None

    def _ensure_mono_remap_sink(self, master_sink: str) -> str:
        """Create/reuse a mono remap sink for master_sink; return sink to route to."""
        master_sink = self._normalize_master_sink_name(master_sink)
        cached = self._mono_sink_cache.get(master_sink)
        if cached and self._resolve_sink(cached):
            self._ensure_remap_stream_on_master_sink(master_sink)
            return cached

        existing = self._find_existing_mono_remap_sink(master_sink)
        if existing and self._resolve_sink(existing):
            self._mono_sink_cache[master_sink] = existing
            self._ensure_remap_stream_on_master_sink(master_sink)
            return existing

        sanitized = re.sub(r'[^a-zA-Z0-9_.-]', '_', master_sink)
        mono_sink_name = f"{self.MONO_REMAP_PREFIX}{sanitized}"[:120]
        sink_label = self._friendly_sink_label(master_sink)
        sink_desc = f"SinkSwitch Mono ({sink_label})"[:160]

        result = subprocess.run(
            host_cmd([
                'pactl',
                'load-module',
                'module-remap-sink',
                f'sink_name={mono_sink_name}',
                f'master={master_sink}',
                f"sink_properties=device.description='{sink_desc}'",
                'channels=1',
                'channel_map=mono',
                'remix=yes',
            ]),
            capture_output=True,
            text=True,
            **SUBPROCESS_TEXT_KW,
            timeout=5,
            check=False,
        )

        if result.returncode != 0:
            err = (result.stderr or result.stdout or '').strip()
            logger.warning(
                "Failed to create mono remap sink for %s: %s",
                master_sink,
                err or f"exit {result.returncode}",
            )
            return master_sink

        if self._resolve_sink(mono_sink_name):
            logger.info("Created mono remap sink %s for %s", mono_sink_name, master_sink)
            self._mono_sink_cache[master_sink] = mono_sink_name
            self._ensure_remap_stream_on_master_sink(master_sink)
            return mono_sink_name

        logger.warning("Mono remap sink %s was created but not resolvable; using %s", mono_sink_name, master_sink)
        return master_sink

    def _get_effective_target_sink(self, sink_name: str) -> str:
        """Return sink name to route to, enabling mono for single-channel Bluetooth."""
        if 'bluez' not in (sink_name or '').lower():
            return sink_name
        master_sink = self._normalize_master_sink_name(sink_name)
        if self.force_bluetooth_mono:
            mono_sink = self._ensure_mono_remap_sink(master_sink)
            if mono_sink != sink_name:
                logger.info("Forced Bluetooth mono enabled for %s; routing via %s", sink_name, mono_sink)
            self._required_mono_masters.add(master_sink)
            return mono_sink
        if not self.auto_mono_single_channel_bluetooth:
            return sink_name
        if not self._is_single_channel_bluetooth_sink(master_sink):
            return sink_name
        mono_sink = self._ensure_mono_remap_sink(master_sink)
        if mono_sink != sink_name:
            logger.info("Single-channel Bluetooth sink detected for %s; routing via %s", sink_name, mono_sink)
        self._required_mono_masters.add(master_sink)
        return mono_sink
    
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
        self._required_mono_masters = set()
        
        for rule in rules:
            result = self._apply_rule(rule)
            results.append(result)

        # Also enforce fallback behavior for streams that do not match any rule.
        results.append(self._route_unmatched_streams_to_default(rules))
        self._cleanup_sinkswitch_remaps(startup=False)
        
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
            effective_targets: List[str] = []
            for target in all_targets:
                resolved_target = self._get_effective_target_sink(target)
                if resolved_target not in effective_targets:
                    effective_targets.append(resolved_target)

            routed = self._route_applications(
                applications,
                keywords,
                effective_targets
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
        app_lower = (app_name or '').lower().strip()
        if not app_lower:
            return False
        
        # Check exact matches
        for app in applications:
            if app.lower() in app_lower or app_lower in app.lower():
                return True
        
        # Check keyword matches
        for keyword in keywords:
            if keyword.lower() in app_lower:
                return True
        
        return False

    def _matches_any_rule(self, app_name: str, rules: List[Dict]) -> bool:
        """Return True when app_name matches any configured routing rule."""
        for rule in rules:
            if self._matches_rule(
                app_name,
                rule.get('applications', []),
                rule.get('application_keywords', []),
            ):
                return True
        return False

    def _get_sink_inputs(self) -> List[Dict[str, str]]:
        """Return sink-input rows with index, sink, and metadata used for filtering."""
        try:
            result = subprocess.run(
                host_cmd(['pactl', 'list', 'sink-inputs']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5,
            )
            if result.returncode != 0:
                return []

            streams: List[Dict[str, str]] = []
            current: Dict[str, str] = {}
            for raw_line in result.stdout.split('\n'):
                line = raw_line.strip()
                if line.startswith('Sink Input #'):
                    if current and current.get('index'):
                        streams.append(current)
                    current = {'index': line.split('#', 1)[1].strip()}
                elif not current:
                    continue
                elif line.startswith('Sink:'):
                    sink_part = line.split(':', 1)[1].strip().split()
                    if sink_part:
                        current['sink'] = sink_part[0]
                elif 'application.name' in line and '=' in line:
                    app_name = line.split('=', 1)[1].strip().strip('"')
                    current['application_name'] = app_name
                elif 'media.name' in line and '=' in line:
                    media_name = line.split('=', 1)[1].strip().strip('"')
                    current['media_name'] = media_name
                elif 'node.name' in line and '=' in line:
                    node_name = line.split('=', 1)[1].strip().strip('"')
                    current['node_name'] = node_name

            if current and current.get('index'):
                streams.append(current)
            return streams
        except Exception as e:
            logger.debug(f"Failed to read sink inputs: {e}")
            return []

    def _is_internal_mono_remap_stream(self, stream: Dict[str, str]) -> bool:
        """Return True when sink-input is the internal stream of our mono remap sink."""
        node_name = (stream.get('node_name') or '').lower()
        media_name = (stream.get('media_name') or '').lower()
        app_name = (stream.get('application_name') or '').lower()
        if 'sinkswitch_mono.' in node_name:
            return True
        if 'remapped ' in media_name and 'bluez_output.' in media_name:
            return True
        if app_name.startswith('sinkswitch_mono.'):
            return True
        return False

    def _move_sink_input(self, sink_input_id: str, target_sink_name: str, target_sink_id: str) -> bool:
        """Move one sink-input, trying sink name first then numeric id."""
        for target in (target_sink_name, target_sink_id):
            move_res = subprocess.run(
                host_cmd(['pactl', 'move-sink-input', sink_input_id, target]),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5,
                check=False,
            )
            if move_res.returncode == 0:
                return True
        err = (move_res.stderr or move_res.stdout or '').strip()
        logger.warning(
            "move-sink-input failed for %s -> %s / #%s: %s",
            sink_input_id,
            target_sink_name,
            target_sink_id,
            err or f"exit {move_res.returncode}",
        )
        return False

    def _ensure_remap_stream_on_master_sink(self, master_sink: str) -> None:
        """Move mono remap internal stream back to master sink if fallback displaced it."""
        master_resolved = self._resolve_sink(master_sink)
        if not master_resolved:
            return
        master_sink_id, master_sink_name = master_resolved
        for stream in self._get_sink_inputs():
            if not self._is_internal_mono_remap_stream(stream):
                continue
            sink_input_id = stream.get('index')
            current_sink_id = stream.get('sink')
            if not sink_input_id or not current_sink_id or current_sink_id == master_sink_id:
                continue
            if self._move_sink_input(sink_input_id, master_sink_name, master_sink_id):
                logger.info(
                    "Moved internal mono remap stream %s back to master sink %s",
                    sink_input_id,
                    master_sink_name,
                )

    def _route_unmatched_streams_to_default(self, rules: List[Dict]) -> Dict:
        """Move streams that match no rule to the current default sink."""
        default_sink_name = self.device_monitor.get_default_sink()
        if not default_sink_name:
            return {
                'rule_name': 'Default fallback',
                'success': False,
                'routed_count': 0,
                'message': 'No default sink available',
            }

        resolved = self._resolve_sink(default_sink_name)
        if not resolved:
            return {
                'rule_name': 'Default fallback',
                'success': False,
                'routed_count': 0,
                'message': f"Could not resolve default sink: {default_sink_name}",
            }

        default_sink_id, default_sink_name_resolved = resolved
        effective_default_sink = self._get_effective_target_sink(default_sink_name_resolved)
        if effective_default_sink != default_sink_name_resolved:
            effective_resolved = self._resolve_sink(effective_default_sink)
            if effective_resolved:
                default_sink_id, default_sink_name_resolved = effective_resolved
        streams = self._get_sink_inputs()
        moved = 0

        for stream in streams:
            if self._is_internal_mono_remap_stream(stream):
                continue
            app_name = stream.get('application_name', '')
            if not app_name:
                continue
            if self._matches_any_rule(app_name, rules):
                continue
            if stream.get('sink') == default_sink_id:
                continue

            sink_input_id = stream.get('index')
            if not sink_input_id:
                continue
            if self._move_sink_input(sink_input_id, default_sink_name_resolved, default_sink_id):
                moved += 1

        return {
            'rule_name': 'Default fallback',
            'success': True,
            'routed_count': moved,
            'message': f"Routed {moved} unmatched stream(s) to default output",
        }
    
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
                **SUBPROCESS_TEXT_KW,
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
                **SUBPROCESS_TEXT_KW,
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
            device_name_lower = (device_name or '').lower()
            use_bluetooth_fuzzy = device_name_lower.startswith('bluez_output.')
            result = subprocess.run(
                host_cmd(['pactl', 'list', 'sinks']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
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
                    if use_bluetooth_fuzzy and 'bluez' in name_value.lower():
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
                **SUBPROCESS_TEXT_KW,
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
                        **SUBPROCESS_TEXT_KW,
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
