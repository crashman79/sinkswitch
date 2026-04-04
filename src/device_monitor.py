#!/usr/bin/env python3
"""
Device monitoring module for detecting and tracking audio output devices
"""

import logging
import subprocess
import json
from host_command import host_cmd, SUBPROCESS_TEXT_KW
from collections import defaultdict
from typing import Dict, List, Optional, Callable, Set, Tuple
from dataclasses import dataclass
import time
import threading

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
        self.last_devices: List[Dict] = []
        self.last_streams = []  # Track audio streams
        self._detect_audio_backend()
        self.bluetooth_devices_cache = {}  # Cache of Bluetooth device info
        self.bluetooth_profile_state = {}  # Track Bluetooth device profiles
        self.last_config_regeneration = 0  # Timestamp of last config regeneration
        self.config_regeneration_cooldown = 10  # Minimum seconds between regenerations
        self._last_periodic_rule_apply_ts = 0.0

    def _detect_audio_backend(self):
        """Detect which audio backend is available (PipeWire or PulseAudio)"""
        try:
            subprocess.run(host_cmd(['pw-cli', 'info']),
                          capture_output=True,
                          check=False,
                          timeout=2)
            self.backend = 'pipewire'
            logger.debug("Detected PipeWire audio backend")
        except FileNotFoundError:
            self.backend = 'pulseaudio'
            logger.debug("Detected PulseAudio audio backend")
    
    def get_devices(self) -> List[Dict]:
        """Get list of available audio output devices"""
        if self.backend == 'pipewire':
            return self._get_pipewire_devices()
        else:
            return self._get_pulseaudio_devices()

    def get_default_sink(self) -> Optional[str]:
        """Return the current default sink name (where unmatched audio goes), or None."""
        try:
            r = subprocess.run(
                host_cmd(['pactl', 'get-default-sink']),
                capture_output=True, text=True, timeout=2, **SUBPROCESS_TEXT_KW
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception as e:
            logger.debug(f"get_default_sink: {e}")
        return None

    def set_default_sink(self, sink_name: str) -> bool:
        """Set the default sink (fallback for unmatched streams). Returns True on success."""
        try:
            r = subprocess.run(
                host_cmd(['pactl', 'set-default-sink', sink_name]),
                capture_output=True, text=True, timeout=2, **SUBPROCESS_TEXT_KW
            )
            return r.returncode == 0
        except Exception as e:
            logger.debug(f"set_default_sink: {e}")
            return False
    
    def get_bluetooth_card_info(self, device_address: str) -> Optional[Dict]:
        """Get Bluetooth card profile information
        
        Args:
            device_address: Bluetooth MAC address (e.g., 00:02:3C:AD:09:85)
        
        Returns:
            Dictionary with card info including available profiles and active profile
        """
        try:
            result = subprocess.run(
                host_cmd(['pactl', 'list', 'cards']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
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
                host_cmd(['pactl', 'list', 'sinks', 'short']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
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
                host_cmd(['pactl', 'set-card-profile', card_name, profile]),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
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

    def _classify_device_type(self, device: Dict) -> str:
        """Return a friendly type: bluetooth, usb_headset, hdmi, analog_speakers, unknown."""
        text = f"{device.get('id', '')} {device.get('name', '')} {device.get('description', '')}".lower()
        if 'bluez' in text or 'bluetooth' in text:
            return 'bluetooth'
        if 'usb' in text:
            return 'usb_headset' if ('headset' in text or 'headphone' in text) else 'usb_speakers'
        if 'hdmi' in text or 'displayport' in text:
            return 'hdmi'
        if 'analog' in text or 'line out' in text or 'built-in' in text:
            return 'analog_speakers'
        return 'unknown'

    def _get_friendly_name(self, device: Dict) -> str:
        """Return a short, human-readable name for the device."""
        desc = device.get('description') or ''
        name = device.get('name') or ''
        dev_id = device.get('id') or ''
        # Use description when it looks like a real name (not a long technical string)
        if desc and len(desc) <= 60 and desc != name and not desc.startswith('alsa_'):
            return desc.strip()
        # Derive from id/name
        text = (dev_id + ' ' + name).lower()
        if 'bluez' in text:
            return desc.strip() if desc else 'Bluetooth'
        if 'hdmi' in text or 'displayport' in text:
            return desc.strip() if desc else 'HDMI'
        if 'usb' in text:
            return desc.strip() if desc else 'USB Audio'
        if 'analog' in text or 'alsa' in text:
            return desc.strip() if desc else 'Built-in Audio'
        return desc.strip() or name[:50] or dev_id[:50]

    def _enrich_device(self, device: Dict) -> None:
        """Set device_type and friendly_name on device dict."""
        device['device_type'] = self._classify_device_type(device)
        device['friendly_name'] = self._get_friendly_name(device)

    def _finalize_sink_devices(self, devices: List[Dict]) -> List[Dict]:
        """Drop incomplete pactl sink blocks; normalize id/name (avoids KeyError in GUI/monitor)."""
        out: List[Dict] = []
        for d in devices:
            dev_id = (d.get('id') or d.get('name') or '').strip()
            if not dev_id:
                logger.debug("Skipping sink entry without id/name: %s", d)
                continue
            d['id'] = dev_id
            if not d.get('name'):
                d['name'] = dev_id
            out.append(d)
        return out

    def _get_pipewire_devices(self) -> List[Dict]:
        """Get devices using PipeWire"""
        try:
            # Use pactl as fallback since pw-cli output varies
            result = subprocess.run(
                host_cmd(['pactl', 'list', 'sinks']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5
            )
            
            devices = []
            current_device = {}
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                
                if line.startswith('Sink #'):
                    if current_device:
                        self._enrich_device(current_device)
                        devices.append(current_device)
                    current_device = {
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
                self._enrich_device(current_device)
                devices.append(current_device)
            
            return self._finalize_sink_devices(devices)
        except Exception as e:
            logger.error(f"Failed to get PipeWire devices: {e}")
            return []
    
    def _get_pulseaudio_devices(self) -> List[Dict]:
        """Get devices using PulseAudio"""
        try:
            result = subprocess.run(
                host_cmd(['pactl', 'list', 'sinks']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5
            )
            
            devices = []
            current_device = {}
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                
                if line.startswith('Sink #'):
                    if current_device:
                        self._enrich_device(current_device)
                        devices.append(current_device)
                    current_device = {
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
                self._enrich_device(current_device)
                devices.append(current_device)
            
            return self._finalize_sink_devices(devices)
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
    
    def _run_watch_iteration(
        self,
        callback: Callable,
        config_regen_callback: Optional[Callable],
        rules_ref: Optional[List[Dict]],
    ) -> None:
        """One iteration: fetch state, optional config regen, relevance check, callback if needed."""
        current_devices = self.get_devices()
        current_streams = self._get_audio_streams()

        self._monitor_bluetooth_profiles(current_devices)

        if config_regen_callback and self._is_significant_device_change(current_devices):
            time_since_last = time.time() - self.last_config_regeneration
            if time_since_last >= self.config_regeneration_cooldown:
                logger.info("Triggering config regeneration due to significant device change")
                try:
                    config_regen_callback()
                    self.last_config_regeneration = time.time()
                except Exception as e:
                    logger.error(f"Failed to regenerate config: {e}")
            else:
                logger.debug("Skipping config regeneration (cooldown)")

        now = time.time()
        periodic_rules = bool(rules_ref) and (now - self._last_periodic_rule_apply_ts >= 15.0)
        if periodic_rules:
            self._last_periodic_rule_apply_ts = now

        device_changed = self._devices_changed(current_devices)
        stream_changed = self._streams_changed(current_streams)
        if rules_ref:
            rule_target_ids = self._get_rule_target_device_ids(rules_ref)
            device_changed = device_changed and rule_target_ids and self._device_change_involves_rules(current_devices, rule_target_ids)
            stream_changed = stream_changed and self._stream_change_involves_rules(current_streams, rules_ref)

        if periodic_rules or device_changed or stream_changed:
            if periodic_rules and not device_changed and not stream_changed:
                logger.debug("Periodic routing re-apply")
            elif device_changed and stream_changed:
                logger.info("Devices and audio streams changed - applying routing rules")
            elif device_changed:
                logger.info("Device configuration changed - applying routing rules")
            elif stream_changed:
                logger.info("Audio streams changed - applying routing rules")
            self.last_devices = current_devices
            self.last_streams = current_streams
            callback()

    def watch_devices(self, callback: Callable, interval: int = 5, config_regen_callback: Optional[Callable] = None, stop_event: Optional[threading.Event] = None, rules_ref: Optional[List[Dict]] = None):
        """Watch for device changes and call callback when changes detected.

        Uses pactl subscribe (event-based) when available for low latency and no polling;
        falls back to polling every interval seconds if subscribe is unavailable.
        """
        if self._try_watch_via_pactl_subscribe(callback, config_regen_callback, stop_event, rules_ref, interval):
            return
        logger.info("Event-based monitoring unavailable, using polling (interval=%ss)", interval)
        if config_regen_callback:
            logger.info("Config auto-regeneration enabled for bluetooth/USB device changes")
        try:
            while stop_event is None or not stop_event.is_set():
                self._run_watch_iteration(callback, config_regen_callback, rules_ref)
                for _ in range(interval):
                    if stop_event and stop_event.is_set():
                        break
                    time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Device monitoring stopped")
        except Exception as e:
            logger.error(f"Error during device monitoring: {e}")

    def _try_watch_via_pactl_subscribe(
        self,
        callback: Callable,
        config_regen_callback: Optional[Callable],
        stop_event: Optional[threading.Event],
        rules_ref: Optional[List[Dict]],
        poll_interval_fallback: int,
    ) -> bool:
        """Run watch loop driven by pactl subscribe events. Returns True if we ran to completion (or stop)."""
        try:
            proc = subprocess.Popen(
                host_cmd(['pactl', 'subscribe']),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                **SUBPROCESS_TEXT_KW,
                bufsize=1,
            )
        except (FileNotFoundError, OSError) as e:
            logger.debug("pactl subscribe not available: %s", e)
            return False
        event_occurred = threading.Event()
        debounce_sec = 0.5
        bt_interval_sec = 30.0
        last_bt = time.time()

        def read_events():
            try:
                for line in proc.stdout:
                    if stop_event and stop_event.is_set():
                        break
                    line = (line or '').strip().lower()
                    if not line or line.startswith('Event '):
                        continue
                    if 'sink' in line or 'server' in line:
                        event_occurred.set()
            except Exception as e:
                logger.debug("pactl subscribe read error: %s", e)
            finally:
                try:
                    proc.terminate()
                except Exception:
                    pass

        reader = threading.Thread(target=read_events, daemon=True)
        reader.start()
        logger.info("Device monitoring using pactl subscribe (event-based)")

        try:
            while stop_event is None or not stop_event.is_set():
                if proc.poll() is not None:
                    logger.info("pactl subscribe exited, falling back to polling")
                    return False
                now = time.time()
                timeout = min(debounce_sec, max(0.1, bt_interval_sec - (now - last_bt)))
                timeout = max(0.1, min(timeout, 1.0))
                if event_occurred.wait(timeout=timeout):
                    event_occurred.clear()
                    time.sleep(debounce_sec)
                    if stop_event and stop_event.is_set():
                        break
                    self._run_watch_iteration(callback, config_regen_callback, rules_ref)
                if now - last_bt >= bt_interval_sec:
                    last_bt = now
                    self._run_watch_iteration(callback, config_regen_callback, rules_ref)
        except KeyboardInterrupt:
            logger.info("Device monitoring stopped")
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                pass
        return True
    
    def _devices_changed(self, current_devices: List[Dict]) -> bool:
        """Check if device list has changed"""
        if not self.last_devices and current_devices:
            self.last_devices = current_devices
            return True
        
        if len(current_devices) != len(self.last_devices):
            return True
        
        current_ids = {d.get('id') for d in current_devices if d.get('id')}
        last_ids = {d.get('id') for d in self.last_devices if d.get('id')}
        
        if current_ids != last_ids:
            return True
        
        # Check connection state changes
        for device in current_devices:
            last_device = next(
                (d for d in self.last_devices if d.get('id') == device.get('id')),
                None
            )
            if last_device and device.get('connected') != last_device.get('connected'):
                return True
        
        return False
    
    def _get_audio_streams(self) -> List[Dict]:
        """Get list of active audio streams (sink-inputs)
        
        Returns:
            List of stream dictionaries with 'index', 'sink' (numeric id), and
            'application_name'. Including 'sink' is required so we detect when
            PipeWire/Pulse stream-restore or the default sink moves a matched
            stream back off the rule target without changing application.name.
        """
        try:
            result = subprocess.run(
                host_cmd(['pactl', 'list', 'sink-inputs']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                check=False,
            )
            if result.returncode != 0:
                return []
            
            streams = []
            current_stream: Dict = {}
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                
                if line.startswith('Sink Input #'):
                    if current_stream and 'application_name' in current_stream:
                        streams.append(current_stream)
                    current_stream = {'index': line.split('#')[1]}
                elif current_stream and line.startswith('Sink:'):
                    parts = line.split(':', 1)
                    if len(parts) > 1:
                        sink_part = parts[1].strip().split()
                        if sink_part:
                            current_stream['sink'] = sink_part[0]
                elif current_stream and 'application.name' in line and '=' in line:
                    app_name = line.split('=')[1].strip().strip('"')
                    current_stream['application_name'] = app_name
            
            # Add last stream
            if current_stream and 'application_name' in current_stream:
                streams.append(current_stream)
            
            return streams
            
        except Exception as e:
            logger.debug(f"Failed to get audio streams: {e}")
            return []
    
    def _streams_changed(self, current_streams: List[Dict]) -> bool:
        """Check if audio streams have changed
        
        Args:
            current_streams: List of current audio streams
            
        Returns:
            True if streams changed (new/removed stream, app name, or sink-input sink)
        """
        if len(current_streams) != len(self.last_streams):
            return True
        
        def stream_sig(s: Dict) -> tuple:
            return (
                s.get('index') or '',
                s.get('application_name', ''),
                s.get('sink') or '',
            )

        return sorted(stream_sig(s) for s in current_streams) != sorted(
            stream_sig(s) for s in self.last_streams
        )

    def _get_rule_target_device_ids(self, rules: List[Dict]) -> Set[str]:
        """Set of device ids that are targets of any rule (including variants)."""
        out: Set[str] = set()
        for r in rules:
            tid = r.get('target_device')
            if tid:
                out.add(tid)
            for v in r.get('target_device_variants') or []:
                out.add(v)
        return out

    @staticmethod
    def _bluez_mac_from_sink_id(sink_id: str) -> Optional[str]:
        """MAC segment from e.g. bluez_output.00_02_3C_AD_09_85.2 → 00_02_3C_AD_09_85."""
        if not sink_id or 'bluez' not in sink_id.lower():
            return None
        parts = sink_id.split('.')
        return parts[1] if len(parts) >= 2 else None

    def _bluez_macs_from_rule_targets(self, rule_target_ids: Set[str]) -> Set[str]:
        return {m for tid in rule_target_ids if (m := self._bluez_mac_from_sink_id(tid))}

    def _bluez_snapshots_for_macs(
        self, devices: List[Dict], macs: Set[str]
    ) -> Dict[str, Tuple[Tuple[str, bool], ...]]:
        """Per-MAC sorted (sink_id, connected) tuples for comparing reconnect / profile churn."""
        by_mac: Dict[str, List[Tuple[str, bool]]] = defaultdict(list)
        for d in devices:
            did = d.get('id') or ''
            m = self._bluez_mac_from_sink_id(did)
            if m in macs:
                by_mac[m].append((did, bool(d.get('connected'))))
        return {m: tuple(sorted(by_mac[m])) for m in macs}

    def _bluetooth_rule_target_state_changed(self, current_devices: List[Dict], rule_target_ids: Set[str]) -> bool:
        """True when a rule-target BT device (by MAC) appeared, vanished, renumbered, or toggled connected."""
        macs = self._bluez_macs_from_rule_targets(rule_target_ids)
        if not macs:
            return False
        return self._bluez_snapshots_for_macs(self.last_devices, macs) != self._bluez_snapshots_for_macs(
            current_devices, macs
        )

    def _device_change_involves_rules(self, current_devices: List[Dict], rule_target_ids: Set[str]) -> bool:
        """True if connection state changed for any device that is a rule target.

        Bluetooth sinks are matched by MAC: PipeWire often creates a new sink suffix after reconnect
        (e.g. .1 → .2) while YAML still references the old id — strict id-only checks would skip routing.
        """
        if not rule_target_ids:
            return True
        last_by_id = {d['id']: d for d in self.last_devices if d.get('id')}
        for d in current_devices:
            did = d.get('id')
            if did not in rule_target_ids:
                continue
            old = last_by_id.get(did)
            if old is None:
                return True  # new rule-target device appeared
            if d.get('connected') != old.get('connected'):
                return True
        current_ids = {d.get('id') for d in current_devices if d.get('id')}
        for did in rule_target_ids:
            if did in last_by_id and did not in current_ids:
                return True  # rule-target device disappeared
        if self._bluetooth_rule_target_state_changed(current_devices, rule_target_ids):
            return True
        return False

    @staticmethod
    def _app_matches_rule(app_name: str, rule: Dict) -> bool:
        """True if app_name matches the rule's applications or keywords."""
        app_lower = (app_name or '').lower()
        for a in rule.get('applications') or []:
            if a.lower() in app_lower or app_lower in a.lower():
                return True
        for kw in rule.get('application_keywords') or []:
            if kw.lower() in app_lower:
                return True
        return False

    def _stream_change_involves_rules(self, current_streams: List[Dict], rules_ref: List[Dict]) -> bool:
        """True if rule-matching streams changed (count, identity, or current sink)."""
        if not rules_ref:
            return True

        def matching_sigs(streams: List[Dict]) -> frozenset:
            return frozenset(
                (
                    s.get('index') or '',
                    s.get('application_name') or '',
                    s.get('sink') or '',
                )
                for s in streams
                if any(self._app_matches_rule(s.get('application_name') or '', r) for r in rules_ref)
            )

        return matching_sigs(current_streams) != matching_sigs(self.last_streams)
    
    def _is_significant_device_change(self, current_devices: List[Dict]) -> bool:
        """Check if device changes are significant enough to trigger config regeneration
        
        Significant changes are:
        - Bluetooth devices connecting/disconnecting
        - USB headsets connecting/disconnecting
        - Any device with 'bluez' or 'usb' in the ID
        """
        if not self.last_devices:
            return False
        
        current_ids = {d.get('id') for d in current_devices if d.get('id')}
        last_ids = {d.get('id') for d in self.last_devices if d.get('id')}
        
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
                host_cmd(['pactl', 'list', 'source-outputs', 'short']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5
            )
            
            # If there are any source outputs (mic streams), return True
            return bool(result.stdout.strip())
        
        except Exception as e:
            logger.debug(f"Failed to check mic streams: {e}")
            return False
