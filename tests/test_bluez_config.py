#!/usr/bin/env python3
"""
Tests for BlueZ first-connect A2DP fix helpers (src/bluez_config.py).

Covers the pure main.conf merge logic plus the D-Bus policy constants.  No
root required for these string transforms.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest

from bluez_config import (
    merge_main_conf,
    DBUS_POLICY_CONTENT,
    DBUS_POLICY_PATH,
    WIREPLUMBER_BT_CONF_CONTENT,
    WIREPLUMBER_BT_CONF,
)
from host_command import host_cmd


TYPICAL_CONF = """\
# Bluetoothd configuration file
[General]
#Class = 0x000100
Name = My Computer
#ReverseServiceDiscovery = true
"""


def test_reverse_service_discovery_set_under_general():
    out = merge_main_conf(TYPICAL_CONF, set_keys={"ReverseServiceDiscovery": "false"})
    assert "ReverseServiceDiscovery = false" in out
    assert "Name = My Computer" in out
    # Commented-out default stays intact (informational).
    assert "#ReverseServiceDiscovery = true" in out


def test_reverse_service_discovery_removed_restores_original():
    out = merge_main_conf(TYPICAL_CONF, set_keys={"ReverseServiceDiscovery": "false"})
    reverted = merge_main_conf(out, remove_keys=["ReverseServiceDiscovery"])
    active_lines = [
        ln for ln in reverted.splitlines()
        if ln.strip().startswith("ReverseServiceDiscovery")
    ]
    assert active_lines == []
    assert reverted == TYPICAL_CONF


def test_existing_value_replaced_in_place():
    conf = "[General]\nReverseServiceDiscovery = true\nName = Foo\n"
    out = merge_main_conf(conf, set_keys={"ReverseServiceDiscovery": "false"})
    assert out.count("ReverseServiceDiscovery") == 1
    assert "ReverseServiceDiscovery = false" in out
    assert "Name = Foo" in out


def test_no_general_section_creates_one():
    conf = "Name = Foo\nClass = 0x000100\n"
    out = merge_main_conf(conf, set_keys={"ReverseServiceDiscovery": "false"})
    assert "[General]" in out
    assert "ReverseServiceDiscovery = false" in out


def test_empty_content_creates_general():
    out = merge_main_conf("", set_keys={"ReverseServiceDiscovery": "false"})
    assert out == "[General]\nReverseServiceDiscovery = false\n"


def test_no_changes_returns_input_unchanged():
    assert merge_main_conf(TYPICAL_CONF) == TYPICAL_CONF
    assert merge_main_conf(TYPICAL_CONF, set_keys={}, remove_keys=[]) == TYPICAL_CONF


def test_comments_and_other_sections_preserved():
    conf = """\
[General]
Name = Foo

[Policy]
ReconnectAttempts = 7
"""
    out = merge_main_conf(conf, set_keys={"ReverseServiceDiscovery": "false"})
    assert "[Policy]" in out
    assert "ReconnectAttempts = 7" in out
    assert "Name = Foo" in out
    assert "ReverseServiceDiscovery = false" in out


def test_remove_key_drops_only_that_key():
    conf = """\
[General]
Name = Foo
ReverseServiceDiscovery = true
MultiProfile = off
"""
    out = merge_main_conf(conf, remove_keys=["ReverseServiceDiscovery"])
    assert "ReverseServiceDiscovery" not in out
    assert "MultiProfile = off" in out
    assert "Name = Foo" in out


def test_parse_round_trip_idempotent():
    once = merge_main_conf(TYPICAL_CONF, set_keys={"ReverseServiceDiscovery": "false"})
    twice = merge_main_conf(once, set_keys={"ReverseServiceDiscovery": "false"})
    assert once == twice


def test_dbus_policy_content_wellformed():
    assert DBUS_POLICY_PATH.endswith("bluetooth-wireplumber.conf")
    assert "org.bluez.MediaEndpoint1" in DBUS_POLICY_CONTENT
    assert "<policy context=\"default\">" in DBUS_POLICY_CONTENT
    assert "send_type=\"method_return\"" in DBUS_POLICY_CONTENT


def test_wireplumber_conf_content_wellformed():
    # Lives under the WirePlumber 0.5+ bluetooth monitor drop-in dir.
    assert WIREPLUMBER_BT_CONF.endswith("sinkswitch-a2dp.conf")
    assert "bluetooth.conf.d" in WIREPLUMBER_BT_CONF
    # The actual race prevention: only auto-connect A2DP, defer HFP.
    assert "bluez5.auto-connect = [ a2dp_sink ]" in WIREPLUMBER_BT_CONF_CONTENT
    assert "device.name = \"~bluez_card.*\"" in WIREPLUMBER_BT_CONF_CONTENT
    assert "bluez5.roles = [ a2dp_sink ]" in WIREPLUMBER_BT_CONF_CONTENT


def test_host_cmd_unchanged_outside_flatpak():
    assert host_cmd(['bluetoothctl', 'disconnect', '00:02:3C:AD:09:85']) == [
        'bluetoothctl', 'disconnect', '00:02:3C:AD:09:85'
    ]
    assert host_cmd(['pactl', 'list', 'sinks']) == ['pactl', 'list', 'sinks']


def test_host_cmd_flatpak_routes_bluetoothctl_to_host(monkeypatch):
    monkeypatch.setenv("FLATPAK_ID", "io.github.crashman79.sinkswitch")
    monkeypatch.setenv("HOME", "/home/testuser")
    monkeypatch.setenv("USER", "testuser")

    argv = host_cmd(['bluetoothctl', 'disconnect', '00:02:3C:AD:09:85'])
    assert argv[0] == "flatpak-spawn"
    assert "--host" in argv
    assert argv[-4:] == ['--', 'bluetoothctl', 'disconnect', '00:02:3C:AD:09:85']


def test_host_cmd_flatpak_routes_mutating_pactl_to_host(monkeypatch):
    monkeypatch.setenv("FLATPAK_ID", "io.github.crashman79.sinkswitch")
    monkeypatch.setenv("HOME", "/home/testuser")
    monkeypatch.setenv("USER", "testuser")

    argv = host_cmd(['pactl', 'set-card-profile', 'bluez_card.00_02_3C_AD_09_85', 'a2dp-sink'])
    assert argv[0] == "flatpak-spawn"
    assert "--host" in argv


def test_host_cmd_flatpak_keeps_readonly_pactl_in_sandbox(monkeypatch):
    monkeypatch.setenv("FLATPAK_ID", "io.github.crashman79.sinkswitch")
    monkeypatch.setenv("HOME", "/home/testuser")
    monkeypatch.setenv("USER", "testuser")

    assert host_cmd(['pactl', 'list', 'sinks']) == ['pactl', 'list', 'sinks']
    assert host_cmd(['pactl', 'get-default-sink']) == ['pactl', 'get-default-sink']