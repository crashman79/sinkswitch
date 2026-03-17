# Auto-Update Implementation (Portable Spec)

This document describes exactly how auto-update is implemented in SinkSwitch so you can replicate it in another app. It uses **GitHub Releases** for detection and download and an **updater-helper script** to replace the running binary and restart.

---

## 1. Why the updater-helper pattern

On Linux you cannot safely **overwrite** a running executable (kernel returns `ETXTBSY` / "Text file busy"). So the running app must not replace itself.

**Approach used:** The main app spawns a **helper script** and exits. The helper runs in a new process (from `/tmp`), waits ~1 second for the main process to exit, then copies the new binary over the old path and exec's it. The app restarts with the new version.

---

## 2. Prerequisites

- **Releases:** Builds published as GitHub Releases; Linux binary uploaded as a **single asset** with a **fixed name** (e.g. `sinkswitch`).
- **Version:** One source of truth (e.g. `__version__ = "0.7.4"`). Release tags are `v`-prefixed.
- **Current binary path:** When frozen, the app must know its executable path (env var set by launcher).

---

## 3. Constants (per-app)

```python
GITHUB_RELEASES_API = "https://api.github.com/repos/OWNER/REPO/releases/latest"
UPDATES_CACHE_DIR = Path.home() / ".cache" / "MYAPP"
UPDATES_NEW_BINARY = UPDATES_CACHE_DIR / "MYBINARY.new"
RELEASE_ASSET_NAME = "mybinary"
```

Launcher must set e.g. `os.environ["MYAPP_LAUNCH_CMD"] = str(Path(sys.executable).resolve())` when frozen.

---

## 4. Get current binary path (frozen only)

```python
def _get_installable_binary_path() -> Optional[Path]:
    launch = os.environ.get("MYAPP_LAUNCH_CMD", "").strip()
    if not launch or " " in launch:
        return None
    p = Path(launch).resolve()
    return p if p.is_file() and os.access(p, os.X_OK) else None
```

---

## 5. Update check

GET `GITHUB_RELEASES_API`, parse `tag_name` and `assets`. Compare version tuples (strip `v`, split `.`, int). Return `(ok, message, latest_tag, download_url)`. Set `download_url` only when an asset has `name == RELEASE_ASSET_NAME`.

---

## 6. Download

GET `download_url`, write to `UPDATES_NEW_BINARY`, `chmod(0o755)`.

---

## 7. Restart to apply (updater-helper)

1. Ensure `UPDATES_NEW_BINARY.exists()` and `current = _get_installable_binary_path()`.
2. Write a temp script (e.g. `tempfile.NamedTemporaryFile(..., delete=False)`) with:

```sh
#!/bin/sh
sleep 1
cp "$1" "$2" && chmod 755 "$2"
rm -f "$0"
exec "$2"
```

3. `chmod 0o755` the script.
4. `os.execv("/bin/sh", ["/bin/sh", script.name, str(UPDATES_NEW_BINARY), str(current)])` — main app exits; script runs, replaces binary, exec's it.

---

## 8. Launcher: cleanup on startup

When frozen and starting normally, remove `UPDATES_NEW_BINARY` if it exists so the next run doesn't use a stale update.

---

## 9. GUI

Run update check and download in a background thread; connect result to slots that update status label and show/hide "Download update" / "Restart to apply". Restart button calls `_update_restart_to_apply()`.

---

## 10. CI

Upload the binary as a release asset with **name** equal to `RELEASE_ASSET_NAME` (e.g. `files: sinkswitch`).

---

## 11. SinkSwitch reference

- Constants, _get_installable_binary_path, _update_check, _update_download, _update_restart_to_apply: `audio-router/src/audio_router_gui.py`
- LAUNCH_CMD env, cleanup .new, optional --replace-and-run: `audio-router/run_app.py`
- UpdateCheckThread, About tab update UI: `audio_router_gui.py`
