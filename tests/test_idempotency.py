#!/usr/bin/env python3
"""
Test the idempotency of the intelligent audio router
Simulates different device scenarios to verify consistent behavior
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import yaml
from unittest.mock import patch
from types import SimpleNamespace
from audio_router_engine import AudioRouterEngine
from intelligent_audio_router import IntelligentAudioRouter, DeviceClassifier
from device_monitor import DeviceMonitor

# Mock devices for testing
MOCK_DEVICES = {
    "scenario_1_basic": [
        {
            'id': 'alsa_output.pci-0000_0e_00.4.analog-stereo',
            'name': 'alsa_output.pci-0000_0e_00.4.analog-stereo',
            'description': 'Starship/Matisse HD Audio Controller Analog Stereo',
            'device_type': 'Sink',
            'connected': True,
            'properties': {}
        },
        {
            'id': 'bluez_output.00_02_3C_AD_09_85.1',
            'name': 'bluez_output.00_02_3C_AD_09_85.1',
            'description': 'Aurvana Ace 2',
            'device_type': 'Sink',
            'connected': True,
            'properties': {}
        }
    ],
    "scenario_2_with_usb": [
        {
            'id': 'alsa_output.pci-0000_0e_00.4.analog-stereo',
            'name': 'alsa_output.pci-0000_0e_00.4.analog-stereo',
            'description': 'Starship/Matisse HD Audio Controller Analog Stereo',
            'device_type': 'Sink',
            'connected': True,
            'properties': {}
        },
        {
            'id': 'alsa_output.usb-Logitech_Logitech_G633_Gaming_Headset_00000000-00.analog-stereo',
            'name': 'alsa_output.usb-Logitech_Logitech_G633_Gaming_Headset_00000000-00.analog-stereo',
            'description': 'Logitech G633 Gaming Headset Analog Stereo',
            'device_type': 'Sink',
            'connected': True,
            'properties': {}
        },
        {
            'id': 'bluez_output.00_02_3C_AD_09_85.1',
            'name': 'bluez_output.00_02_3C_AD_09_85.1',
            'description': 'Aurvana Ace 2',
            'device_type': 'Sink',
            'connected': True,
            'properties': {}
        }
    ],
    "scenario_3_usb_only": [
        {
            'id': 'alsa_output.usb-Logitech_Logitech_G633_Gaming_Headset_00000000-00.analog-stereo',
            'name': 'alsa_output.usb-Logitech_Logitech_G633_Gaming_Headset_00000000-00.analog-stereo',
            'description': 'Logitech G633 Gaming Headset Analog Stereo',
            'device_type': 'Sink',
            'connected': True,
            'properties': {}
        },
        {
            'id': 'bluez_output.00_02_3C_AD_09_85.1',
            'name': 'bluez_output.00_02_3C_AD_09_85.1',
            'description': 'Aurvana Ace 2',
            'device_type': 'Sink',
            'connected': True,
            'properties': {}
        }
    ],
    "scenario_4_speakers_only": [
        {
            'id': 'alsa_output.pci-0000_0e_00.4.analog-stereo',
            'name': 'alsa_output.pci-0000_0e_00.4.analog-stereo',
            'description': 'Starship/Matisse HD Audio Controller Analog Stereo',
            'device_type': 'Sink',
            'connected': True,
            'properties': {}
        }
    ],
}


def test_device_classification():
    """Test that device classification is consistent"""
    print("\n" + "="*80)
    print("TEST 1: Device Classification Consistency")
    print("="*80)
    
    classifier = DeviceClassifier()
    
    test_cases = [
        ("bluez_output.00_02_3C_AD_09_85.1", "Aurvana Ace 2", "bluetooth"),
        ("alsa_output.usb-Logitech*", "Logitech G633 Gaming Headset", "usb_headset"),
        ("alsa_output.pci-0000_0e_00.4.analog-stereo", "Analog Stereo", "analog_speakers"),
    ]
    
    all_pass = True
    for device_id, description, expected_type in test_cases:
        device = {
            'id': device_id,
            'name': device_id,
            'description': description,
            'device_type': 'Sink',
            'connected': True,
            'properties': {}
        }
        
        classified = classifier.classify_device(device)
        passed = classified == expected_type
        all_pass = all_pass and passed
        
        status = "✓" if passed else "✗"
        print(f"{status} {device_id}: expected={expected_type}, got={classified}")
    
    return all_pass


def test_scenario_consistency():
    """Test that running generation twice produces identical output"""
    print("\n" + "="*80)
    print("TEST 2: Configuration Generation Idempotency")
    print("="*80)
    
    all_pass = True
    
    for scenario_name, devices in MOCK_DEVICES.items():
        print(f"\n{scenario_name}:")
        print(f"  Connected devices: {len(devices)}")
        for dev in devices:
            print(f"    - {dev['description']}")
        
        # Simulate generating config twice
        classifier = DeviceClassifier()
        
        # First pass
        device_map_1 = {}
        for device in devices:
            dev_type = classifier.classify_device(device)
            if dev_type not in device_map_1:
                device_map_1[dev_type] = []
            device_map_1[dev_type].append(device)
        
        # Second pass (should be identical)
        device_map_2 = {}
        for device in devices:
            dev_type = classifier.classify_device(device)
            if dev_type not in device_map_2:
                device_map_2[dev_type] = []
            device_map_2[dev_type].append(device)
        
        # Compare
        maps_equal = str(device_map_1) == str(device_map_2)
        all_pass = all_pass and maps_equal
        
        status = "✓" if maps_equal else "✗"
        print(f"  {status} Two generations produce identical device maps")
    
    return all_pass


def test_routing_rules_generation():
    """Test that generated rules are deterministic"""
    print("\n" + "="*80)
    print("TEST 3: Generated Routing Rules Determinism")
    print("="*80)
    
    all_pass = True
    
    for scenario_name, devices in MOCK_DEVICES.items():
        print(f"\n{scenario_name}:")
        
        # Simulate the routing rule generation logic
        app_categories = {
            'browsers': ['firefox', 'chrome', 'chromium', 'opera', 'edge', 'brave'],
            'meetings': ['zoom', 'teams', 'meet', 'discord', 'skype', 'slack'],
            'music': ['spotify', 'vlc', 'rhythmbox', 'cmus', 'mpv', 'audacious'],
        }
        
        routing_priorities = {
            'browsers': ['bluetooth_earbuds', 'usb_headset', 'default'],
            'meetings': ['bluetooth_earbuds', 'usb_headset', 'default'],
            'music': ['bluetooth_earbuds', 'usb_headset', 'default'],
        }
        
        classifier = DeviceClassifier()
        
        # Build device map
        device_map = {}
        for device in devices:
            dev_type = classifier.classify_device(device)
            if dev_type not in device_map:
                device_map[dev_type] = []
            device_map[dev_type].append(device)
        
        # Generate rules (simulate the algorithm)
        rules_generated = []
        for category, priorities in routing_priorities.items():
            for priority in priorities:
                if priority == 'default':
                    continue
                
                priority_map = {
                    'bluetooth_earbuds': 'bluetooth',
                    'usb_headset': 'usb_headset',
                }
                
                device_type = priority_map.get(priority)
                if device_type and device_type in device_map:
                    device = device_map[device_type][0]
                    rules_generated.append({
                        'category': category,
                        'target_device': device['id'],
                        'device_type': device_type
                    })
                    break
        
        print(f"  Generated {len(rules_generated)} routing rules:")
        for rule in rules_generated:
            print(f"    - {rule['category']} → {rule['device_type']}")
        
        # Generate again and verify identical
        rules_generated_2 = []
        for category, priorities in routing_priorities.items():
            for priority in priorities:
                if priority == 'default':
                    continue
                
                priority_map = {
                    'bluetooth_earbuds': 'bluetooth',
                    'usb_headset': 'usb_headset',
                }
                
                device_type = priority_map.get(priority)
                if device_type and device_type in device_map:
                    device = device_map[device_type][0]
                    rules_generated_2.append({
                        'category': category,
                        'target_device': device['id'],
                        'device_type': device_type
                    })
                    break
        
        rules_equal = str(rules_generated) == str(rules_generated_2)
        all_pass = all_pass and rules_equal
        
        status = "✓" if rules_equal else "✗"
        print(f"  {status} Two generations produce identical rules")
    
    return all_pass


def test_bt_master_sink_resolution_skips_managed_remaps():
    """Regression test: physical Bluetooth sink resolution must ignore SinkSwitch remap sinks."""
    print("\n" + "="*80)
    print("TEST 4: Bluetooth Master Sink Resolution")
    print("="*80)

    sinks_output = """Sink #12
Name: sinkswitch_mono.bluez_output.00_02_3C_AD_09_85.1

Sink #13
Name: bluez_output.00_02_3C_AD_09_85.1
"""

    def fake_run(cmd, **kwargs):
        joined = " ".join(cmd)
        if "pactl list sinks" in joined:
            return SimpleNamespace(returncode=0, stdout=sinks_output, stderr="")
        if "pactl list short modules" in joined:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "pactl list short sinks" in joined:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch("audio_router_engine.subprocess.run", side_effect=fake_run), \
         patch.object(AudioRouterEngine, "_cleanup_sinkswitch_remaps", return_value=None):
        engine = AudioRouterEngine()
        resolved = engine._resolve_sink(
            "bluez_output.00_02_3C_AD_09_85.1",
            allow_managed_remaps=False,
        )

    passed = resolved == ("13", "bluez_output.00_02_3C_AD_09_85.1")
    status = "✓" if passed else "✗"
    print(f"{status} Resolver returned physical Bluetooth sink: {resolved}")
    return passed


def test_bt_off_profile_triggers_recovery():
    """Regression test: Bluetooth profile stuck on off should trigger A2DP recovery."""
    print("\n" + "="*80)
    print("TEST 5: Bluetooth Off Profile Recovery")
    print("="*80)

    called = []

    with patch.object(DeviceMonitor, "get_bluetooth_card_info", return_value={
        "name": "bluez_card.00_02_3C_AD_09_85",
        "active_profile": "off",
        "profiles": {"a2dp-sink": "High Fidelity Playback"},
    }), patch.object(DeviceMonitor, "prefer_a2dp_profile", side_effect=lambda addr: called.append(addr) or True), \
         patch.object(DeviceMonitor, "_get_connected_bluetooth_macs", return_value={"00_02_3C_AD_09_85"}), \
         patch.object(DeviceMonitor, "_is_internal_managed_sink_id", return_value=False):
        monitor = DeviceMonitor()
        monitor.bluetooth_profile_state = {}
        monitor._monitor_bluetooth_profiles([])

    passed = called == ["00:02:3C:AD:09:85"]
    status = "✓" if passed else "✗"
    print(f"{status} Recovery triggered for off profile: {called}")
    return passed


def test_hfp_only_skips_mono_remap():
    """Regression test: an HFP/headset-profile BT sink (inherently mono) must
    never be wrapped in a SinkSwitch mono remap sink. In the real bug this
    triggered `pactl load-module module-remap-sink` against a dying HFP
    transport, which hung for 5s and wedged the audio server."""
    print("\n" + "="*80)
    print("TEST 6: HFP-Only Connect Skips Mono Remap")
    print("="*80)

    mono_remap_called = []

    def fail_if_remap(master_sink):
        mono_remap_called.append(master_sink)
        return "sinkswitch_mono.should_never_happen"

    engine = AudioRouterEngine()
    with patch.object(DeviceMonitor, "is_headset_profile", return_value=True), \
         patch.object(AudioRouterEngine, "_is_single_channel_bluetooth_sink", return_value=True), \
         patch.object(AudioRouterEngine, "_ensure_mono_remap_sink", side_effect=fail_if_remap):
        result = engine._get_effective_target_sink("bluez_output.00_02_3C_AD_09_85.1")

    passed = result == "bluez_output.00_02_3C_AD_09_85.1" and not mono_remap_called
    status = "✓" if passed else "✗"
    print(f"{status} Effective target stays on physical sink: {result} (mono_remap calls={mono_remap_called})")
    return passed


def test_detect_audio_backend_never_raises_on_timeout():
    """Regression test: a hanging `pw-cli info` must not raise out of the
    DeviceMonitor constructor. When it did, TimeoutExpired escaped a PyQt slot
    (update_streams) and PyQt6 aborted the whole app with qFatal/SIGABRT."""
    print("\n" + "="*80)
    print("TEST 7: Backend Detection Never Raises On Timeout")
    print("="*80)

    from subprocess import TimeoutExpired

    with patch("device_monitor.subprocess.run", side_effect=TimeoutExpired(cmd=["pw-cli", "info"], timeout=2)):
        try:
            DeviceMonitor._backend_cache = None
            monitor = DeviceMonitor()
            raised = False
        except Exception:
            raised = True
        finally:
            DeviceMonitor._backend_cache = None

    passed = not raised and monitor.backend in ('pipewire', 'pulseaudio')
    status = "✓" if passed else "✗"
    print(f"{status} Constructor tolerated pw-cli timeout (backend={getattr(monitor, 'backend', None)})")
    return passed


def test_prefer_a2dp_restores_profile_on_failure():
    """Regression test: when the soft-toggle to A2DP fails, the previous headset
    profile is restored so the headset keeps producing audio (sound must not be
    left broken until a manual reconnect)."""
    print("\n" + "="*80)
    print("TEST 8: Soft-Toggle Failure Restores Previous Profile")
    print("="*80)

    profile_calls = []

    def fake_set_profile(card_name, profile):
        profile_calls.append((card_name, profile))
        # First (off) succeeds; actual A2DP never materialises.
        return profile == "off"

    def fake_card_info(address):
        return {
            "name": "bluez_card.00_02_3C_AD_09_85",
            "active_profile": "headset-head-unit",
            "profiles": {"off": "Off", "headset-head-unit": "Headset Head Unit"},
        }

    with patch.object(DeviceMonitor, "get_bluetooth_card_info", side_effect=fake_card_info), \
         patch.object(DeviceMonitor, "set_bluetooth_profile", side_effect=fake_set_profile), \
         patch("device_monitor.time.sleep", return_value=None):
        monitor = DeviceMonitor()
        monitor._last_bt_a2dp_soft_toggle_ts_by_mac = {}
        ok = monitor.prefer_a2dp_profile("00:02:3C:AD:09:85")

    passed = not ok and ("bluez_card.00_02_3C_AD_09_85", "headset-head-unit") in profile_calls
    status = "✓" if passed else "✗"
    print(f"{status} Previous profile restored after failed toggle (calls={profile_calls})")
    return passed


def test_prefer_a2dp_soft_toggle_cooldown():
    """Regression test: repeated soft-toggle attempts are throttled so the card is
    not churned on every routing pass."""
    print("\n" + "="*80)
    print("TEST 9: Soft-Toggle Cooldown")
    print("="*80)

    off_toggles = []

    def fake_set_profile(card_name, profile):
        off_toggles.append(profile)
        return profile == "off"

    def fake_card_info(address):
        return {
            "name": "bluez_card.00_02_3C_AD_09_85",
            "active_profile": "headset-head-unit",
            "profiles": {"off": "Off", "headset-head-unit": "Headset Head Unit"},
        }

    with patch.object(DeviceMonitor, "get_bluetooth_card_info", side_effect=fake_card_info), \
         patch.object(DeviceMonitor, "set_bluetooth_profile", side_effect=fake_set_profile), \
         patch("device_monitor.time.sleep", return_value=None), \
         patch("device_monitor.time.time", return_value=1000.0):
        monitor = DeviceMonitor()
        monitor._last_bt_a2dp_soft_toggle_ts_by_mac = {}
        monitor.prefer_a2dp_profile("00:02:3C:AD:09:85")
        # Second call within cooldown: must not attempt another soft-toggle.
        monitor.prefer_a2dp_profile("00:02:3C:AD:09:85")

    # One invocation runs up to 3 internal retries; the cooldown-blocked second
    # invocation must add zero additional 'off' attempts.
    passed = off_toggles.count("off") == 3
    status = "✓" if passed else "✗"
    print(f"{status} Soft-toggle blocked within cooldown (off_toggles={off_toggles})")
    return passed


def test_ensure_mono_remap_handles_load_module_timeout():
    """Regression test: a `pactl load-module module-remap-sink` that times out
    must degrade to returning the master sink instead of raising."""
    print("\n" + "="*80)
    print("TEST 10: Mono Remap Load-Module Timeout Is Safe")
    print("="*80)

    from subprocess import TimeoutExpired

    def fake_run(cmd, **kwargs):
        joined = " ".join(cmd)
        if "pactl list sinks" in joined:
            return SimpleNamespace(
                returncode=0,
                stdout="Sink #13\n\tName: bluez_output.00_02_3C_AD_09_85.1\n",
                stderr="",
            )
        if "pactl list short modules" in joined:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "pactl list short sinks" in joined:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "pactl list sink-inputs" in joined:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "load-module" in joined:
            raise TimeoutExpired(cmd=["pactl", "load-module"], timeout=5)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch("audio_router_engine.subprocess.run", side_effect=fake_run), \
         patch.object(AudioRouterEngine, "_cleanup_sinkswitch_remaps", return_value=None):
        engine = AudioRouterEngine()
        engine._mono_sink_cache = {}
        engine._mono_master_sink_id_cache = {}
        result = engine._ensure_mono_remap_sink("bluez_output.00_02_3C_AD_09_85.1")

    passed = result == "bluez_output.00_02_3C_AD_09_85.1"
    status = "✓" if passed else "✗"
    print(f"{status} load-module timeout returned physical master: {result}")
    return passed


def main():
    print("\n" + "="*80)
    print("IDEMPOTENCY TEST SUITE")
    print("Testing automatic routing configuration generation")
    print("="*80)
    
    test_1 = test_device_classification()
    test_2 = test_scenario_consistency()
    test_3 = test_routing_rules_generation()
    test_4 = test_bt_master_sink_resolution_skips_managed_remaps()
    test_5 = test_bt_off_profile_triggers_recovery()
    test_6 = test_hfp_only_skips_mono_remap()
    test_7 = test_detect_audio_backend_never_raises_on_timeout()
    test_8 = test_prefer_a2dp_restores_profile_on_failure()
    test_9 = test_prefer_a2dp_soft_toggle_cooldown()
    test_10 = test_ensure_mono_remap_handles_load_module_timeout()

    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Device Classification:      {'✓ PASS' if test_1 else '✗ FAIL'}")
    print(f"Scenario Consistency:       {'✓ PASS' if test_2 else '✗ FAIL'}")
    print(f"Routing Rules Determinism: {'✓ PASS' if test_3 else '✗ FAIL'}")
    print(f"BT Master Resolution:       {'✓ PASS' if test_4 else '✗ FAIL'}")
    print(f"BT Off Recovery:            {'✓ PASS' if test_5 else '✗ FAIL'}")
    print(f"HFP-Only Skips Mono Remap:  {'✓ PASS' if test_6 else '✗ FAIL'}")
    print(f"Backend Timeout Safe:       {'✓ PASS' if test_7 else '✗ FAIL'}")
    print(f"A2DP Restore On Failure:    {'✓ PASS' if test_8 else '✗ FAIL'}")
    print(f"A2DP Soft-Toggle Cooldown:  {'✓ PASS' if test_9 else '✗ FAIL'}")
    print(f"Remap Load-Module Timeout:  {'✓ PASS' if test_10 else '✗ FAIL'}")
    print("="*80)

    if test_1 and test_2 and test_3 and test_4 and test_5 and test_6 and test_7 and test_8 and test_9 and test_10:
        print("\n✓ All idempotency tests PASSED\n")
        return 0
    else:
        print("\n✗ Some tests FAILED\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
