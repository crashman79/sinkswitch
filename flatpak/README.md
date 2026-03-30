# Flatpak

## Audio tooling

- **`pactl`** — Bundled from **Debian** `.deb` packages (`pulseaudio-utils`, `libpulse0`, `libasyncns0`; `libpulsecommon` ships inside `libpulse0`). It uses Flatpak’s **`--socket=pulseaudio`** proxy to your session’s PipeWire/Pulse stack, so **`pactl subscribe`** runs in-process (no `flatpak-spawn`) and stays responsive. `entrypoint.sh` sets `LD_LIBRARY_PATH` so the bundled client libs are found.
- **`pw-cli`** — Not bundled; still run on the **host** via `flatpak-spawn` with a real `XDG_RUNTIME_DIR` / session bus (`src/host_command.py`).

The build downloads fixed Debian packages with checksums; **your host distro (e.g. Arch) does not matter** — only the Freedesktop runtime ABI.

## Build and install (local)

```bash
flatpak install -y flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08
cd /path/to/sinkswitch
flatpak-builder --user --install --force-clean ../sinkswitch-flatpak-build flatpak/io.github.crashman79.sinkswitch.yml
flatpak run io.github.crashman79.sinkswitch
```

Python deps: **`flatpak/python-requirements.txt`** (PyYAML, certifi, PyQt6). **dbus-python** is omitted (unused in code; sdist needs mesonpy).

The manifest uses **`--share=network`** during pip for local builds. **Flathub** expects vendored wheels (e.g. [flatpak-pip-generator](https://github.com/flatpak/flatpak-builder-tools)) and no network at build time.

## Publishing to Flathub

See **[FLATHUB.md](./FLATHUB.md)** for the full checklist (screenshots, vendored Python wheels, PR flow). Summary:

1. AppStream must include **screenshots** and a current **`<release>`** (see `io.github.crashman79.sinkswitch.metainfo.xml`).
2. For the Flathub copy of the manifest, **pin Python deps** (no network at build time) using [flatpak-pip-generator](https://github.com/flathub/flatpak-builder-tools/tree/master/pip).
3. Open a PR per [Flathub submission](https://docs.flathub.org/docs/for-app-authors/submission/).

**Icons:** Canonical artwork lives in `data/icons/` (`io.github.crashman79.sinkswitch.svg` and `.png`); the Flatpak module installs them into `hicolor` (same as the PyInstaller bundle and in-app window/tray icon).

## Coexisting with other installs

`~/.config/sinkswitch` and `~/.cache/sinkswitch` are mounted from the host.

## Permissions

Flatpak permissions are **only** the manifest `finish-args` (no in-app prompts).

| Permission | Why |
|------------|-----|
| `--socket=pulseaudio` | Bundled `pactl` talks to the session audio server. |
| `--talk-name=org.freedesktop.Flatpak` | `flatpak-spawn --host` for `pw-cli`. |
| `--socket=session-bus` | Session D-Bus (portal / spawn). |
| `--filesystem=…` config/cache | Same files as non-Flatpak installs. |

## Troubleshooting

If devices still misbehave after a rebuild, run `pactl info` inside the app:

```bash
flatpak run --command=sh io.github.crashman79.sinkswitch -c 'pactl info | head'
```

You should see server info, not connection errors.
