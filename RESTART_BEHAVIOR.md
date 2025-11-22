# Restart & Auto-Generation Behavior

## What Happens on System Restart

### 1. PipeWire Auto-Routing Stays Disabled ✅
The PipeWire configuration file (`~/.config/pipewire/pipewire.conf.d/99-disable-auto-routing.conf`) is a system-level configuration that persists across restarts. It ensures that:
- PipeWire's automatic stream re-routing is disabled (`do_routing=false`)
- PipeWire still detects new devices (`on_hotplug=true`)
- Streams don't automatically migrate when devices hotplug

This configuration survives reboots because it's stored in PipeWire's config directory.

### 2. Systemd Service Auto-Starts ✅
The `pipewire-router.service` systemd user service is configured with:
- `WantedBy=default.target` - automatically starts on user login
- `Restart=on-failure` - restarts if it crashes

### 3. Routing Rules Auto-Generate ✅
**This is the key behavior:** On EVERY service startup, the systemd service runs:
```
ExecStartPre=/path/to/audio_router.py generate-config config/routing_rules.yaml
```

This means:
- Before monitoring starts, a fresh routing config is generated
- The config reflects the **currently connected devices** at startup time
- No manual steps needed to regenerate config

### 4. Routing Rules Auto-Apply ✅
After generation completes, the service starts monitoring:
```
ExecStart=/path/to/audio_router.py monitor config/routing_rules.yaml
```

This continuously applies the routing rules to audio streams.

## Device Hotplug Behavior

### When You Plug/Unplug Devices
The `monitor` command watches for device changes every 2 seconds and applies routing rules:
- **Plug in USB headset** → Monitoring detects it, applies rules
- **Unplug USB headset** → Monitoring detects removal, applies rules with fallback
- **Connect Bluetooth** → Monitoring detects it, applies rules
- **Disconnect Bluetooth** → Monitoring detects removal, applies rules with fallback

### Important: Routing Rules Don't Auto-Update
If you plug/unplug devices, the existing rules still apply. They don't regenerate while monitoring.
- If you plug in a new USB headset with a different name, it won't be in the routing rules until the service restarts
- To regenerate config for new hardware: `systemctl --user restart pipewire-router`

## Startup Scenarios

### Scenario 1: Reboot with USB headset plugged in
1. PipeWire starts → auto-routing disabled ✓
2. pipewire-router service starts
3. `ExecStartPre`: Detects USB headset + Bluetooth + speakers → generates routing rules
4. `ExecStart`: Monitoring begins with fresh rules

**Result:** ✅ Browsers/music route to Bluetooth, games use USB headset default

### Scenario 2: Reboot without USB headset, then plug it in later
1. PipeWire starts → auto-routing disabled ✓
2. pipewire-router service starts
3. `ExecStartPre`: Detects only Bluetooth + speakers → generates routing rules without USB
4. `ExecStart`: Monitoring begins
5. You plug in USB headset
6. Monitoring applies rules → but USB not in rules, uses fallback (goes to default)

**To fix:** `systemctl --user restart pipewire-router` - regenerates config with USB headset

### Scenario 3: Reboot, devices auto-connect, all working
1. PipeWire starts, reconnects all previously-paired Bluetooth devices
2. pipewire-router service starts
3. `ExecStartPre`: Detects all devices → generates routing rules
4. `ExecStart`: Monitoring applies rules

**Result:** ✅ Everything works automatically

## Configuration Regeneration

### When Config Auto-Regenerates
- ✅ Every systemd service restart
- ✅ On every reboot (service starts automatically)
- ✅ When you run `./install.sh` (installation generates initial config)

### When Config DOESN'T Auto-Regenerate
- ❌ While monitoring is running (plugging/unplugging devices)
- ❌ When new applications are detected (uses existing rules)

### Manual Regeneration
To regenerate config based on current hardware:
```bash
# Via Python directly
~/.config/pipewire-router/venv/bin/python3 \
  ~/.config/pipewire-router/src/audio_router.py \
  generate-config \
  ~/.config/pipewire-router/config/routing_rules.yaml

# Or restart the service
systemctl --user restart pipewire-router
```

## Auto-Routing (PipeWire's) vs Manual Routing (Our System)

| Feature | PipeWire Auto-Routing | Our Manual Routing |
|---------|----------------------|-------------------|
| Behavior | Moves ALL streams to new device automatically | Applies user-defined rules |
| Problem | Moves games/WoW to Bluetooth earbuds (bad) | Can't force migration, only applies to new streams |
| Solution | **DISABLED** | Always-active monitoring of device changes |
| Restart Behavior | Rebuilds routing on startup | Generates fresh config every startup |

Our system is disabled because PipeWire's auto-routing was moving game audio incorrectly. Our approach is safer - rules are explicit and only apply to matching applications.

## Verification

To verify the system is working on restart:

```bash
# Check service is running
systemctl --user status pipewire-router --no-pager

# Check logs for auto-generation
journalctl --user -u pipewire-router --no-pager -n 50

# Should see: "DETECTED AUDIO DEVICES:" and "GENERATED ROUTING RULES:"
```

## Summary

✅ **Yes, the system fully reactivates after restart:**
- PipeWire auto-routing stays disabled
- Systemd service auto-starts
- Routing rules auto-generate based on currently connected devices
- Monitoring auto-applies rules to audio streams
- No manual intervention needed
