#!/usr/bin/env python3
"""
BlueZ daemon configuration helpers for the first-connect A2DP race.

When a headset connects for the first time (or the first time after a
boot/reboot), BlueZ runs a short internal timer to discover SDP records and
build its profile cache.  If the sound server grabs the media transport before
that cache is ready, BlueZ rejects high-quality A2DP setup and the headset
falls back to low-quality HSP/HFP.

The knobs that actually mitigate this (they are documented fixes in the BlueZ
issue tracker, unlike FastConnectable/MultiProfile which do not address the
discovery race):

  * ReverseServiceDiscovery = false  under [General] in /etc/bluetooth/main.conf
        Skips the reverse-SDP query BlueZ performs for previously-unknown
        devices, removing the discovery window the sound server races into.
        Side effect: AVRCP version info for the peer may be incomplete.

  * /etc/dbus-1/system.d/bluetooth-wireplumber.conf
        D-Bus policy override that lets WirePlumber (PipeWire) send
        method_return/error messages back to bluetoothd.  Without it the
        profile setup can fail at the D-Bus layer and the A2DP sink is missing
        until the bluetooth service is restarted.  See bluez issue #1924.

Editing system files and restarting the bluetooth service needs root, so this
module implements the pure merge logic (unit-testable) plus a standalone
``main()`` intended to run under ``pkexec`` (PolicyKit).

Running as a script (root):
    pkexec python3 bluez_config.py --reverse-service-discovery enable --dbus-policy install
    pkexec python3 bluez_config.py --reverse-service-discovery disable --dbus-policy remove
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAIN_CONF = "/etc/bluetooth/main.conf"
MAIN_CONF_BACKUP_SUFFIX = ".sinkswitch.bak"
DBUS_POLICY_PATH = "/etc/dbus-1/system.d/bluetooth-wireplumber.conf"

# D-Bus system policy allowing PipeWire/WirePlumber to reply to bluetoothd
# during A2DP/HFP negotiation (bluez issue #1924).
DBUS_POLICY_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <policy context="default">
    <allow send_destination="org.bluez"/>
    <allow send_interface="org.bluez.MediaEndpoint1"/>
    <allow send_interface="org.bluez.MediaPlayer1"/>
    <allow send_interface="org.bluez.Profile1"/>
    <allow send_interface="org.bluez.GattCharacteristic1"/>
    <allow send_interface="org.bluez.GattDescriptor1"/>
    <allow send_interface="org.bluez.LEAdvertisement1"/>
    <allow send_interface="org.bluez.AdvertisementMonitor1"/>
    <allow send_interface="org.bluez.Agent1"/>
    <allow send_interface="org.freedesktop.DBus.ObjectManager"/>
    <allow send_interface="org.freedesktop.DBus.Properties"/>
    <allow send_interface="org.mpris.MediaPlayer2.Player"/>
    <allow send_type="error"/>
    <allow send_type="method_return"/>
  </policy>
</busconfig>
"""


def merge_main_conf(
    content: str,
    set_keys: Optional[Dict[str, str]] = None,
    remove_keys: Optional[List[str]] = None,
) -> str:
    """Return ``content`` with keys set/removed under the [General] section.

    Args:
        content: Current contents of /etc/bluetooth/main.conf (may be empty).
        set_keys: Map of key -> value to set under [General]. Existing keys are
            replaced in place; missing keys are inserted at the top of the
            [General] section (a new section is created if absent).
        remove_keys: Keys (case-insensitive) to drop from [General] entirely.

    The merge is line-based so comments and unrelated settings are preserved.
    """
    set_keys = set_keys or {}
    remove_keys = {k.lower() for k in (remove_keys or [])}
    if not set_keys and not remove_keys:
        return content

    want_lower = {key.lower(): value for key, value in set_keys.items()}

    lines = content.splitlines() if content else []
    out: List[str] = []
    section: Optional[str] = None
    general_header_index: Optional[int] = None
    matched = set()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().lower()
            out.append(line)
            if section == "general" and general_header_index is None:
                general_header_index = len(out) - 1
            continue

        if section == "general" and not stripped.startswith("#") and "=" in line:
            key_part = line.split("=", 1)[0].strip()
            key_lower = key_part.lower()
            if key_lower in remove_keys:
                continue
            if key_lower in want_lower and key_lower not in matched:
                indent = line[: len(line) - len(line.lstrip())]
                out.append(f"{indent}{key_part} = {want_lower[key_lower]}")
                matched.add(key_lower)
                continue

        out.append(line)

    missing = [
        (key, value) for key, value in set_keys.items() if key.lower() not in matched
    ]
    if missing:
        if general_header_index is None:
            if out and out[-1].strip() != "":
                out.append("")
            out.append("[General]")
            general_header_index = len(out) - 1
        insert_lines = [f"{key} = {value}" for key, value in missing]
        out = out[: general_header_index + 1] + insert_lines + out[general_header_index + 1 :]

    result = "\n".join(out)
    if not result.endswith("\n"):
        result += "\n"
    return result


def _bluetooth_service_restart_command() -> List[str]:
    return ["systemctl", "restart", "bluetooth"]


def _dbus_reload_command() -> List[str]:
    """Reload D-Bus config so newly installed policy files take effect."""
    return ["systemctl", "reload", "dbus"]


def _read_or_empty(path: str) -> str:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def _install_dbus_policy(path: str) -> None:
    Path(path).write_text(DBUS_POLICY_CONTENT, encoding="utf-8")


def _remove_dbus_policy(path: str) -> bool:
    try:
        Path(path).unlink(missing_ok=True)
        return True
    except OSError:
        return False


def apply_bluetooth_settings(
    reverse_service_discovery: Optional[bool] = None,
    dbus_policy: Optional[bool] = None,
    main_conf: str = MAIN_CONF,
    dbus_policy_path: str = DBUS_POLICY_PATH,
) -> Tuple[bool, str]:
    """Persist the first-connect A2DP fixes and restart BlueZ. Must run as root.

    Args:
        reverse_service_discovery: True -> set ReverseServiceDiscovery=false
            (enable the fix); False -> remove the key (restore default true);
            None -> leave untouched.
        dbus_policy: True -> install the WirePlumber D-Bus policy override;
            False -> remove it; None -> leave untouched.

    Returns:
        (ok, message). A backup of main.conf is written before any change, and
        the bluetooth service is restarted after a successful write.
    """
    try:
        changes = []
        set_keys: Dict[str, str] = {}
        remove_keys: List[str] = []
        if reverse_service_discovery is not None:
            if reverse_service_discovery:
                set_keys["ReverseServiceDiscovery"] = "false"
                changes.append("ReverseServiceDiscovery=false")
            else:
                remove_keys.append("ReverseServiceDiscovery")
                changes.append("ReverseServiceDiscovery (default true)")

        content = _read_or_empty(main_conf)
        new_content = merge_main_conf(content, set_keys=set_keys, remove_keys=remove_keys)
        if new_content != content:
            shutil.copyfile(main_conf, main_conf + MAIN_CONF_BACKUP_SUFFIX)
            with open(main_conf, "w", encoding="utf-8") as f:
                f.write(new_content)

        policy_changed = False
        if dbus_policy is not None:
            if dbus_policy:
                _install_dbus_policy(dbus_policy_path)
                changes.append("D-Bus policy installed")
            else:
                _remove_dbus_policy(dbus_policy_path)
                changes.append("D-Bus policy removed")
            policy_changed = True

        if policy_changed:
            try:
                subprocess.run(
                    _dbus_reload_command(),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except Exception:
                pass

        res = subprocess.run(
            _bluetooth_service_restart_command(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if res.returncode != 0:
            err = (res.stderr or res.stdout or "").strip()
            return False, (
                f"Config updated ({', '.join(changes)}), but restarting bluetooth failed: "
                f"{err or res.returncode}"
            )
        if changes:
            return True, f"Bluetooth restarted with: {', '.join(changes)}"
        return True, "Bluetooth service restarted."
    except Exception as e:
        return False, str(e)


def _host_python() -> str:
    """A python binary that pkexec can run regardless of user venv activation."""
    if os.environ.get("FLATPAK_ID"):
        return "/usr/bin/python3"
    if sys.prefix == sys.base_prefix and sys.executable:
        return sys.executable
    return "/usr/bin/python3"


def _script_path() -> Path:
    return Path(__file__).resolve()


def _stage_host_script() -> Path:
    """Copy this script to a host-visible path when running inside Flatpak.

    Flatpak app files live under /app which the host cannot see, and pkexec
    runs on the host, so the module must be reachable from a path the host
    shares with the sandbox.

    Note: inside the sandbox, writes to $XDG_RUNTIME_DIR are redirected to a
    private ``.flatpak/<app-id>/xdg-run`` overlay, so a plain file write here
    is NOT visible to the host. We therefore write through ``flatpak-spawn
    --host`` so pkexec actually runs the updated helper.
    """
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if runtime_dir:
        host_dir = Path(runtime_dir) / "sinkswitch"
    else:
        host_dir = Path.home() / ".local" / "share" / "sinkswitch" / "scripts"
    target = host_dir / "bluez_config.py"

    content = _script_path().read_text(encoding="utf-8")
    if os.environ.get("FLATPAK_ID"):
        subprocess.run(
            ["flatpak-spawn", "--host", "mkdir", "-p", str(host_dir)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        proc = subprocess.run(
            ["flatpak-spawn", "--host", "sh", "-c", 'cat > "$1"', "_", str(target)],
            input=content,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Failed to stage BlueZ helper on host: {(proc.stderr or proc.stdout or '').strip() or proc.returncode}"
            )
        return target

    host_dir.mkdir(parents=True, exist_ok=True)
    if _script_path().resolve() != target:
        shutil.copyfile(_script_path(), target)
    return target


def _pkexec_command(
    reverse_service_discovery: Optional[bool] = None,
    dbus_policy: Optional[bool] = None,
) -> List[str]:
    script = _stage_host_script() if os.environ.get("FLATPAK_ID") else _script_path()

    cmd: List[str] = []
    if os.environ.get("FLATPAK_ID"):
        cmd = [
            "flatpak-spawn",
            "--host",
            "--directory=/tmp",
            "--env=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "pkexec",
        ]
    else:
        cmd = ["pkexec"]

    cmd += [_host_python(), str(script)]
    if reverse_service_discovery is not None:
        cmd += ["--reverse-service-discovery", "enable" if reverse_service_discovery else "disable"]
    if dbus_policy is not None:
        cmd += ["--dbus-policy", "install" if dbus_policy else "remove"]
    return cmd


def run_bluetooth_settings_apply(
    reverse_service_discovery: Optional[bool] = None,
    dbus_policy: Optional[bool] = None,
) -> Tuple[bool, str]:
    """Apply the first-connect A2DP fixes via pkexec (PolicyKit auth dialog)."""
    if reverse_service_discovery is None and dbus_policy is None:
        return True, "No BlueZ settings changed."

    cmd = _pkexec_command(reverse_service_discovery, dbus_policy)
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as e:
        return False, f"Failed to run BlueZ settings helper: {e}"

    if res.returncode == 0:
        out = (res.stdout or "").strip()
        return True, out or "BlueZ settings applied."
    if res.returncode in (126, 127):
        return False, "Authorization cancelled or pkexec unavailable."
    err = (res.stderr or res.stdout or "").strip()
    return False, err or f"BlueZ settings helper exited with {res.returncode}"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply BlueZ first-connect A2DP fixes (run as root)."
    )
    parser.add_argument(
        "--reverse-service-discovery",
        choices=["enable", "disable", "keep"],
        default="keep",
    )
    parser.add_argument(
        "--dbus-policy",
        choices=["install", "remove", "keep"],
        default="keep",
    )
    args = parser.parse_args(argv)

    reverse_service_discovery = (
        None
        if args.reverse_service_discovery == "keep"
        else args.reverse_service_discovery == "enable"
    )
    dbus_policy = (
        None if args.dbus_policy == "keep" else args.dbus_policy == "install"
    )

    ok, msg = apply_bluetooth_settings(reverse_service_discovery, dbus_policy)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())