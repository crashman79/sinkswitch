#!/usr/bin/env python3
"""
Audio routing engine - applies routing rules to audio streams
"""

import subprocess
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from device_monitor import DeviceMonitor
from host_command import host_cmd, SUBPROCESS_TEXT_KW
from routing_latency_log import log_latency_event

logger = logging.getLogger(__name__)


class AudioRouterEngine:
    """Engine for applying audio routing rules"""
    # A single, short, fixed-name sink that SinkSwitch creates to redirect
    # Bluetooth audio. Whether it is a mono remap (single-earbud) or a stereo
    # passthrough is a (re)creation parameter -- there is never more than one of
    # these at a time. The bare prefix identifies any SinkSwitch-managed module
    # (old ``sinkswitch_mono.*`` vestiges included) for listing/cleanup.
    MANAGED_SINK_NAME = 'sinkswitch_bt'
    MANAGED_PREFIX = 'sinkswitch_'

    # BlueZ/pipewire expose a Bluetooth sink node before the transport is
    # actually usable.  These constants keep routing out of that window.
    BT_SETTLE_SEC = 2.5
    BT_BACKOFF_INITIAL_SEC = 1.0
    BT_BACKOFF_MAX_SEC = 10.0
    BT_TRANSPORT_FAILED_SEC = 15.0
    BT_CARD_INFO_TTL_SEC = 1.5

    _BT_REASON_LABELS = {
        'sink-missing': 'sink not present yet',
        'unavailable': 'sink unavailable',
        'settling': 'transport still settling',
        'profile-empty': 'A2DP profile not active yet',
        'profile-mismatch': 'card/sink profile mismatch',
        'card-off': 'card profile is off',
        'card-profile-unknown': 'card profile unknown',
    }

    def __init__(
        self,
        auto_mono_single_channel_bluetooth: bool = True,
        force_bluetooth_mono: bool = False,
    ):
        self.device_monitor = DeviceMonitor()
        self.auto_mono_single_channel_bluetooth = auto_mono_single_channel_bluetooth
        self.force_bluetooth_mono = force_bluetooth_mono
        # Exactly one SinkSwitch-created sink. ``_managed_sink`` tracks its
        # current master device and mono flag so we can reuse it or recreate it
        # (never duplicate it) when the target or mono requirement changes.
        self._managed_sink: Optional[Dict[str, Any]] = None
        self._managed_sink_required: bool = False
        # Bluetooth readiness / debounce / backoff state.
        self._bt_observed_master_ids: Dict[str, str] = {}
        self._bt_settle_until: Dict[str, float] = {}
        self._bt_backoff_sec: Dict[str, float] = {}
        self._bt_backoff_until: Dict[str, float] = {}
        self._bt_not_ready_since: Dict[str, float] = {}
        self._bt_state: Dict[str, Tuple[str, str]] = {}
        self._bt_card_info_cache: Dict[str, Tuple[float, Optional[Dict]]] = {}
        self._rate_limited_logs: Dict[str, float] = {}
        # Clean stale remap modules from earlier sessions.
        self._cleanup_sinkswitch_remaps(startup=True)

    @staticmethod
    def _bt_mac_from_sink(sink_name: str) -> Optional[str]:
        """Extract the Bluetooth address from a bluez_output/bluez_card id."""
        parts = (sink_name or '').split('.')
        if len(parts) < 3 or 'bluez' not in parts[0].lower():
            return None
        return parts[1].replace('_', ':')

    def _bt_reason_label(self, reason: str) -> str:
        return self._BT_REASON_LABELS.get(reason, reason or 'not ready')

    def _log_rate_limited(
        self,
        key: str,
        message: str,
        *args: Any,
        level: int = logging.WARNING,
        interval: float = 60.0,
    ) -> None:
        """Log a repeated condition once per interval, debug afterwards."""
        now = time.monotonic()
        last = self._rate_limited_logs.get(key)
        if last is not None and (now - last) < interval:
            logger.debug(message, *args)
            return
        self._rate_limited_logs[key] = now
        logger.log(level, message, *args)

    def _probe_bt_sink(self, sink_name: str) -> Optional[Dict[str, Any]]:
        """Read the live sink block for a Bluetooth sink.

        Returns None when the sink block cannot be read so callers can fail open
        on non-BlueZ/PulseAudio setups instead of blocking all routing.
        """
        try:
            result = subprocess.run(
                host_cmd(['pactl', 'list', 'sinks']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                return None

            current: Optional[Dict[str, Any]] = None
            for raw_line in result.stdout.split('\n'):
                line = raw_line.strip()
                if line.startswith('Sink #'):
                    if current and current.get('name') == sink_name:
                        return current
                    current = {
                        'id': line.split('#', 1)[1].strip(),
                        'name': '',
                        'state': '',
                        'profile': None,
                        'connection': None,
                    }
                    continue
                if current is None:
                    continue
                if line.startswith('Name:'):
                    current['name'] = line.split(':', 1)[1].strip()
                elif line.startswith('State:'):
                    current['state'] = line.split(':', 1)[1].strip()
                elif line.startswith('api.bluez5.profile') and '=' in line:
                    current['profile'] = line.split('=', 1)[1].strip().strip('"')
                elif line.startswith('api.bluez5.connection') and '=' in line:
                    current['connection'] = line.split('=', 1)[1].strip().strip('"')

            if current and current.get('name') == sink_name:
                return current
            return None
        except Exception as e:
            logger.debug("Failed to probe Bluetooth sink %s: %s", sink_name, e)
            return None

    def _get_bt_card_info_cached(self, device_address: str) -> Optional[Dict]:
        """Return Bluetooth card info with a short TTL to avoid per-pass churn."""
        now = time.monotonic()
        cached = self._bt_card_info_cache.get(device_address)
        if cached and (now - cached[0]) < self.BT_CARD_INFO_TTL_SEC:
            return cached[1]
        try:
            info = self.device_monitor.get_bluetooth_card_info(device_address)
        except Exception as e:
            logger.debug("Failed to read Bluetooth card info for %s: %s", device_address, e)
            info = None
        self._bt_card_info_cache[device_address] = (now, info)
        return info

    def _evaluate_bt_readiness(self, master_sink: str) -> Tuple[bool, str]:
        """Return (ready, reason) for a Bluetooth master sink.

        A sink node existing in ``pactl`` does not mean the A2DP transport is
        usable.  If we pin a remap or move a stream while BlueZ is still
        negotiating, PipeWire is forced to Acquire a transport that is not
        ready yet -- exactly the window that exposes the BlueZ 5.87 SEP-cache
        failure.  Require an active matching profile and let node-instance
        churn settle before touching the device.
        """
        if 'bluez' not in (master_sink or '').lower():
            return True, 'not-bluetooth'

        resolved = self._resolve_sink(master_sink, allow_managed_remaps=False)
        if not resolved:
            return False, 'sink-missing'
        sink_id, sink_name = resolved

        now = time.monotonic()
        observed_id = self._bt_observed_master_ids.get(master_sink)
        if observed_id is None:
            # First sighting in this process: do not delay startup routing.
            self._bt_observed_master_ids[master_sink] = sink_id
        elif observed_id != sink_id:
            # pipewire/BlueZ recreated the node during profile negotiation.
            # Coalesce the churn before rebuilding remaps or moving streams.
            self._bt_observed_master_ids[master_sink] = sink_id
            self._bt_settle_until[master_sink] = now + self.BT_SETTLE_SEC
            self._bt_backoff_sec.pop(master_sink, None)
            self._bt_backoff_until.pop(master_sink, None)
            logger.info(
                "Bluetooth sink instance changed for %s (%s -> %s); "
                "waiting %.1fs for the transport to settle",
                master_sink,
                observed_id,
                sink_id,
                self.BT_SETTLE_SEC,
            )

        if now < self._bt_settle_until.get(master_sink, 0.0):
            return False, 'settling'

        probe = self._probe_bt_sink(sink_name)
        if probe:
            state = (probe.get('state') or '').upper()
            if state == 'UNAVAILABLE':
                return False, 'unavailable'

            profile = probe.get('profile')
            if profile is not None:
                profile = profile.strip().lower()
                if not profile:
                    # BlueZ created the node but has not attached an A2DP
                    # transport yet; this is the half-connected state.
                    return False, 'profile-empty'
                if not (profile.startswith('a2dp') or profile.startswith('headset')):
                    return False, f'profile:{profile}'

            connection = (probe.get('connection') or '').strip().lower()
            if connection and connection != 'connected':
                return False, f'connection:{connection}'

        mac = self._bt_mac_from_sink(sink_name)
        card = self._get_bt_card_info_cached(mac) if mac else None
        if card:
            active = (card.get('active_profile') or '').strip().lower()
            if not active:
                return False, 'card-profile-unknown'
            if active == 'off':
                return False, 'card-off'
            sink_profile = probe.get('profile') if probe else None
            if sink_profile is not None:
                sink_profile = sink_profile.strip().lower()
                if active.startswith('a2dp') and not sink_profile.startswith('a2dp'):
                    return False, 'profile-mismatch'
                if active.startswith('headset') and not sink_profile.startswith('headset'):
                    return False, 'profile-mismatch'

        return True, 'ready'

    def _log_bt_state(self, master_sink: str, state: str, reason: str) -> None:
        """Log one line per Bluetooth state transition, never per routing pass."""
        state_key = (state, reason if state != 'ready' else 'ready')
        if self._bt_state.get(master_sink) == state_key:
            return
        self._bt_state[master_sink] = state_key

        if state == 'ready':
            logger.info("Bluetooth target %s is ready; resuming routing", master_sink)
        elif state == 'failed':
            logger.warning(
                "Bluetooth target %s is connected but not routable (%s) after %.0fs; "
                "waiting for the transport to recover before retrying",
                master_sink,
                self._bt_reason_label(reason),
                self.BT_TRANSPORT_FAILED_SEC,
            )
        else:
            now = time.monotonic()
            retry = max(0.1, self._bt_backoff_until.get(master_sink, now) - now)
            logger.info(
                "Bluetooth target %s not ready (%s); deferring routing for %.1fs",
                master_sink,
                self._bt_reason_label(reason),
                retry,
            )

    def _note_bt_not_ready(self, master_sink: str, reason: str) -> float:
        """Record a not-ready result and return the retry delay."""
        now = time.monotonic()
        existing_until = self._bt_backoff_until.get(master_sink)
        if existing_until is not None and now < existing_until:
            # A rule and the default-fallback check can both see the same
            # target in one pass; never grow the backoff twice for that.
            retry = max(0.1, existing_until - now)
        elif reason == 'settling':
            retry = max(0.1, self._bt_settle_until.get(master_sink, now) - now)
            self._bt_backoff_until[master_sink] = now + retry
        else:
            previous = self._bt_backoff_sec.get(master_sink, 0.0)
            retry = min(
                max(self.BT_BACKOFF_INITIAL_SEC, previous * 2.0),
                self.BT_BACKOFF_MAX_SEC,
            )
            self._bt_backoff_sec[master_sink] = retry
            self._bt_backoff_until[master_sink] = now + retry

        since = self._bt_not_ready_since.setdefault(master_sink, now)
        failed = (
            reason != 'settling'
            and (now - since) >= self.BT_TRANSPORT_FAILED_SEC
        )
        self._log_bt_state(master_sink, 'failed' if failed else 'waiting', reason)
        return retry

    def _note_bt_ready(self, master_sink: str) -> None:
        self._bt_backoff_sec.pop(master_sink, None)
        self._bt_backoff_until.pop(master_sink, None)
        self._bt_not_ready_since.pop(master_sink, None)
        self._log_bt_state(master_sink, 'ready', 'ready')

    def _bt_retry_after(self, targets: List[str]) -> float:
        """Shortest backoff remaining across the given deferred targets."""
        now = time.monotonic()
        waits = []
        for target in targets:
            master = self._normalize_master_sink_name(target)
            until = self._bt_backoff_until.get(master)
            if until is not None:
                waits.append(max(0.05, until - now))
        return min(waits) if waits else 0.25


    def _normalize_master_sink_name(self, sink_name: str) -> str:
        """Unwrap a SinkSwitch managed sink name to its physical master sink.

        The managed sink has a fixed name (``sinkswitch_bt``) that does not encode
        the device, so the underlying master is tracked in ``self._managed_sink``.
        """
        out = sink_name or ''
        if out == self.MANAGED_SINK_NAME and self._managed_sink:
            return self._managed_sink.get('master', out)
        while out.startswith(self.MANAGED_PREFIX):
            out = out[len(self.MANAGED_PREFIX):]
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
                if not sink_name.startswith(self.MANAGED_PREFIX):
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
            required = self._managed_sink_required
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
                if self._managed_sink and self._managed_sink.get('master') == master:
                    self._managed_sink = None

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

    def _unload_managed_sink_by_name(self, sink_name: str) -> bool:
        """Unload a SinkSwitch managed module by sink name."""
        for mod in self._list_sinkswitch_remap_modules():
            if mod.get('sink_name') != sink_name:
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
                    "Failed to unload managed sink %s: %s",
                    sink_name,
                    e,
                )
                return False
            if unload_res.returncode == 0:
                if self._managed_sink and self._managed_sink.get('master_name'):
                    self._managed_sink = None
                logger.info("Unloaded managed sink %s", sink_name)
                return True
            err = (unload_res.stderr or unload_res.stdout or '').strip()
            logger.warning(
                "Failed to unload managed sink %s: %s",
                sink_name,
                err or f"exit {unload_res.returncode}",
            )
            return False
        return False

    def _ensure_managed_sink(self, master_sink: str, mono: bool) -> str:
        """Create/reuse the single SinkSwitch managed sink for ``master_sink``.

        There is exactly one SinkSwitch-created sink (``MANAGED_SINK_NAME``).  It
        is (re)created as a mono remap when ``mono`` is True, otherwise as a
        stereo passthrough remap.  If the existing managed sink already matches
        the requested master and mono flag it is reused; otherwise the single
        existing module is unloaded first so we never end up with two sinks.
        Returns the sink name to route to (the managed sink, or ``master_sink`` on
        failure so routing degrades gracefully to the real device).
        """
        master_sink = self._normalize_master_sink_name(master_sink)

        # Resolve the actual PipeWire sink name for master= so module-remap-sink
        # wires its output to the correct device.  Without this, if the configured
        # name differs from the live name (profile suffix, fuzzy match only), pactl
        # silently loads the module with no master and PipeWire falls back to the
        # system default sink (typically analog speakers).
        resolved_master = self._resolve_sink(master_sink, allow_managed_remaps=False)
        if not resolved_master:
            self._log_rate_limited(
                f"managed-master-missing:{master_sink}",
                "Cannot create managed sink: master %r not found",
                master_sink,
            )
            return master_sink
        actual_master_id, actual_master_name = resolved_master

        # Reuse the existing managed sink when it already matches the request.
        if self._managed_sink:
            cur = self._managed_sink
            if (
                cur.get('master_name') == actual_master_name
                and cur.get('mono') == mono
                and self._resolve_sink(self.MANAGED_SINK_NAME)
            ):
                self._fix_remap_output_routing(self.MANAGED_SINK_NAME, actual_master_name)
                return self.MANAGED_SINK_NAME

        # Master or mono flag changed (or no managed sink yet): unload the single
        # existing module before (re)creating so there is never more than one.
        for mod in self._list_sinkswitch_remap_modules():
            if mod.get('sink_name') == self.MANAGED_SINK_NAME:
                self._unload_managed_sink_by_name(self.MANAGED_SINK_NAME)

        sink_desc = f"SinkSwitch_{'Mono' if mono else 'Stereo'}_BT"
        args = [
            'pactl',
            'load-module',
            'module-remap-sink',
            f'sink_name={self.MANAGED_SINK_NAME}',
            f'master={actual_master_name}',
            f'sink_properties=device.description={sink_desc}',
        ]
        if mono:
            args += ['channels=1', 'channel_map=mono', 'remix=yes']
        else:
            args += ['channels=2', 'channel_map=front-left,front-right', 'remix=no']

        try:
            result = subprocess.run(
                host_cmd(args),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5,
                check=False,
            )
        except Exception as e:
            logger.warning(
                "Failed to create managed sink for %s: %s",
                master_sink,
                e,
            )
            return master_sink

        if result.returncode != 0:
            err = (result.stderr or result.stdout or '').strip()
            logger.warning(
                "Failed to create managed sink for %s: %s",
                master_sink,
                err or f"exit {result.returncode}",
            )
            return master_sink

        if self._resolve_sink(self.MANAGED_SINK_NAME):
            self._managed_sink = {
                'master': master_sink,
                'master_id': actual_master_id,
                'master_name': actual_master_name,
                'mono': mono,
            }
            self._fix_remap_output_routing(self.MANAGED_SINK_NAME, actual_master_name)
            return self.MANAGED_SINK_NAME
        return master_sink

    def get_managed_sink_state(self) -> Optional[Dict[str, Any]]:
        """Return the current managed sink descriptor, or None if none exists.

        Used by the GUI to label streams routed through the managed sink and to
        resolve the real (physical) device they land on.
        """
        if not self._managed_sink:
            return None
        if not self._resolve_sink(self.MANAGED_SINK_NAME):
            self._managed_sink = None
            return None
        return dict(self._managed_sink)

    def get_bluetooth_volume_target(self) -> Optional[str]:
        """Return the sink name whose volume the Bluetooth volume shortcuts adjust.

        Prefers the live Bluetooth master behind the managed sink; falls back to
        the first connected Bluetooth sink reported by the device monitor.
        """
        state = self.get_managed_sink_state()
        if state and state.get('master_name'):
            return state['master_name']
        try:
            for d in self.device_monitor.get_devices():
                did = d.get('id', '')
                if 'bluez' in did.lower() and d.get('connected'):
                    return did
        except Exception:
            pass
        return None

    def adjust_bluetooth_volume(self, delta: str) -> bool:
        """Adjust the Bluetooth sink volume by a relative amount (e.g. '+5%').

        Returns False if there is no Bluetooth target or the pactl call fails.
        """
        target = self.get_bluetooth_volume_target()
        if not target:
            return False
        try:
            res = subprocess.run(
                host_cmd(['pactl', 'set-sink-volume', target, delta]),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5,
                check=False,
            )
            if res.returncode != 0:
                logger.warning(
                    "Failed to adjust Bluetooth volume for %s (%s): %s",
                    target, delta, (res.stderr or res.stdout or '').strip(),
                )
                return False
            return True
        except Exception as e:
            logger.warning("Failed to adjust Bluetooth volume: %s", e)
            return False

    def toggle_bluetooth_mute(self) -> bool:
        """Toggle the Bluetooth sink mute state."""
        target = self.get_bluetooth_volume_target()
        if not target:
            return False
        try:
            res = subprocess.run(
                host_cmd(['pactl', 'set-sink-mute', target, 'toggle']),
                capture_output=True,
                text=True,
                **SUBPROCESS_TEXT_KW,
                timeout=5,
                check=False,
            )
            return res.returncode == 0
        except Exception as e:
            logger.warning("Failed to toggle Bluetooth mute: %s", e)
            return False

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

    def _get_effective_target_sink(self, sink_name: str) -> Optional[str]:
        """Return sink name to route to, or None if a Bluetooth target is not ready."""
        if 'bluez' not in (sink_name or '').lower():
            return sink_name

        master_sink = self._normalize_master_sink_name(sink_name)

        # HFP/HSP (headset) Bluetooth sinks are inherently mono (16 kHz) SCO
        # transports. Wrapping them in a SinkSwitch mono remap is pointless and a
        # pactl load-module against a profile that is mid-switch can hang and
        # wedge the whole audio server, so never mono-remap a headset profile.
        # HFP is a legitimate active profile, so it needs no A2DP readiness check.
        if self._is_headset_profile_bluetooth_sink(master_sink):
            self._note_bt_ready(master_sink)
            return sink_name

        ready, reason = self._evaluate_bt_readiness(master_sink)
        if not ready:
            retry = self._note_bt_not_ready(master_sink, reason)
            logger.debug(
                "Deferring Bluetooth target %s (%s); retry in %.1fs",
                master_sink,
                reason,
                retry,
            )
            return None

        self._note_bt_ready(master_sink)

        # Decide whether the single managed sink should be mono or stereo.
        if self.force_bluetooth_mono:
            mono = True
        elif not self.auto_mono_single_channel_bluetooth:
            mono = False
        elif self._is_single_channel_bluetooth_sink(master_sink):
            mono = True
        else:
            mono = False

        managed = self._ensure_managed_sink(master_sink, mono)
        self._managed_sink_required = True
        return managed

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
        self._managed_sink_required = False
        self._cleanup_sinkswitch_remaps(startup=True)
    
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
        log_latency_event(f"apply_start rules={len(rules) if rules else 'fallback'}")
        if not rules:
            rules = self._generate_fallback_rules()

        _start = time.time()
        results = []
        self._managed_sink_required = False
        
        for rule in rules:
            result = self._apply_rule(rule)
            results.append(result)

        # Also enforce fallback behavior for streams that do not match any rule.
        results.append(self._route_unmatched_streams_to_default(rules))
        self._cleanup_sinkswitch_remaps(startup=False)

        _moved = sum(int(r.get('routed_count', 0)) for r in results)
        log_latency_event(
            f"apply_done rules={len(rules)} moved={_moved} elapsed_ms={int((time.time() - _start) * 1000)}"
        )

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

        try:
            if not all_targets:
                return {
                    'rule_name': rule_name,
                    'success': False,
                    'message': 'No target device configured for this rule',
                }

            # Route only to targets that exist and whose Bluetooth transport is
            # actually ready.  A node that exists but has no active A2DP profile
            # is not routable yet; a target that is gone entirely cannot be used
            # at all.  Both are candidates for the rule's default fallback.
            effective_targets: List[str] = []
            ready_targets: List[str] = []
            deferred_targets: List[str] = []
            unavailable_targets: List[str] = []
            for target in all_targets:
                effective = self._get_effective_target_sink(target)
                if not effective:
                    deferred_targets.append(target)
                    continue
                if not self._resolve_sink(effective):
                    unavailable_targets.append(target)
                    continue
                ready_targets.append(target)
                if effective not in effective_targets:
                    effective_targets.append(effective)

            logger.debug(
                "Rule %r target resolution: preferred=%r ready=%s deferred=%s unavailable=%s",
                rule_name,
                target_device,
                ready_targets,
                deferred_targets,
                unavailable_targets,
            )

            if not effective_targets:
                if deferred_targets:
                    reason = 'not ready'
                    for target in deferred_targets:
                        state = self._bt_state.get(self._normalize_master_sink_name(target))
                        if state:
                            reason = state[1]
                            break
                    waiting_message = (
                        f"Waiting for Bluetooth transport "
                        f"({self._bt_reason_label(reason)})"
                    )
                    retry_after = self._bt_retry_after(deferred_targets)
                else:
                    waiting_message = (
                        "Target device not available: "
                        + ", ".join(str(t) for t in unavailable_targets)
                    )
                    retry_after = None

                # Honour the rule's fallback setting instead of leaving matched
                # apps on whatever device they happen to be using.
                if rule.get('enable_default_fallback', True):
                    (
                        fallback_sink,
                        _fallback_index,
                        fallback_retry,
                        fallback_reason,
                    ) = self._resolve_default_routing_sink()
                    if fallback_sink:
                        routed = self._route_applications(
                            applications,
                            keywords,
                            [fallback_sink],
                        )
                        result = {
                            'rule_name': rule_name,
                            'success': True,
                            'routed_count': routed,
                            'fallback': True,
                            'message': (
                                f"Target unavailable; routed {routed} stream(s) "
                                f"to default output"
                            ),
                        }
                        if retry_after is not None:
                            result['retry_after'] = retry_after
                        return result

                    return {
                        'rule_name': rule_name,
                        'success': True,
                        'routed_count': 0,
                        'deferred': True,
                        'retry_after': (
                            fallback_retry if fallback_retry is not None else retry_after
                        ),
                        'message': f"{waiting_message}; {fallback_reason}",
                    }

                return {
                    'rule_name': rule_name,
                    'success': True,
                    'routed_count': 0,
                    'deferred': True,
                    'retry_after': retry_after,
                    'message': waiting_message,
                }

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

            connected_target = ready_targets[0] if ready_targets else all_targets[0]
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
        """Return True for SinkSwitch-managed internal remap output streams."""
        node_name = (stream.get('node_name') or '').strip()
        media_name = (stream.get('media_name') or '').strip()
        app_name = (stream.get('application_name') or '').strip()

        if node_name.startswith(f"output.{self.MANAGED_PREFIX}"):
            return True
        if node_name.startswith(self.MANAGED_PREFIX):
            return True
        if 'sinkswitch' in node_name.lower():
            return True

        lowered_media = media_name.lower()
        if 'sinkswitch' in lowered_media:
            return True

        # Some hosts expose the remap output without app name; keep this as a
        # conservative guard against fallback moving internal streams.
        if 'sinkswitch' in app_name.lower():
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

    def _resolve_default_routing_sink(
        self,
    ) -> Tuple[Optional[str], Optional[str], Optional[float], Optional[str]]:
        """Resolve the system default sink for routing.

        Returns ``(sink_name, sink_index, retry_after, reason)``.  When the
        default cannot be used right now, ``sink_name`` is ``None`` and
        ``reason`` explains why.  ``retry_after`` is set when waiting for a
        Bluetooth transport may make it usable.
        """
        default_sink_name = self.device_monitor.get_default_sink()
        if not default_sink_name:
            return None, None, None, 'No default sink available'

        resolved = self._resolve_sink(default_sink_name)
        if not resolved:
            return (
                None,
                None,
                None,
                f"Could not resolve default sink: {default_sink_name}",
            )

        default_sink_id, default_sink_name_resolved = resolved

        # Never move streams onto a Bluetooth default whose transport has not
        # opened yet; that would force an early Acquire and make the reconnect
        # race visible in the audio graph.
        if 'bluez' in default_sink_name_resolved.lower():
            master = self._normalize_master_sink_name(default_sink_name_resolved)
            if not self._is_headset_profile_bluetooth_sink(master):
                ready, reason = self._evaluate_bt_readiness(master)
                if not ready:
                    retry = self._note_bt_not_ready(master, reason)
                    return (
                        None,
                        None,
                        retry,
                        "Default Bluetooth output not ready "
                        f"({self._bt_reason_label(reason)})",
                    )
            self._note_bt_ready(master)

        return default_sink_name_resolved, default_sink_id, None, None

    def _route_unmatched_streams_to_default(self, rules: List[Dict]) -> Dict:
        """Move streams that match no rule to the current default sink."""
        (
            default_sink_name_resolved,
            default_sink_id,
            retry_after,
            reason,
        ) = self._resolve_default_routing_sink()

        if not default_sink_name_resolved:
            if retry_after is not None:
                return {
                    'rule_name': 'Default fallback',
                    'success': True,
                    'routed_count': 0,
                    'deferred': True,
                    'retry_after': retry_after,
                    'message': f"{reason}; leaving streams in place",
                }
            return {
                'rule_name': 'Default fallback',
                'success': False,
                'routed_count': 0,
                'message': reason or 'No default sink available',
            }

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
                and not requested.startswith(self.MANAGED_PREFIX)
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
                    if (not allow_managed_remaps) and name_value.startswith(self.MANAGED_PREFIX):
                        continue
                    if name_value == requested:
                        return (current_sink_id, name_value)
                    if use_bluetooth_fuzzy and name_value.lower().startswith('bluez_output.'):
                        if (not allow_managed_remaps) and name_value.startswith(self.MANAGED_PREFIX):
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
                self._log_rate_limited(
                    f"unresolved-target:{target_device}",
                    "Could not resolve sink for target device %r (not in pactl list sinks)",
                    target_device,
                )
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
            if any_ok and target_sink_name.startswith(self.MANAGED_PREFIX):
                self._repair_remap_output_after_move(target_sink_name)
            return any_ok
        except Exception as e:
            logger.debug(f"PulseAudio routing failed: {e}")
            return False
