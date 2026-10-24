# SinkSwitch

Send each app's audio to the output you want — Bluetooth earbuds, a USB headset,
HDMI TV, or your speakers — instead of everything fighting over one device.

SinkSwitch is a small desktop app for Linux. You pick a **default output** (where
unmatched apps go) and then define **rules** so specific apps always play through
the device you choose. It runs entirely on your machine using PipeWire or
PulseAudio; there is no account, no cloud, and no background service to manage.

> Typical use: keep your music or video call on Bluetooth earbuds while game
> sound and system notifications stay on the speakers — automatically, the moment
> each app starts playing.

---

## Why SinkSwitch (advantages)

- **Per-app routing without the fiddling.** New audio streams are caught
  automatically and moved to the right device based on rules you define once.
- **Your speaker volume keys still work.** SinkSwitch adds an *optional*
  modifier‑plus‑volume shortcut that controls **only** the Bluetooth device.
  The plain volume keys keep controlling your speakers, exactly as your desktop
  always did.
- **One Bluetooth control point.** When you route to Bluetooth, SinkSwitch
  creates a single virtual "SinkSwitch Bluetooth" output that all your
  Bluetooth‑routed apps share. That is what lets one keyboard shortcut adjust
  them together, and it handles single‑earbud mono mixing cleanly.
- **Calm interface.** The device and stream lists refresh only when something
  actually changes — a device connects, an app starts playing, or you switch the
  default output. No constant flicker or CPU churn from polling.
- **Just an app.** No daemon, systemd unit, or root service. Start it, stop it,
  or leave it in the tray.

---

## How it works (design and logic, in plain terms)

**The router lives inside the app.** When routing is on, a small loop inside
SinkSwitch watches your audio graph. For every app that starts playing, it asks:

1. *Does this app match one of my rules?* If yes, move its audio to that rule's
   target device.
2. *If not, leave it on the default output* you selected in the toolbar.

That's the whole model. When the router is stopped, SinkSwitch stops moving
streams: apps already sent to a device stay there until they finish, and any new
streams are left to play on the system default. Start it again and the rules
reapply.

**Rules are simple and forgiving.** Each rule has a name, a list of apps (by
name or keyword), a target device, and an optional *fallback*: if the target
isn't connected right now (earbuds in the case?), the app falls back to your
default output instead of going silent. You can make rules in the **Routing
Rules** tab or let SinkSwitch generate a sensible starter set on first run.

**Bluetooth is special.** Rather than pointing each app straight at the raw
Bluetooth device, SinkSwitch routes them through one managed virtual sink that
mirrors your earbuds. This gives a single, reliable volume control and makes the
modifier‑plus‑volume shortcut possible. If Bluetooth isn't available, routing
simply degrades to the real device.

**Volume shortcuts.** With the setting enabled, a global hotkey —
*modifier* + Volume Up/Down/Mute (e.g. Ctrl+VolumeUp) — nudges the Bluetooth
output's volume. It uses the desktop's Global Shortcuts portal, so your desktop
environment still owns the unmodified keys. The first time, your desktop may ask
for permission; if you decline, the setting just shows a status and the rest of
the app works normally.

**Refresh is event‑driven.** Instead of re‑scanning every couple of seconds,
SinkSwitch listens to system audio events and only redraws the lists when the
parsed data actually changes. A slow safety check runs in the background in case
event notifications are unavailable, and even that never redraws unchanged data.

---

## The interface

The window has a toolbar and a few tabs:

- **Devices & Streams** — the main view.
  - *Devices:* the outputs SinkSwitch can see, with a status dot (green =
    connected, red = disconnected).
  - *Active Streams:* the apps currently playing, where each one is going, and
    its Route (a rule name, a temporary override, or "Default"). Select a stream
    and use **Bluetooth / HDMI / Analog speakers** to send it there. Choose
    **Temporary** (applies while the router runs) or **Permanent** (saved as a
    rule).
- **Routing Rules** — view, add, edit, delete, and auto‑generate rules, then
  save your config.
- **Logs** — a live view of what the router is doing (handy when something
  doesn't route as expected).
- **Settings** — startup, appearance, tray, Bluetooth mono, and the volume
  shortcut (see below).
- **About** — version, config location, and update checks.

**Toolbar:** a router status indicator, the **Default output** selector, a
**Force Mono** toggle (force Bluetooth to mono regardless of detection), and
**Start / Restart / Stop** for the router.

**System tray:** minimize to tray, show the window, start/stop the router, and
quit — all from the tray menu. Closing the window minimizes to tray when that
option is enabled.

---

## Getting started

1. **Install and launch** SinkSwitch (see *Install* below).
2. On first run it creates a config and, if you have devices connected, generates
   a starter set of rules (browsers/meetings/media → Bluetooth/USB when present).
   Review them in **Routing Rules**; edit or remove anything you don't want.
3. The router **starts automatically by default** (you can turn this off in
   Settings). If it's stopped, click **Start** in the toolbar.
4. Play something and watch **Active Streams**. Matched apps move to their rule's
   device; everything else stays on the **Default output** you picked.
5. Need a one‑off change? Select a stream and click **Bluetooth / HDMI /
   Analog** — Temporary for now, or Permanent to remember it.

---

## Settings explained

| Setting | What it does |
| --- | --- |
| **Start SinkSwitch when I log in** | Adds SinkSwitch to your login startup (Flatpak XDG autostart, with a portal fallback). |
| **Start minimized (tray only when possible)** | Opens to the tray on login instead of a window. |
| **Start routing automatically when app opens** | Turns the router on at launch (on by default). |
| **Theme** | Follow the desktop, or force Light/Dark. |
| **Close to tray** | Closing the window hides it in the tray instead of quitting. |
| **Auto‑mono for single‑earbud Bluetooth** | Mixes left/right to mono when a Bluetooth device reports one channel (e.g. one earbud in the case); stays stereo when both channels are present. |
| **Use a modifier + volume keys to control the Bluetooth device** | Enables the global Bluetooth volume shortcut. Pick the modifier (Ctrl / Super / Alt). A status line shows whether the shortcut is active or was denied. |

---

## Limitations and caveats

SinkSwitch is purpose‑built for a normal Linux desktop audio setup. A few honest
boundaries:

- **Linux only.** It relies on PipeWire or PulseAudio and the desktop portals;
  there is no Windows or macOS build.
- **Bluetooth volume shortcut needs a compatible desktop.** It uses the
  Global Shortcuts portal (present on current KDE/GNOME under both Wayland and
  X11). If your desktop doesn't support it, the shortcut simply won't bind — the
  status line tells you — and you can still set Bluetooth volume from your sound
  settings. The rest of the app is unaffected.
- **It routes streams that are playing.** An app that already locked its audio to
  a device before routing started may need a quick manual re‑route (select it in
  Active Streams and click a target). New streams are caught automatically.
- **App detection is name‑based.** Most native apps are identified cleanly.
  Apps that hide behind a generic host (some Wine/Proton games, or browsers where
  every tab looks the same) may not match a rule by name — for those, use the
  one‑click quick route.
- **Auto‑generated rules are a starting point.** They're based on device type and
  common app names; glance at them and adjust to taste.
- **One Bluetooth target at a time.** The managed Bluetooth output follows the
  Bluetooth device your rules route to. If you switch which earbuds you use,
  update the rule's target (or re‑run Auto‑Generate).
- **No capture/recording, no system‑wide EQ.** SinkSwitch moves existing playback
  streams between outputs; it does not process or record audio.

---

## Intended uses

- Keep a video call or music on Bluetooth earbuds while game audio and system
  notifications stay on the speakers.
- Send meetings to a USB headset and music to Bluetooth — automatically.
- Route a specific app (a browser tab, a media player) to the HDMI TV.
- Throw the currently focused app to Bluetooth with a single click, temporarily
  or permanently.
- Quiet the earbuds with one shortcut while the speaker volume keys keep doing
  their normal job.

---

## Install

### Option A — GitHub release (Flatpak)

From [Releases](https://github.com/crashman79/sinkswitch/releases), download
**`sinkswitch-<version>-x86_64.flatpak`**, then:

```bash
flatpak install --user ./sinkswitch-<version>-x86_64.flatpak
flatpak run io.github.crashman79.sinkswitch
```

### Option B — Flatpak (build from source)

See **[flatpak/README.md](flatpak/README.md)**. After
`flatpak-builder --install`, run `flatpak run io.github.crashman79.sinkswitch`.

### Option C — From source or a virtual environment

With Python 3.8+ and the dependencies from `requirements.txt`:

```bash
pip install -r requirements.txt
python3 run_app.py
```

Config and behavior are identical; the config directory is
`~/.config/sinkswitch/` (override with the `AUDIO_ROUTER_CONFIG` environment
variable).

### Quick Flatpak build and run (development)

Requires Flatpak, `flatpak-builder`, and the Freedesktop 24.08 runtime/SDK (see
**[flatpak/README.md](flatpak/README.md)**).

```bash
./build-and-run.sh                 # build + install + run
./build-and-run.sh --clean         # wipe the build dir first
./build-and-run.sh -- --minimized  # launch minimized (tray)
```

---

## Config and rules (optional manual editing)

- **Config directory:** `~/.config/sinkswitch/` (or `AUDIO_ROUTER_CONFIG`)
- **Rules file:** `config/routing_rules.yaml` inside that directory

You normally manage rules from the GUI, but the file is plain YAML if you prefer
to edit it. A rule looks like:

```yaml
routing_rules:
  - name: "Conference Apps to Bluetooth"
    applications:
      - "zoom"
      - "teams"
      - "discord"
    target_device: "bluez_output.00_02_3C_AD_09_85.1"
    enable_default_fallback: true
```

- `applications` — app names or keywords to match.
- `target_device` — the device name from `pactl list sinks` (the **Name:** line).
- `enable_default_fallback` — if the target isn't connected, use the default
  output instead of going silent.

See `examples/` for more samples. To find device names:
`pactl list sinks | grep -i "Name:"`.

---

## Command line (advanced)

With the repository on your `PYTHONPATH` (or from the repo root), the engine can
be driven without the GUI:

```bash
python3 src/audio_router.py list-devices
python3 src/audio_router.py generate-config --output config/routing_rules.yaml
python3 src/audio_router.py apply-rules config/routing_rules.yaml
python3 src/audio_router.py monitor config/routing_rules.yaml
```

The GUI runs the same routing monitor internally; these commands are optional
for scripting or debugging.

---

## Updates

When you run the built (Flatpak) binary, the **About** tab can check for new
releases on GitHub and download them in place. Update checks are only available
in the packaged build, not when running from source.

---

## For maintainers

- Pushing a tag `v*` runs the **Flatpak release** workflow: it builds
  `sinkswitch-<version>-x86_64.flatpak` and attaches it to a GitHub release.
- Before tagging, bump **`src/_version.py`** and the `<release>` entry in
  **`flatpak/io.github.crashman79.sinkswitch.metainfo.xml`** (or let CI rewrite
  them from the tag). The Flathub manifest pins the source commit, so update
  `flatpak/io.github.crashman79.sinkswitch-flathub.yml`'s `commit:` to the
  release commit for a Flathub submission.

---

## License

MIT.

The bundled application icon is derived from the KDE Breeze icon theme
(`audio-card`), licensed under LGPL-3.0-or-later / LGPL-2.1-only. See
[`data/icons/NOTICE`](data/icons/NOTICE) and the included license texts.
