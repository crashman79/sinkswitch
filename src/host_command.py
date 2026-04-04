"""Run host binaries when the app is sandboxed (e.g. Flatpak)."""
from __future__ import annotations

import os
from typing import Dict, List, Sequence

# pactl/pw-cli may emit property strings in the session encoding; strict UTF-8 fails.
SUBPROCESS_TEXT_KW: Dict[str, str] = {"encoding": "utf-8", "errors": "replace"}

# In Flatpak, read-only pactl (list, subscribe, get-default-sink, …) must stay
# in the sandbox: it sees the same graph as the proxy. Running *all* pactl on
# the host after unsetting PULSE_* often yields empty device lists.
_PACTL_HOST_SUBCOMMANDS = frozenset(
    {
        "move-sink-input",
        "set-default-sink",
        "set-card-profile",
    }
)


def _flatpak_host_spawn_prefix() -> List[str]:
    """Env for host subprocesses that need the real PipeWire/Pulse session.

    In-sandbox ``pactl`` uses Flatpak's Pulse proxy: listing works but mutating
    commands return "Access denied". Those mutations run via host ``pactl``.
    """
    uid = os.getuid()
    runtime_dir = f"/run/user/{uid}"
    dbus_addr = f"unix:path={runtime_dir}/bus"
    prefix: List[str] = [
        "flatpak-spawn",
        "--host",
        # flatpak-spawn defaults to the caller's working directory; when called
        # from inside the Flatpak it may be `/app/...` which doesn't exist on
        # the host filesystem. Use a directory that exists in both.
        "--directory=/tmp",
        "--unset-env=PULSE_SERVER",
        "--unset-env=PULSE_COOKIE",
        "--unset-env=PULSE_RUNTIME_PATH",
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
    return prefix


def host_cmd(argv: Sequence[str]) -> List[str]:
    """Adjust argv for subprocess when running inside Flatpak.

    - ``pw-cli``: always on the host (not bundled in the app).
    - ``pactl``: default in-sandbox (Pulse proxy; lists/subscribe match the UI).
      Only mutating subcommands use ``flatpak-spawn --host`` so moves/profiles
      are permitted.

    Outside Flatpak, argv is returned unchanged.
    """
    if not os.environ.get("FLATPAK_ID"):
        return list(argv)

    exe = argv[0] if argv else ""
    if exe == "pw-cli":
        prefix = _flatpak_host_spawn_prefix()
        prefix.append("--")
        prefix.extend(argv)
        return prefix

    if exe == "pactl" and len(argv) > 1 and argv[1] in _PACTL_HOST_SUBCOMMANDS:
        prefix = _flatpak_host_spawn_prefix()
        prefix.append("--")
        prefix.extend(argv)
        return prefix

    return list(argv)
