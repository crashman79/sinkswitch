"""Run host binaries when the app is sandboxed (e.g. Flatpak)."""
from __future__ import annotations

import os
from typing import List, Sequence


def host_cmd(argv: Sequence[str]) -> List[str]:
    """Adjust argv for subprocess when running inside Flatpak.

    ``pactl`` is bundled under ``/app/bin`` and talks to the session’s
    PipeWire/Pulse **compatibility layer** via Flatpak’s ``pulseaudio`` socket.
    That supports long-running ``pactl subscribe`` and avoids ``flatpak-spawn``.

    ``pw-cli`` is not bundled; it still runs on the host with a real
    ``XDG_RUNTIME_DIR`` / session bus.
    """
    if not os.environ.get("FLATPAK_ID"):
        return list(argv)

    exe = argv[0] if argv else ""
    if exe == "pactl":
        return list(argv)

    uid = os.getuid()
    runtime_dir = f"/run/user/{uid}"
    dbus_addr = f"unix:path={runtime_dir}/bus"

    prefix: List[str] = [
        "flatpak-spawn",
        "--host",
        f"--env=XDG_RUNTIME_DIR={runtime_dir}",
        f"--env=DBUS_SESSION_BUS_ADDRESS={dbus_addr}",
        "--env=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    ]
    home = os.environ.get("HOME")
    if home:
        prefix.append(f"--env=HOME={home}")
    user = os.environ.get("USER")
    if user:
        prefix.append(f"--env=USER={user}")
    prefix.append("--")
    prefix.extend(argv)
    return prefix
