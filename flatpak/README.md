# Flatpak

## Audio tooling

- **`pactl`** — Bundled from **Debian** `.deb` packages (`pulseaudio-utils`, `libpulse0`, `libasyncns0`; `libpulsecommon` ships inside `libpulse0`). It uses Flatpak’s **`--socket=pulseaudio`** proxy to your session’s PipeWire/Pulse stack, so **`pactl subscribe`** runs in-process (no `flatpak-spawn`) and stays responsive. `entrypoint.sh` sets `LD_LIBRARY_PATH` so the bundled client libs are found.
- **`pw-cli`** — Not bundled; still run on the **host** via `flatpak-spawn` with a real `XDG_RUNTIME_DIR` / session bus (`src/host_command.py`).

The build downloads fixed Debian packages with checksums; **your host distro (e.g. Arch) does not matter** — only the Freedesktop runtime ABI.

## Build and install (local)

```bash
flatpak install --user flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08
cd /path/to/sinkswitch
flatpak-builder --user --install --force-clean ../sinkswitch-flatpak-build flatpak/io.github.crashman79.sinkswitch.yml
flatpak run io.github.crashman79.sinkswitch
```

**Python:** Vendored wheels in the manifest (PyYAML, certifi, PyQt6)—no build-time network for `pip`. **`flatpak/python-requirements.txt`** mirrors those versions for non-Flatpak installs. **dbus-python** is omitted (unused in code).

**GitHub Releases** attach a `.flatpak` bundle when you push a tag `v*` (see repo root README).

### Optional: Flathub manifest (git-pinned upstream)

**`io.github.crashman79.sinkswitch-flathub.yml`** is the same layout with a **git `commit`** instead of `type: dir` for the app sources. See [FLATHUB.md](./FLATHUB.md).

### Refreshing vendored Python wheels

Freedesktop SDK **24.08** uses Python **3.12**. To bump PyYAML / certifi / PyQt6:

1. Download wheels (x86_64 example):

   ```bash
   mkdir -p flatpak/flathub-pip-wheels/x86_64
   python3 -m pip download -r flatpak/python-requirements.txt -d flatpak/flathub-pip-wheels/x86_64 \
     --only-binary=:all: --python-version 312 \
     --platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64 \
     --platform manylinux1_x86_64 --platform manylinux_2_5_x86_64
   ```

2. `sha256sum` each `.whl` and match URLs from PyPI JSON at `https://pypi.org/pypi/{project}/{version}/json` (`digests.sha256`).

3. **aarch64** may need a different **PyQt6** line than x86_64 (PyPI); current split is **6.9.1 (x64)** vs **6.7.1 (arm)**.

4. Update **`python3-deps.yml`**, then copy the two **`python3-deps-*`** modules into **`io.github.crashman79.sinkswitch.yml`** and **`io.github.crashman79.sinkswitch-flathub.yml`** so all three match.

## Publishing to Flathub (optional)

See **[FLATHUB.md](./FLATHUB.md)** if you submit to Flathub later.

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
