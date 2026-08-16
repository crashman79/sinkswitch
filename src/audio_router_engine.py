#!/usr/bin/env python3
"""
Audio routing engine - applies routing rules to audio streams
"""

import subprocess
import logging
import re
import time
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
        self._mono_master_sink_id_cache: Dict[str, str] = {}
        self._required_mono_masters: Set[str] = set()
        # Clean stale remap modules from earlier sessions.
        self._cleanup_sinkswitch_remaps(startup=True)

    def _normalize_master_sink_name(self, sink_name: str) -> str:
        """Unwrap SinkSwitch mono remap sink names to their physical master sink."""
        out = sink_name or ''
        while out.startswith(self.MONO_REMAP_PREFIX):
            out = out[len(self.MONO_REMAP_PREFIX):]
        return out

    def _list_sinkswitch_remap_modules(self) -> List[Dict[str, str]]:
        """Return module rows for SinkSwitch-managed remap sinks."""
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
        """Return mapping sink_name -> state from pactl list short sinks."""
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

        Runtime unload/reload churn can introduce audible fallback-to-default
        windows when browsers recreate streams. Keep remaps stable during normal
        operation and only perform destructive cleanup at startup/shutdown.
        """
        if not startup:
            return
        modules = self._list_sinkswitch_remap_modules()
        if not modules:
            return

        sink_states = self._get_sink_states()
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

    def _get_sink_channel_count(self, sink_name: str) -> Optional[int]:
        """Return sink channel count parsed from pactl list sinks."""
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

    @staticmethod
    def _sink_state_rank(state: str) -> int:
        """Lower rank means a better sink candidate for immediate routing."""
        normalized = (state or '').strip().upper()
        if normalized == 'RUNNING':
            return 0
        if normalized == 'IDLE':
            return 1
        if normalized == 'SUSPENDED':
            return 2
        if normalized == 'UNKNOWN':
            return 3
        if normalized == 'UNAVAILABLE':
            return 9
        return 4

    def _prioritize_target_sinks(self, preferred_target: str, all_targets: List[str]) -> List[str]:
        """Sort target sink ids so active/available Bluetooth variants are tried first."""
        deduped: List[str] = []
        seen: Set[str] = set()
        for target in all_targets:
            if not target or target in seen:
                continue
            deduped.append(target)
            seen.add(target)

        if not deduped:
            return []

        sink_states = self._get_sink_states()
        default_sink_name = self.device_monitor.get_default_sink() or ''

        # Keep non-Bluetooth ordering stable to avoid behavior changes elsewhere.
        if not any('bluez' in target.lower() for target in deduped):
            return deduped

        preferred_state = sink_states.get(preferred_target, 'UNKNOWN')
        if preferred_state.upper() == 'UNAVAILABLE':
            preferred_state = 'UNKNOWN'

        scored: List[Tuple[Tuple[int, int, int, int], str]] = []
        for index, target in enumerate(deduped):
            resolved = self._resolve_sink(target, allow_managed_remaps=False)
            resolved_name = resolved[1] if resolved else target
            state = sink_states.get(resolved_name, sink_states.get(target, 'UNKNOWN'))
            unavailable_penalty = 1 if state.upper() == 'UNAVAILABLE' else 0
            default_bonus = 0 if (default_sink_name and resolved_name == default_sink_name) else 1
            state_rank = self._sink_state_rank(state)
            preferred_bonus = 0 if (target == preferred_target and preferred_state.upper() != 'UNAVAILABLE') else 1
            score = (unavailable_penalty, default_bonus, state_rank, preferred_bonus, index)
            scored.append((score, target))

        scored.sort(key=lambda item: item[0])
        return [target for _, target in scored]

    def _is_single_channel_bluetooth_sink(self, sink_name: str) -> bool:
        """Detect Bluetooth sinks that currently report one output channel."""
        if 'bluez' not in (sink_name or '').lower():
            return False
        return self._get_sink_channel_count(sink_name) == 1

    def _find_existing_mono_remap_sink(self, master_sink: str) -> Optional[str]:
        """Return existing mono remap sink name for master_sink, if present.

        The master= field stored in the module args is the resolved PipeWire sink
        name (may include profile suffix).  We match by MAC address for Bluetooth
        sinks so fuzzy-named devices are still recognised.
        """
        normalized_master = self._normalize_master_sink_name(master_sink)
        # Extract MAC portion for fuzzy BT matching (XX_XX_XX_XX_XX_XX)
        bt_mac: Optional[str] = None
        if 'bluez' in normalized_master.lower():
            parts = normalized_master.split('.')
            if len(parts) >= 2:
                bt_mac = parts[1]

        for mod in self._list_sinkswitch_remap_modules():
            mod_master = self._normalize_master_sink_name(mod.get('master', ''))
            if mod_master == normalized_master:
                sink_name = mod.get('sink_name', '')
                if sink_name:
                    return sink_name
            if bt_mac and bt_mac in mod_master:
                sink_name = mod.get('sink_name', '')
                if sink_name:
                    return sink_name
        return None

    def _fix_remap_output_routing(self, mono_sink_name: str, actual_master_name: str) -> None:
        """Move the remap module's internal output stream to the correct master sink.

        WirePlumber persists per-stream routing state by node name.  When a remap
        sink is recreated (or loaded for the first time after a stale state entry
        exists), WirePlumber will route the 'output.<mono_sink_name>' stream back
        to whatever sink it last used (often the system default / analog), ignoring
        the master= argument we passed to module-remap-sink.  Explicitly moving
        the stream overwrites that state so PipeWire routes correctly.
        """
        output_node_name = f"output.{mono_sink_name}"
        resolved = self._resolve_sink(actual_master_name, allow_managed_remaps=False)
        if not resolved:
            logger.debug("_fix_remap_output_routing: cannot resolve master %r", actual_master_name)
            return
        master_id, master_name = resolved

        try:
            result = subprocess.run(
                host_cmd(['pactl', 'list', 'sink-inputs']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                return

            current_id: Optional[str] = None
            current_sink: Optional[str] = None
            current_node: Optional[str] = None
            for raw_line in result.stdout.split('\n'):
                line = raw_line.strip()
                if line.startswith('Sink Input #'):
                    # Process previous entry
                    if current_id and current_node == output_node_name and current_sink != master_id:
                        self._move_sink_input(current_id, master_name, master_id)
                        logger.debug(
                            "Corrected remap output stream %r from sink #%s to %s",
                            output_node_name, current_sink, master_name,
                        )
                    current_id = line.split('#', 1)[1].strip()
                    current_sink = None
                    current_node = None
                elif line.startswith('Sink:'):
                    parts = line.split(':', 1)[1].strip().split()
                    if parts:
                        current_sink = parts[0]
                elif 'node.name' in line and '=' in line:
                    current_node = line.split('=', 1)[1].strip().strip('"')

            # Handle last entry
            if current_id and current_node == output_node_name and current_sink != master_id:
                self._move_sink_input(current_id, master_name, master_id)
                logger.debug(
                    "Corrected remap output stream %r from sink #%s to %s",
                    output_node_name, current_sink, master_name,
                )
        except Exception as e:
            logger.debug("_fix_remap_output_routing error: %s", e)

    def _unload_mono_remap_sink(self, mono_sink_name: str) -> bool:
        """Unload one SinkSwitch mono remap module by sink name."""
        for mod in self._list_sinkswitch_remap_modules():
            if mod.get('sink_name') != mono_sink_name:
                continue
            module_id = mod.get('id', '')
            if not module_id:
                return False
            try:
                unload_res = subprocess.run(
                    host_cmd(['pactl', 'unload-module', module_id]),
                    capture_output=True,
                    text=True,
                    **SUBPROCESS_TEXT_KW,
                    timeout=5,
                    check=False,
                )
            except Exception as e:
                logger.warning(
                    "Failed to unload stale mono remap sink %s: %s",
                    mono_sink_name,
                    e,
                )
                return False
            if unload_res.returncode == 0:
                logger.info("Unloaded stale Bluetooth mono remap sink %s", mono_sink_name)
                return True
            err = (unload_res.stderr or unload_res.stdout or '').strip()
            logger.warning(
                "Failed to unload stale mono remap sink %s: %s",
                mono_sink_name,
                err or f"exit {unload_res.returncode}",
            )
            return False
        return False

    def _ensure_mono_remap_sink(self, master_sink: str) -> str:
        """Create/reuse a mono remap sink for master_sink; return sink to route to."""
        master_sink = self._normalize_master_sink_name(master_sink)

        # Resolve the actual PipeWire sink name for master= so module-remap-sink
        # wires its output to the correct device.  Without this, if the configured
        # name differs from the live name (profile suffix, fuzzy match only), pactl
        # silently loads the module with no master and PipeWire falls back to the
        # system default sink (typically analog speakers).
        resolved_master = self._resolve_sink(master_sink, allow_managed_remaps=False)
        if not resolved_master:
            logger.warning("Cannot create mono remap sink: master %r not found", master_sink)
            return master_sink
        actual_master_id, actual_master_name = resolved_master
        is_bluetooth_master = 'bluez' in actual_master_name.lower()
        previous_master_id = self._mono_master_sink_id_cache.get(master_sink)

        if is_bluetooth_master and previous_master_id and previous_master_id != actual_master_id:
            stale_cached = self._mono_sink_cache.pop(master_sink, None)
            if stale_cached:
                self._unload_mono_remap_sink(stale_cached)
            stale_existing = self._find_existing_mono_remap_sink(master_sink)
            if stale_existing:
                self._unload_mono_remap_sink(stale_existing)
            logger.info(
                "Bluetooth sink instance changed for %s (%s -> %s); forcing mono remap rebuild",
                master_sink,
                previous_master_id,
                actual_master_id,
            )

        cached = self._mono_sink_cache.get(master_sink)
        if cached and self._resolve_sink(cached):
            self._mono_master_sink_id_cache[master_sink] = actual_master_id
            self._fix_remap_output_routing(cached, actual_master_name)
            return cached

        existing = self._find_existing_mono_remap_sink(master_sink)
        if existing and self._resolve_sink(existing):
            self._mono_sink_cache[master_sink] = existing
            self._mono_master_sink_id_cache[master_sink] = actual_master_id
            self._fix_remap_output_routing(existing, actual_master_name)
            return existing

        sanitized = re.sub(r'[^a-zA-Z0-9_.-]', '_', master_sink)
        mono_sink_name = f"{self.MONO_REMAP_PREFIX}{sanitized}"[:120]
        sink_desc = f"SinkSwitch_Mono_for_{sanitized}"[:160]

        try:
            result = subprocess.run(
                host_cmd([
                    'pactl',
                    'load-module',
                    'module-remap-sink',
                    f'sink_name={mono_sink_name}',
                    f'master={actual_master_name}',
                    f'sink_properties=device.description={sink_desc}',
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
        except Exception as e:
            logger.warning(
                "Failed to create mono remap sink for %s: %s",
                master_sink,
                e,
            )
            return master_sink

        if result.returncode != 0:
            err = (result.stderr or result.stdout or '').strip()
            logger.warning(
                "Failed to create mono remap sink for %s: %s",
                master_sink,
                err or f"exit {result.returncode}",
            )
            return master_sink

        if self._resolve_sink(mono_sink_name):
            self._mono_sink_cache[master_sink] = mono_sink_name
            self._mono_master_sink_id_cache[master_sink] = actual_master_id
            self._fix_remap_output_routing(mono_sink_name, actual_master_name)
            return mono_sink_name
        return master_sink

    def _repair_remap_output_after_move(self, mono_sink_name: str) -> None:
        """Repair remap output routing after app streams are moved.

        The remap output stream (node.name=output.<mono_sink_name>) is often
        created lazily only after the first sink-input is moved to the remap sink.
        If WirePlumber has stale routing state, that stream can appear on the
        wrong sink. Retry briefly so we can correct it once it exists.
        """
        for mod in self._list_sinkswitch_remap_modules():
            if mod.get('sink_name') != mono_sink_name:
                continue
            master_name = self._normalize_master_sink_name(mod.get('master', ''))
            if not master_name:
                return
            for _ in range(6):
                self._fix_remap_output_routing(mono_sink_name, master_name)
                # Exit early if output stream is already on the desired sink.
                output_node_name = f"output.{mono_sink_name}"
                resolved = self._resolve_sink(master_name, allow_managed_remaps=False)
                if not resolved:
                    return
                master_id, _ = resolved
                try:
                    si_res = subprocess.run(
                        host_cmd(['pactl', 'list', 'sink-inputs']),
                        capture_output=True,
                        text=True,
                        **SUBPROCESS_TEXT_KW,
                        timeout=5,
                        check=False,
                    )
                except Exception:
                    return
                if si_res.returncode != 0:
                    return

                current_sink = None
                current_node = None
                found_output = False
                for raw_line in si_res.stdout.split('\n'):
                    line = raw_line.strip()
                    if line.startswith('Sink Input #'):
                        if current_node == output_node_name:
                            found_output = True
                            break
                        current_sink = None
                        current_node = None
                    elif line.startswith('Sink:'):
                        parts = line.split(':', 1)[1].strip().split()
                        if parts:
                            current_sink = parts[0]
                    elif 'node.name' in line and '=' in line:
                        current_node = line.split('=', 1)[1].strip().strip('"')
                if current_node == output_node_name:
                    found_output = True
                if found_output and current_sink == master_id:
                    return
                time.sleep(0.08)
            return

    def _get_effective_target_sink(self, sink_name: str) -> str:
        """Return sink name to route to, enabling mono for Bluetooth when configured."""
        if 'bluez' not in (sink_name or '').lower():
            return sink_name

        master_sink = self._normalize_master_sink_name(sink_name)

        # HFP/HSP (headset) Bluetooth sinks are inherently mono (16 kHz) SCO
        # transports. Wrapping them in a SinkSwitch mono remap is pointless and a
        # pactl load-module against a profile that is mid-switch can hang and
        # wedge the whole audio server, so never mono-remap a headset profile.
        if self._is_headset_profile_bluetooth_sink(master_sink):
            return sink_name

        if self.force_bluetooth_mono:
            mono_sink = self._ensure_mono_remap_sink(master_sink)
            self._required_mono_masters.add(master_sink)
            return mono_sink

        if not self.auto_mono_single_channel_bluetooth:
            return sink_name
        if not self._is_single_channel_bluetooth_sink(master_sink):
            return sink_name

        mono_sink = self._ensure_mono_remap_sink(master_sink)
        self._required_mono_masters.add(master_sink)
        return mono_sink

    def _is_headset_profile_bluetooth_sink(self, sink_name: str) -> bool:
        """Return True when a Bluetooth sink belongs to a card in the HFP/HSP headset profile."""
        try:
            if 'bluez' not in (sink_name or '').lower():
                return False
            parts = (sink_name or '').split('.')
            if len(parts) < 3:
                return False
            device_address = parts[1].replace('_', ':')
            return self.device_monitor.is_headset_profile(device_address)
        except Exception as e:
            logger.debug(f"Failed to check headset profile for {sink_name}: {e}")
            return False

    def cleanup_managed_sinks(self) -> None:
        """Public cleanup helper used when stopping the in-app monitor."""
        self._required_mono_masters = set()
        self._cleanup_sinkswitch_remaps(startup=True)
    
    def _ensure_a2dp_profile(self, sink_name: str, allow_soft_toggle: bool = False) -> bool:
        """Ensure Bluetooth device is using A2DP (high-fidelity) profile
        
        Args:
            sink_name: Bluetooth sink name (e.g., 'bluez_output.00_02_3C_AD_09_85.1')
            allow_soft_toggle: Permit the destructive off→a2dp transport toggle.
                Routing hot paths leave this False so they never disrupt the audio
                server; the low-frequency profile monitor handles recovery.
        
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
            return self.device_monitor.prefer_a2dp_profile(
                device_address, allow_soft_toggle=allow_soft_toggle
            )
        
        except Exception as e:
            logger.debug(f"Failed to ensure A2DP profile: {e}")
            return False

    def _generate_fallback_rules(self) -> List[Dict]:
        """Auto-generate routing rules from connected devices when none are configured."""
        try:
            from intelligent_audio_router import IntelligentAudioRouter
            config = IntelligentAudioRouter().generate_routing_config()
            rules = config.get('routing_rules', [])
            if rules:
                logger.info(
                    "No routing rules configured; using %d auto-generated rule(s)",
                    len(rules),
                )
            return rules
        except Exception as e:
            logger.debug("Failed to generate fallback rules: %s", e)
            return []

    def apply_rules(self, rules: List[Dict]) -> List[Dict]:
        """Apply routing rules to audio streams
        
        Args:
            rules: List of routing rules
            
        Returns:
            List of result dictionaries with success status and messages
        """
        if not rules:
            rules = self._generate_fallback_rules()

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
        applications = rule.get('applications', [])
        keywords = rule.get('application_keywords', [])
        
        # Build list of all target devices to try
        all_targets = [target_device]
        if target_variants:
            all_targets = target_variants
        all_targets = self._prioritize_target_sinks(target_device, all_targets)

        # Try to restore A2DP before selecting a sink variant, so we avoid
        # routing streams into non-playback Bluetooth profiles.
        first_bluetooth_target = next(
            (target for target in all_targets if 'bluez' in (target or '').lower()),
            None,
        )
        if first_bluetooth_target:
            self._ensure_a2dp_profile(first_bluetooth_target)
            all_targets = self._prioritize_target_sinks(target_device, all_targets)
        
        try:
            if not all_targets:
                return {
                    'rule_name': rule_name,
                    'success': False,
                    'message': 'No target device configured for this rule',
                }

            # Pick the best currently reachable target for status messaging,
            # but do not abort routing if resolution is temporarily stale.
            connected_target = all_targets[0]
            sink_states = self._get_sink_states()
            target_probe: List[Tuple[str, str, str, str]] = []
            for target in all_targets:
                resolved = self._resolve_sink(target, allow_managed_remaps=False)
                if not resolved:
                    target_probe.append((target, 'missing', '-', '-'))
                    continue
                _, sink_name = resolved
                sink_state = sink_states.get(sink_name, 'UNKNOWN').upper()
                target_probe.append((target, 'resolved', sink_name, sink_state))
                if sink_state == 'UNAVAILABLE':
                    continue
                connected_target = target
                break
            logger.debug(
                "Rule %r target resolution: preferred=%r bt_target=%r probes=%s connected_choice=%r",
                rule_name,
                target_device,
                first_bluetooth_target,
                target_probe,
                connected_target,
            )
            
            # Route matching applications to target device (try all variants)
            effective_targets: List[str] = []
            for target in all_targets:
                effective_targets.append(self._get_effective_target_sink(target))
            routed = self._route_applications(
                applications,
                keywords,
                effective_targets
            )
            logger.debug(
                "Rule %r route result: routed=%s effective_targets=%s apps=%s keywords=%s",
                rule_name,
                routed,
                effective_targets,
                applications,
                keywords,
            )

            # Keep profile maintenance off the routing hot path so stream moves
            # happen first for newly created browser/media sink-inputs.
            if 'bluez' in connected_target:
                self._ensure_a2dp_profile(connected_target)
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
            matched_apps = 0
            for app_name in running_apps:
                if self._matches_rule(app_name, applications, keywords):
                    matched_apps += 1
                    logger.debug(f"App '{app_name}' matches rule, routing to {target_devices[0]}")
                    # Try each target device variant until one succeeds
                    for target_device in target_devices:
                        if self._route_stream(app_name, target_device):
                            routed_count += 1
                            break
                else:
                    logger.debug(f"App '{app_name}' does NOT match rule")

            logger.debug(
                "Route pass summary: running_apps=%s matched_apps=%s routed=%s targets=%s",
                len(running_apps),
                matched_apps,
                routed_count,
                target_devices,
            )
            
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
        """Return sink-input rows with index/sink plus key stream properties."""
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
                elif 'node.name' in line and '=' in line:
                    node_name = line.split('=', 1)[1].strip().strip('"')
                    current['node_name'] = node_name
                elif 'media.name' in line and '=' in line:
                    media_name = line.split('=', 1)[1].strip().strip('"')
                    current['media_name'] = media_name

            if current and current.get('index'):
                streams.append(current)
            return streams
        except Exception as e:
            logger.debug(f"Failed to read sink inputs: {e}")
            return []

    def _is_internal_remap_sink_input(self, stream: Dict[str, str]) -> bool:
        """Return True for SinkSwitch-managed internal mono remap output streams."""
        node_name = (stream.get('node_name') or '').strip()
        media_name = (stream.get('media_name') or '').strip()
        app_name = (stream.get('application_name') or '').strip()

        if node_name.startswith(f"output.{self.MONO_REMAP_PREFIX}"):
            return True
        if node_name.startswith(self.MONO_REMAP_PREFIX):
            return True
        if 'sinkswitch_mono' in node_name.lower():
            return True

        lowered_media = media_name.lower()
        if lowered_media.startswith('sinkswitch_mono_for_') and ' output' in lowered_media:
            return True

        # Some hosts expose the remap output without app name; keep this as a
        # conservative guard against fallback moving internal streams.
        if 'sinkswitch_mono' in app_name.lower():
            return True
        return False

    def _move_sink_input(self, sink_input_id: str, target_sink_name: str, target_sink_id: str) -> bool:
        """Move one sink-input, trying sink name first then numeric id."""
        move_res = None
        for target in (target_sink_name, target_sink_id):
            try:
                move_res = subprocess.run(
                    host_cmd(['pactl', 'move-sink-input', sink_input_id, target]),
                    capture_output=True,
                    text=True,
                    **SUBPROCESS_TEXT_KW,
                    timeout=5,
                    check=False,
                )
            except Exception as e:
                logger.warning(
                    "move-sink-input failed for %s -> %s / #%s: %s",
                    sink_input_id,
                    target_sink_name,
                    target_sink_id,
                    e,
                )
                return False
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
        streams = self._get_sink_inputs()
        moved = 0

        for stream in streams:
            app_name = stream.get('application_name', '')
            if self._is_internal_remap_sink_input(stream):
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
    
    def _resolve_sink(
        self,
        device_name: str,
        allow_managed_remaps: bool = True,
    ) -> Optional[Tuple[str, str]]:
        """Return (sink_index, sink_name); BT ids match by MAC if PipeWire renumbered suffix."""
        try:
            requested = (device_name or '').strip()
            requested_lower = requested.lower()
            # Only do Bluetooth fuzzy matching for physical bluez sink ids.
            # Managed mono remap names must resolve exactly.
            use_bluetooth_fuzzy = (
                requested_lower.startswith('bluez_output.')
                and not requested.startswith(self.MONO_REMAP_PREFIX)
            )
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
                    if (not allow_managed_remaps) and name_value.startswith(self.MONO_REMAP_PREFIX):
                        continue
                    if name_value == requested:
                        return (current_sink_id, name_value)
                    if use_bluetooth_fuzzy and name_value.lower().startswith('bluez_output.'):
                        if (not allow_managed_remaps) and name_value.startswith(self.MONO_REMAP_PREFIX):
                            continue
                        parts = requested.split('.')
                        if len(parts) >= 2:
                            mac_address = parts[1]
                            if mac_address in name_value:
                                logger.debug(
                                    f"Fuzzy matched Bluetooth sink '{requested}' to '{name_value}' (sink #{current_sink_id})"
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
            matched_inputs = 0
            already_on_target = 0
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
                    matched_inputs += 1
                    if current_sink_num is None or current_sink_num != target_sink_id:
                        to_move.append((current_sink_input, current_sink_num))
                    else:
                        already_on_target += 1
            
            if not to_move:
                logger.debug(
                    "No sink-input moves for app %r -> %s (#%s); matched_inputs=%s already_on_target=%s",
                    app_name,
                    target_sink_name,
                    target_sink_id,
                    matched_inputs,
                    already_on_target,
                )
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

            # When routing to a mono remap sink, also correct the remap's own
            # output stream target after app streams are moved (lazy creation).
            if any_ok and target_sink_name.startswith(self.MONO_REMAP_PREFIX):
                self._repair_remap_output_after_move(target_sink_name)
            return any_ok
        except Exception as e:
            logger.debug(f"PulseAudio routing failed: {e}")
            return False
