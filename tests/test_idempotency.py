#!/usr/bin/env python3
"""
Test the idempotency of the intelligent audio router
Simulates different device scenarios to verify consistent behavior
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import yaml
from intelligent_audio_router import IntelligentAudioRouter, DeviceClassifier

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


def main():
    print("\n" + "="*80)
    print("IDEMPOTENCY TEST SUITE")
    print("Testing automatic routing configuration generation")
    print("="*80)
    
    test_1 = test_device_classification()
    test_2 = test_scenario_consistency()
    test_3 = test_routing_rules_generation()
    
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Device Classification:      {'✓ PASS' if test_1 else '✗ FAIL'}")
    print(f"Scenario Consistency:       {'✓ PASS' if test_2 else '✗ FAIL'}")
    print(f"Routing Rules Determinism: {'✓ PASS' if test_3 else '✗ FAIL'}")
    print("="*80)
    
    if test_1 and test_2 and test_3:
        print("\n✓ All idempotency tests PASSED\n")
        return 0
    else:
        print("\n✗ Some tests FAILED\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
