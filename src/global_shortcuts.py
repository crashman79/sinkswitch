"""Bluetooth volume control via the Global Shortcuts portal.

SinkSwitch redirects Bluetooth audio while the desktop environment keeps
controlling the main/speaker volume with the plain multimedia keys. This module
adds a *modifier + volume key* shortcut (e.g. Ctrl+VolumeUp) that adjusts the
Bluetooth device volume without hijacking the OS keys: the DE still owns the
unmodified keys.

The portal's ``BindShortcuts`` method takes an ``a(sa{sv})`` argument. PyQt6's
QtDBus cannot marshal that signature from Python, so the portal conversation
runs on a small worker thread using jeepney, a pure-Python D-Bus client. All
failures degrade gracefully: if the portal is unavailable or the user denies
the binding, the controller reports a status and does nothing else.
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

try:
    from jeepney import DBusAddress, MatchRule, new_method_call
    from jeepney.io.blocking import open_dbus_connection
    _JEEPNEY_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on packaging
    DBusAddress = None  # type: ignore[assignment]
    MatchRule = None  # type: ignore[assignment]
    new_method_call = None  # type: ignore[assignment]
    open_dbus_connection = None  # type: ignore[assignment]
    _JEEPNEY_AVAILABLE = False

logger = logging.getLogger(__name__)

PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
PORTAL_IFACE = "org.freedesktop.portal.GlobalShortcuts"
REQUEST_IFACE = "org.freedesktop.portal.Request"
SESSION_IFACE = "org.freedesktop.portal.Session"

# Application-provided shortcut IDs (stable; shown in the portal dialog).
SC_VOL_UP = "bt_volume_up"
SC_VOL_DOWN = "bt_volume_down"
SC_MUTE = "bt_mute"

# XF86 multimedia key names used as the base trigger (modifier is prefixed).
_AUDIO_KEYS = {
    SC_VOL_UP: "XF86AudioRaiseVolume",
    SC_VOL_DOWN: "XF86AudioLowerVolume",
    SC_MUTE: "XF86AudioMute",
}

# User-facing modifier -> xkbcommon modifier name used by the XDG shortcuts
# specification (modifiers and keysyms joined with '+').
MODIFIER_PREFIX = {
    "Ctrl": "CTRL+",
    "Super": "LOGO+",
    "Alt": "ALT+",
    "Win": "LOGO+",
}

_DESCRIPTIONS = {
    SC_VOL_UP: "Raise Bluetooth volume",
    SC_VOL_DOWN: "Lower Bluetooth volume",
    SC_MUTE: "Mute or unmute Bluetooth",
}

# Shortcut ID -> the engine action it triggers.
ACTION_VOLUME_UP = "volume_up"
ACTION_VOLUME_DOWN = "volume_down"
ACTION_MUTE = "mute"

_SHORTCUT_TO_ACTION = {
    SC_VOL_UP: ACTION_VOLUME_UP,
    SC_VOL_DOWN: ACTION_VOLUME_DOWN,
    SC_MUTE: ACTION_MUTE,
}


def _trigger(modifier: str, key: str) -> str:
    prefix = MODIFIER_PREFIX.get(modifier, "<Ctrl>")
    return f"{prefix}{key}"


def _token(prefix: str = "sw") -> str:
    return prefix + secrets.token_hex(6)


def _variant_value(value: Any) -> Any:
    """Unwrap jeepney's ``(signature, value)`` variant representation."""
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
        return value[1]
    return value


class GlobalShortcutsController(QObject):
    """Bind modifier+volume global shortcuts that drive Bluetooth volume.

    Handlers map a logical action (``volume_up`` / ``volume_down`` / ``mute``) to
    a zero-argument callable supplied by the caller (typically the GUI wiring the
    action to ``engine.adjust_bluetooth_volume`` / ``engine.toggle_bluetooth_mute``).
    """

    activated = pyqtSignal(str)
    status_changed = pyqtSignal(str, str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._handlers: Dict[str, Callable[[], None]] = {}
        self._status_cb: Optional[Callable[[str, str], None]] = None
        self._available = False
        self._bound_shortcuts: List[Tuple[str, Dict[str, str]]] = []
        self._session_handle: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.status_changed.connect(self._on_status_changed)
        self.activated.connect(self._on_activated_action)

    # -- public API -------------------------------------------------------
    def set_status_callback(self, cb: Callable[[str, str], None]) -> None:
        """Register a callback invoked with (level, message); level in
        {ok, warn, error}."""
        self._status_cb = cb

    @property
    def available(self) -> bool:
        return self._available

    @property
    def bound_shortcuts(self) -> List[Tuple[str, Dict[str, str]]]:
        return list(self._bound_shortcuts)

    def start(self, handlers: Dict[str, Callable[[], None]], modifier: str = "Ctrl") -> bool:
        """Start a GlobalShortcuts session and bind the volume shortcuts.

        Returns True if the worker was started; the actual grant (or denial)
        arrives later via the status callback.
        """
        self.stop()

        if not _JEEPNEY_AVAILABLE:
            self._report(
                "error",
                "Global shortcuts need the 'jeepney' package; install it or use the Flatpak build",
            )
            return False

        self._handlers = dict(handlers)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            args=(modifier,),
            name="GlobalShortcuts",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        """Close the session and release any bound shortcuts."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
        self._thread = None
        self._available = False
        self._bound_shortcuts = []

    # -- Qt-thread dispatch ----------------------------------------------
    def _on_status_changed(self, level: str, message: str) -> None:
        cb = self._status_cb
        if cb is None:
            return
        try:
            cb(level, message)
        except Exception:
            logger.debug("GlobalShortcuts status callback failed", exc_info=True)

    def _on_activated_action(self, action: str) -> None:
        handler = self._handlers.get(action)
        if handler is None:
            return
        try:
            handler()
        except Exception:
            logger.exception("Bluetooth volume shortcut handler failed")

    def _report(self, level: str, message: str) -> None:
        logger.info("GlobalShortcuts %s: %s", level, message)
        self.status_changed.emit(level, message)

    # -- worker -----------------------------------------------------------
    def _run(self, modifier: str) -> None:
        conn = None
        session = None
        try:
            conn = open_dbus_connection(bus="SESSION")
            self._report(
                "warn",
                "Approve the desktop's shortcut dialog to bind Bluetooth volume shortcuts...",
            )
            session = self._create_session(conn)
            if not session:
                return
            self._session_handle = session
            if not self._bind(conn, session, modifier):
                return
            self._available = True
            self._listen(conn, session)
        except Exception as e:
            logger.exception("GlobalShortcuts worker failed")
            self._report("error", f"Global shortcuts failed: {e}")
        finally:
            self._available = False
            self._session_handle = None
            if conn is not None:
                if session:
                    self._close_session(conn, session)
                try:
                    conn.close()
                except Exception:
                    pass

    def _create_session(self, conn) -> Optional[str]:
        options = {
            "handle_token": ("s", _token()),
            "session_handle_token": ("s", _token()),
        }
        reply = conn.send_and_get_reply(
            new_method_call(
                DBusAddress(
                    PORTAL_PATH,
                    bus_name=PORTAL_SERVICE,
                    interface=PORTAL_IFACE,
                ),
                "CreateSession",
                "a{sv}",
                (options,),
            )
        )
        request_path = reply.body[0]
        message = self._wait_for_response(conn, request_path, timeout=15.0)
        if message is None:
            self._report("error", "Portal did not answer the shortcut session request")
            return None
        code, results = self._response_parts(message)
        if code != 0:
            self._report("warn", "Shortcut session cancelled or denied by the system")
            return None
        session = _variant_value(results.get("session_handle"))
        if not session:
            self._report("error", "Portal did not return a shortcut session")
            return None
        return str(session)

    def _bind(self, conn, session: str, modifier: str) -> bool:
        shortcuts = [
            (
                sid,
                {
                    "description": ("s", _DESCRIPTIONS[sid]),
                    "preferred_trigger": (
                        "s",
                        _trigger(modifier, _AUDIO_KEYS[sid]),
                    ),
                },
            )
            for sid in (SC_VOL_UP, SC_VOL_DOWN, SC_MUTE)
        ]
        options = {"handle_token": ("s", _token())}
        reply = conn.send_and_get_reply(
            new_method_call(
                DBusAddress(
                    PORTAL_PATH,
                    bus_name=PORTAL_SERVICE,
                    interface=PORTAL_IFACE,
                ),
                "BindShortcuts",
                "oa(sa{sv})sa{sv}",
                (session, shortcuts, "", options),
            )
        )
        request_path = reply.body[0]
        message = self._wait_for_response(conn, request_path, timeout=600.0)
        if message is None:
            self._report(
                "warn",
                "No response from the shortcut dialog. Apply again, or assign the "
                "Bluetooth volume shortcuts in System Settings → Shortcuts.",
            )
            return False
        code, results = self._response_parts(message)
        if code != 0:
            self._report("warn", "Shortcut binding cancelled or denied by the system")
            return False
        bound = _variant_value(results.get("shortcuts")) or []
        self._bound_shortcuts = list(bound)
        if not bound:
            self._report(
                "warn",
                "Portal bound no shortcuts; check your desktop keybinding settings",
            )
            return False

        assigned: List[str] = []
        unassigned: List[str] = []
        for entry in bound:
            props = entry[1] if isinstance(entry, (list, tuple)) and len(entry) > 1 else {}
            trigger = _variant_value(props.get("trigger_description")) if isinstance(props, dict) else ""
            description = (
                _variant_value(props.get("description")) if isinstance(props, dict) else ""
            )
            label = str(description or entry[0])
            if trigger:
                assigned.append(f"{label} ({trigger})")
            else:
                unassigned.append(label)

        if assigned:
            message = "Bluetooth volume shortcuts active: " + ", ".join(assigned)
            if unassigned:
                message += (
                    ". Not assigned: "
                    + ", ".join(unassigned)
                    + " — open System Settings → Shortcuts to assign them"
                )
            self._report("ok", message)
        else:
            self._report(
                "warn",
                "Shortcuts registered but no keys assigned. Open System Settings → "
                "Shortcuts and assign the SoundCorral Bluetooth volume shortcuts.",
            )
        return True

    def _listen(self, conn, session: str) -> None:
        rule = MatchRule(
            type="signal",
            interface=PORTAL_IFACE,
            member="Activated",
            path=session,
        )
        with conn.filter(rule) as queue:
            while not self._stop_event.is_set():
                try:
                    message = conn.recv_until_filtered(queue, timeout=1.0)
                except TimeoutError:
                    continue
                except Exception:
                    logger.debug("GlobalShortcuts listener stopped", exc_info=True)
                    return
                args = message.body
                if len(args) < 2:
                    continue
                shortcut_id = _variant_value(args[1])
                action = _SHORTCUT_TO_ACTION.get(str(shortcut_id))
                if action:
                    self.activated.emit(action)

    def _wait_for_response(self, conn, request_path: str, timeout: float):
        rule = MatchRule(
            type="signal",
            interface=REQUEST_IFACE,
            member="Response",
            path=request_path,
        )
        deadline = time.monotonic() + max(0.1, timeout)
        with conn.filter(rule) as queue:
            while not self._stop_event.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                try:
                    return conn.recv_until_filtered(queue, timeout=min(1.0, remaining))
                except TimeoutError:
                    continue
        return None

    @staticmethod
    def _response_parts(message) -> Tuple[int, Dict[str, Any]]:
        args = message.body
        if not isinstance(args, (list, tuple)) or len(args) < 2:
            return -1, {}
        try:
            code = int(args[0])
        except (TypeError, ValueError):
            code = -1
        results = args[1] if isinstance(args[1], dict) else {}
        return code, results

    @staticmethod
    def _shortcut_label(entry: Any) -> str:
        if isinstance(entry, (list, tuple)) and len(entry) > 1 and isinstance(entry[1], dict):
            props = entry[1]
            label = (
                _variant_value(props.get("trigger_description"))
                or _variant_value(props.get("description"))
                or entry[0]
            )
            return str(label)
        return str(_variant_value(entry))

    @staticmethod
    def _close_session(conn, session: str) -> None:
        try:
            conn.send_and_get_reply(
                new_method_call(
                    DBusAddress(
                        session,
                        bus_name=PORTAL_SERVICE,
                        interface=SESSION_IFACE,
                    ),
                    "Close",
                    "",
                    (),
                ),
                timeout=2.0,
            )
        except Exception:
            pass
