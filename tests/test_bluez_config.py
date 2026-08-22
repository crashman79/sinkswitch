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
)


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