# SoundCorral

SoundCorral is a Linux desktop app that lets you choose where each app's audio plays. You can keep a browser on Bluetooth headphones, a game on your speakers, and a call on a USB headset at the same time, without changing the output for everything else.

Everything runs inside the app. There is no account, no cloud service, and no separate background daemon to install or manage.

## What it does

SoundCorral watches the audio streams on your system and moves them to the output you want:

- Apps that match a **routing rule** go to that rule's device.
- Apps that match no rule go to the **Default output** you choose at the top of the window.
- You can also move a single stream by hand with the quick-route buttons, either just for now (**Temporary**) or as a saved rule (**Permanent**).

It works with PipeWire or PulseAudio, through the standard system audio tools.

## Why use it

- **Per-app control.** Different programs can use different outputs at the same time.
- **Automatic routing.** Rules move matching apps whenever their audio appears, so you set it up once.
- **See what is happening.** Connected devices and active streams are shown together, with the current route for each stream.
- **Fast one-off changes.** Send the currently playing stream somewhere else in a click, temporarily or permanently.
- **Better Bluetooth handling.** Bluetooth-routed apps share one managed SoundCorral Bluetooth output, which gives you a single volume control point and allows mono mixing for single-earbud listening.
- **Quiet when nothing changes.** The lists refresh when your audio setup actually changes instead of polling constantly, so the window does not flicker.

## How routing works

The router runs in the background while the app is open. It looks at the audio streams that are currently playing and compares each app against your rules.

1. If an app matches a rule, its stream is moved to the rule's target device.
2. If an app matches no rule, its stream is moved to the current Default output.
3. If a rule's target device is unavailable (for example, a Bluetooth device that is not ready yet), SoundCorral uses the rule's fallback setting. With fallback on, matching apps go to your Default output and the rule is retried once the device becomes usable. With fallback off, matching apps stay where they are until the target is available.

Bluetooth is handled a little differently from other outputs. Instead of sending each app straight to the Bluetooth device, SoundCorral creates one managed Bluetooth output and sends all Bluetooth-routed apps through it. The app still shows the real device name, with "(mono)" added when the mono version is active. If that managed output cannot be created, routing falls back to the real Bluetooth device, so audio keeps working.

Stopping the router only stops it from managing streams. Streams that are already playing stay where they are, and new streams simply use your system default. Starting the router again reapplies your rules.

## Using the app

### The top bar

Across the top of the window you will find:

- **Router status**, which shows whether the router is running.
- **Default output**, the device used for apps that match no rule. Changing it also changes your system default output and, if the router is running, restarts it so the change takes effect immediately.
- **Force Mono: OFF / ON**, which forces the mono Bluetooth output even when the device reports stereo. When off, mono is used only if automatic single-earbud detection is enabled and a one-channel Bluetooth device is found.
- **Start / Restart** and **Stop** buttons for the router.
- **Refresh Devices** on the Devices & Streams tab, for an immediate re-scan.

### Devices & Streams

This tab has two tables.

**Devices** lists the outputs SoundCorral can see:

- a status dot (green for connected, red for disconnected, grey for unknown),
- the device name,
- the device type (Bluetooth, HDMI, analog speakers, USB, and so on),
- the internal device ID.

**Active Streams** lists what is currently playing:

- the application name,
- the output device it is on,
- the **Route** column, which tells you why it is there: a rule name, `Temporary override (device)`, `Default`, or `Unmatched (not on default)`. Bluetooth streams also show `[BT active]` or `[Mono active]`.

To move one stream by hand, select it, choose **Temporary** or **Permanent**, then click **Bluetooth**, **HDMI**, or **Analog speakers**. A quick-route button is only available when a connected device of that type exists.

- **Temporary** moves only the selected stream. It lasts while the router keeps running; stopping or restarting the router clears it.
- **Permanent** moves the stream now, then saves or updates a routing rule for that app and restarts the router so the change sticks.

### Routing Rules

This tab lists your rules and their target devices. From here you can:

- **Add** a rule,
- **Edit** or **Delete** the selected rule,
- **Auto-Generate Rules** from the devices that are currently connected,
- **Save** your changes.

A rule has a name, a list of applications, optional application keywords, a target device, and an **Enable default fallback** option. Matching is name-based: an app matches when its name contains one of the listed names, or when one of the keywords appears in the app name. Keywords are useful for apps whose reported name varies.

With **Enable default fallback** checked (the default), matching apps use your Default output while the rule's target device is unavailable, and SoundCorral retries the rule when the device comes back. When it is unchecked, matching apps wait on their current output until the target is available. The rules list shows this setting as `[AUTO]` (fallback on) or `[LOCKED]` (fallback off).

On first run, SoundCorral creates a starter set of rules based on the devices it finds. Treat those as a starting point and adjust them to suit your setup.

### Logs

A log view of what the router is doing, with **Refresh** and **Clear** buttons. This is the first place to look if an app is not going where you expect.

### Settings

Startup, appearance, tray behavior, Bluetooth mono handling, and the optional Bluetooth volume shortcut are all configured here. See the settings list below.

### About

Shows the app version, where your configuration is stored, and how many rules you have. It also has an update check, which works in the packaged build but not when running from source.

### System tray

If your desktop provides a system tray, SoundCorral adds an icon with **Show**, **Start router** / **Restart router**, **Stop router**, and **Quit**. If you enable **Close to tray**, closing the window hides it instead of quitting. SoundCorral allows only one running copy at a time.

## Getting started

1. Launch SoundCorral. Routing starts automatically by default.
2. Pick the **Default output** you want for apps that do not match a rule.
3. Connect your devices (Bluetooth, USB, HDMI, speakers) and click **Refresh Devices** if they do not appear.
4. Open **Routing Rules** and either adjust the starter rules or click **Auto-Generate Rules**.
5. Play something and check the **Active Streams** table. If an app is in the wrong place, select it and use a quick-route button, or add a rule for it.

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| Start SoundCorral when I log in | Off | Adds SoundCorral to your login startup. |
| Start minimized (tray only when possible) | Off | Starts the app hidden in the tray at login. Available once login startup is enabled. |
| Start routing automatically when app opens | On | Starts the router as soon as SoundCorral launches. |
| Theme | System (follow desktop) | Follows your desktop theme, or forces Light or Dark. |
| Close to tray | Off | Closing the window hides it in the tray instead of quitting. |
| Auto-mono for single-earbud Bluetooth | On | Mixes stereo to mono when a one-channel Bluetooth output is detected; keeps stereo when both channels are available. |
| Use global shortcuts to control the Bluetooth device | On | Enables the optional Bluetooth volume shortcuts described below. |

### Bluetooth volume shortcuts

If you want a shortcut that changes only the Bluetooth device's volume while the plain volume keys keep controlling your speakers, enable **Use global shortcuts to control the Bluetooth device**.

SoundCorral suggests **Ctrl+Volume Up**, **Ctrl+Volume Down**, and **Ctrl+Volume Mute**, but the actual keys are assigned in your desktop's shortcut settings:

1. Enable the option and click **Apply and save**.
2. Your desktop may show a shortcut approval/configuration dialog. Approve the three SoundCorral shortcuts.
3. If the dialog does not appear, click **Open shortcut settings** in SoundCorral, or open **System Settings → Shortcuts**, find **SoundCorral**, and assign:
   - Raise Bluetooth volume → `Ctrl+Volume Up`
   - Lower Bluetooth volume → `Ctrl+Volume Down`
   - Mute or unmute Bluetooth → `Ctrl+Volume Mute`
4. The status line under the setting tells you whether the keys are active.

Plain volume keys still control your speakers through your desktop as usual. The shortcuts control only the Bluetooth device, not the system default output. This uses the desktop's Global Shortcuts portal; a bare modifier alone is not supported, so the shortcut must be a key combination. If the portal is unavailable or you deny the request, the rest of the app still works normally.

## Rules file

Rules are stored as plain YAML in:

```
~/.config/sinkswitch/config/routing_rules.yaml
```

The folder keeps the original `sinkswitch` name (the internal app ID), so existing settings continue to work after the display-name change. You can set the `AUDIO_ROUTER_CONFIG` environment variable to use a different folder. Editing the file by hand is optional; the app writes it when you add, edit, or quick-route rules.

A rule looks like this:

```yaml
routing_rules:
  - name: Browser to Bluetooth
    applications:
      - firefox
      - chromium
    application_keywords:
      - browser
    target_device: bluez_output.XX_XX_XX_XX_XX_XX.1
    enable_default_fallback: true
```

The target device is the internal device name shown in the Devices table.

## Things to know

- **Linux only**, and it needs PipeWire or PulseAudio with the usual command-line audio tools available.
- **It routes streams that are playing.** If an app started and locked itself to a device before the router was running, a quick re-route will usually fix it.
- **Detection is name-based.** Launchers and compatibility layers such as Wine or Proton, and some browsers, may report generic names. If an app does not match automatically, add a keyword or use the quick-route buttons.
- **One Bluetooth target at a time.** All Bluetooth-routed apps share the single managed Bluetooth output.
- **Stopping does not undo routes.** Already-playing streams stay on their current output; only new streams return to the system default until you start the router again.
- **Temporary routes are temporary.** They are cleared when the router stops or restarts.
- **The Bluetooth volume shortcut needs desktop support** for the Global Shortcuts portal. If your desktop does not provide it, the shortcut will not bind. If your desktop does support it but does not assign the keys automatically, use **System Settings → Shortcuts** to assign them.
- **Hand-edited rules are read when the app loads them**, so save and restart the router after changing the file while the app is open.
- **SoundCorral does not record, process, or upload audio.** It only moves streams between outputs.
- **Update checks only work in the packaged build**, not when running from source.

## Install

### Option A: Flatpak release bundle

Download `sinkswitch-<version>-x86_64.flatpak` from the [GitHub Releases](https://github.com/crashman79/sinkswitch/releases) page, then install and launch it:

```bash
flatpak install --user ./sinkswitch-<version>-x86_64.flatpak
flatpak run io.github.crashman79.sinkswitch
```

### Option B: Build the Flatpak from source

With Flatpak and `flatpak-builder` installed, run this from the source checkout:

```bash
./build-and-run.sh
```

The helper installs any missing runtime or SDK, builds the app, and launches it.

### Option C: Run from source

With Python 3 and the system audio tools installed:

```bash
python3 -m pip install -r requirements.txt
python3 run_app.py
```

This is also the usual path for development.

## Development

SoundCorral is developed and maintained by its author. GitHub Copilot and OpenCode have been used for development, diagnostic debugging, and troubleshooting. All changes are reviewed and tested before release.

## License

SoundCorral is released under the **MIT License**.

The bundled application icon is derived from KDE's Breeze icon theme and is provided under its own LGPL terms (LGPL-3.0-or-later and LGPL-2.1-only). See the included icon notices for details.
