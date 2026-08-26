# Checkpoint: HFP-stuck recovery + routing cycle fixes

Date: 2026-08-26 (updated with the Flatpak `bluetoothctl` root-cause fix)
Branch: `main` (uncommitted work from prior session + this checkpoint)

## Context

A recent change added **HFP-stuck Bluetooth recovery**: when a headset reconnects
stuck on HFP-only (no A2DP profile on the card), `DeviceMonitor` escalates from the
soft A2DP toggle to a full `bluetoothctl disconnect`/`connect` cycle so BlueZ
re-runs SDP/profile discovery (`src/device_monitor.py`).

Observed behavior: improved briefly, then got worse. The disconnect/reconnect
generates a storm of `pactl subscribe` events, each re-entering the monitor and
re-running routing logic. Only a cooldown prevented it from firing every event —
while the headset stayed HFP-stuck it would churn a reconnect roughly every
couple of minutes, dropping audio each cycle.

## Changes in this checkpoint

### 4. Root-cause fix: route `bluetoothctl` to the host in the Flatpak sandbox

While verifying the cycle fixes on a live HFP-stuck headset, the recovery still
failed to restore A2DP. The live (sandboxed) log showed `bt_hfp_recover_start`,
`bt_repair_start`, and `bt_hfp_recover_fail` all at the **same millisecond** —
the disconnect/reconnect was failing instantly, not slowly.

Root cause: inside the Flatpak sandbox there is no `bluetoothctl` binary
(`which bluetoothctl` → not found in `/app/bin:/usr/bin`). `host_cmd()` routed
`pw-cli` and mutating `pactl` through `flatpak-spawn --host`, but **not**
`bluetoothctl`. Every `subprocess.run(['bluetoothctl', ...])` in
`DeviceMonitor` (`devices`, `info`, `disconnect`, `connect`) raised
`FileNotFoundError` inside the sandbox, which `_repair_bluetooth_audio_for_mac`
caught and turned into an instant `False`. The entire Bluetooth recovery path
was silently dead under Flatpak.

Fix in `src/host_command.py`: add `bluetoothctl` to an `_ALWAYS_HOST_BINARIES`
set (with `pw-cli`) so it always runs via `flatpak-spawn --host`. Verified
inside the sandbox that a host-spawned `bluetoothctl info` talks to system
bluetoothd, and a full host-spawned disconnect/reconnect cycle restored A2DP:
the card went from `headset-head-unit` only to `Active Profile: a2dp-sink-aac`
with `a2dp-sink-{sbc,sbc_xq,aac,aptX}` available, sink back to stereo
`2ch 48000Hz`.

### 1. Persistent diagnostics log restored (`src/routing_latency_log.py` was orphaned)

The old `engine_2148.py`/`gui_2148.py` wrote `~/.config/sinkswitch/routing_latency.log`
but that logging was lost in the `src/` refactor. Re-wired it:

- `src/audio_router_engine.py` — `apply_rules()` logs `apply_start` / `apply_done`
  with rule count, moved count, and elapsed ms.
- `src/device_monitor.py` — logs `watch_trigger reason=event`, `bt_hfp_recover_start`
  / `fail` / `done`, `bt_auto_repair_start`, and `bt_repair_start`.

Next run will write live evidence of routing/repair behavior to
`~/.config/sinkswitch/routing_latency.log`.

### 2. Cycle fix: `profile_switch_time` reset only on successful recovery

Previously the headset-mode timing window was reset **immediately** after firing
recovery, even though a disconnect/reconnect takes 7+ seconds. That let the 5s
window re-close before recovery finished, allowing re-triggering sooner. Now the
window resets only when recovery returns `True`; on failure/cooldown the original
window stays open and the 120s cooldown governs retry rate.

### 3. Cycle fix: cross-coupled repair cooldowns

Two independent recovery paths both run from `_monitor_bluetooth_profiles` and
both issue a disconnect/reconnect:

- HFP-stuck recovery (`_recover_hfp_stuck_device`) — 120s cooldown
- Connected-but-no-sink auto-repair (`_maybe_auto_repair_bluetooth_audio`) — 90s cooldown

They used independent cooldowns, so a repair on one path could be followed
immediately by a repair on the other. Each path now also stamps the other's
cooldown timestamp before repairing, so a disconnect/reconnect can only happen
once per device regardless of which path triggers it.

## Files touched

- `src/audio_router_engine.py`
- `src/device_monitor.py`
- `src/host_command.py` — route `bluetoothctl` (and `pw-cli`) to the host in Flatpak
- `tests/test_idempotency.py` (existing HFP-stuck tests from prior session)
- `tests/test_bluez_config.py` — new `host_cmd` Flatpak routing tests

## Verification

- `python3 tests/test_idempotency.py` — all 12 tests PASS (including
  HFP-stuck detection and escalation/cooldown).
- `python3 -m pytest tests/test_bluez_config.py` — 14 tests PASS (new
  `host_cmd` routing tests for bluetoothctl/pactl in and out of Flatpak).
- `python3 -m py_compile` on changed modules — OK.
- Live verification inside the Flatpak sandbox: host-spawned `bluetoothctl`
  reaches system bluetoothd; a manual host-spawned disconnect/reconnect
  restored A2DP (`a2dp-sink-aac` active, stereo 48 kHz sink).

## Next steps / open items

- Rebuild the Flatpak (`./build-and-run.sh`) so the running app picks up the
  fixes; verify `~/.var/app/io.github.crashman79.sinkswitch/config/sinkswitch/
  routing_latency.log` (the sandboxed path) shows a successful `bt_hfp_recover_done`
  instead of an instant `bt_hfp_recover_fail`.
- Confirm on a live HFP-stuck headset that the app itself (not a manual cycle)
  restores A2DP with a single disconnect/reconnect and no further cycles within
  the cooldown window.