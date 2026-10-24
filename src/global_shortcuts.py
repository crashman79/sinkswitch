"""Bluetooth volume control via the Global Shortcuts portal.

SoundCorral redirects Bluetooth audio while the desktop environment keeps
controlling the main/speaker volume with the plain multimedia keys. This module
adds a *modifier + volume key* shortcut (e.g. Ctrl+VolumeUp) that adjusts the
Bluetooth device volume without hijacking the OS keys: the DE still owns the
unmodified keys.

It uses version 2 of ``org.freedesktop.portal.GlobalShortcuts`` over QtDBus,
following the same conventions as ``portal_background.py``. All failures degrade
gracefully: if the portal is unavailable or the user denies the binding, the
controller reports a status and does nothing else.
"""
from __future__ import annotations

import logging
import secrets
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtDBus import (
    QDBusConnection,
    QDBusInterface,
    QDBusMessage,
    QDBusPendingCallWatcher,
    QDBusPendingReply,
)

PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
PORTAL_IFACE = "org.freedesktop.portal.GlobalShortcuts"

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

# User-facing modifier -> GTK accelerator prefix understood by the portal.
MODIFIER_PREFIX = {
    "Ctrl": "<Ctrl>",
    "Super": "<Super>",
    "Alt": "<Alt>",
    "Win": "<Super>",
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


class GlobalShortcutsController(QObject):
    """Bind modifier+volume global shortcuts that drive Bluetooth volume.

    Handlers map a logical action (``volume_up`` / ``volume_down`` / ``mute``) to
    a zero-argument callable supplied by the caller (typically the GUI wiring the
    action to ``engine.adjust_bluetooth_volume`` / ``engine.toggle_bluetooth_mute``).
    """

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._bus = QDBusConnection.sessionBus()
        self._session_handle: Optional[str] = None
        self._active_request_path: Optional[str] = None
        self._handlers: Dict[str, Callable[[], None]] = {}
        self._triggers: Dict[str, str] = {}
        self._available = False
        self._bound_shortcuts: List[Tuple[str, Dict[str, str]]] = []
        self._activated_connected = False
        self._status_cb: Optional[Callable[[str, str], None]] = None

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
        """Create a GlobalShortcuts session and bind the volume shortcuts.

        Returns True if the portal call was dispatched (the actual grant arrives
        later via the status callback). Returns False if the bus or portal is
        unavailable.
        """
        if self._available or self._session_handle or self._active_request_path:
            # Already active: close the previous session before rebinding.
            self.stop()

        if not self._bus.isConnected():
            self._report("error", "D-Bus session bus is not connected")
            return False

        iface = QDBusInterface(PORTAL_SERVICE, PORTAL_PATH, PORTAL_IFACE, self._bus)
        if not iface.isValid():
            self._report("error", "GlobalShortcuts portal is not available on this system")
            return False

        self._handlers = dict(handlers)
        self._triggers = {
            sid: _trigger(modifier, key) for sid, key in _AUDIO_KEYS.items()
        }

        app_token = "sw" + secrets.token_hex(6)
        session_token = "sw" + secrets.token_hex(6)
        opts = {
            "handle_token": app_token,
            "session_handle_token": session_token,
        }

        msg = QDBusMessage.createMethodCall(
            PORTAL_SERVICE, PORTAL_PATH, PORTAL_IFACE, "CreateSession"
        )
        msg.setArguments([opts])
        self._dispatch(msg)
        return True

    def stop(self) -> None:
        """Close the session and release any bound shortcuts."""
        if self._activated_connected and self._session_handle:
            try:
                self._bus.disconnect(
                    PORTAL_SERVICE,
                    self._session_handle,
                    PORTAL_IFACE,
                    "Activated",
                    self._on_activated,
                )
            except Exception:
                pass
            self._activated_connected = False
        if self._active_request_path:
            try:
                self._bus.disconnect(
                    PORTAL_SERVICE,
                    self._active_request_path,
                    "org.freedesktop.portal.Request",
                    "Response",
                    self._on_response,
                )
            except Exception:
                pass
            self._active_request_path = None
        if self._session_handle:
            try:
                iface = QDBusInterface(
                    PORTAL_SERVICE,
                    self._session_handle,
                    "org.freedesktop.portal.Session",
                    self._bus,
                )
                iface.call("Close")
            except Exception:
                logger.debug("Failed to close GlobalShortcuts session", exc_info=True)
        self._session_handle = None
        self._available = False
        self._bound_shortcuts = []

    # -- internals --------------------------------------------------------
    def _report(self, level: str, message: str) -> None:
        logger.info("GlobalShortcuts %s: %s", level, message)
        if self._status_cb:
            try:
                self._status_cb(level, message)
            except Exception:
                pass

    def _dispatch(self, msg: QDBusMessage) -> None:
        """asyncCall and watch for completion; connect Request.Response on the
        returned request handle so the actual result (session/shortcuts) arrives
        via :meth:`_on_response`."""
        pending = self._bus.asyncCall(msg)
        watcher = QDBusPendingCallWatcher(pending)
        watcher.finished.connect(lambda _w=watcher: self._on_pending(watcher))

    def _on_pending(self, watcher: QDBusPendingCallWatcher) -> None:
        watcher.deleteLater()
        pr = QDBusPendingReply(watcher)
        if not pr.isFinished():
            self._report("error", "Portal call did not complete")
            return
        if pr.isError():
            self._report("error", f"Portal call failed: {pr.error().message()}")
            return
        reply = pr.reply()
        if reply.type() != QDBusMessage.MessageType.ReplyMessage:
            self._report("error", "Portal returned no reply")
            return
        args = reply.arguments()
        if not args:
            self._report("error", "Portal returned an empty reply")
            return
        h = args[0]
        path = h.path() if hasattr(h, "path") else str(h)
        self._active_request_path = path
        if not self._bus.connect(
            PORTAL_SERVICE,
            path,
            "org.freedesktop.portal.Request",
            "Response",
            self._on_response,
        ):
            self._report("error", "Could not listen for portal response")

    @pyqtSlot(QDBusMessage)
    def _on_response(self, message: QDBusMessage) -> None:
        # A portal Request is one-shot; drop its Response connection now.
        old = self._active_request_path
        self._active_request_path = None
        if old:
            try:
                self._bus.disconnect(
                    PORTAL_SERVICE,
                    old,
                    "org.freedesktop.portal.Request",
                    "Response",
                    self._on_response,
                )
            except Exception:
                pass

        args = message.arguments()
        if len(args) < 2:
            return
        try:
            response_code = int(args[0])
        except (TypeError, ValueError):
            return
        results = args[1] if isinstance(args[1], dict) else {}

        if response_code != 0:
            self._report("warn", "Shortcut binding cancelled or denied by the system")
            return

        if "session_handle" in results:
            self._on_create_response(results)
        elif "shortcuts" in results:
            self._on_bind_response(results)

    def _on_create_response(self, results: Dict) -> None:
        handle = results.get("session_handle")
        if not handle:
            self._report("error", "Portal did not return a session handle")
            return
        self._session_handle = str(handle)
        if not self._bus.connect(
            PORTAL_SERVICE,
            self._session_handle,
            PORTAL_IFACE,
            "Activated",
            self._on_activated,
        ):
            self._report("error", "Could not listen for shortcut activations")
            return
        self._activated_connected = True
        self._bind()

    def _bind(self) -> None:
        if not self._session_handle:
            return
        shortcuts = [
            (
                sid,
                {
                    "description": _DESCRIPTIONS[sid],
                    "preferred_trigger": self._triggers.get(sid, ""),
                },
            )
            for sid in (SC_VOL_UP, SC_VOL_DOWN, SC_MUTE)
        ]
        bind_token = "sw" + secrets.token_hex(6)
        opts = {"handle_token": bind_token}
        msg = QDBusMessage.createMethodCall(
            PORTAL_SERVICE, PORTAL_PATH, PORTAL_IFACE, "BindShortcuts"
        )
        # BindShortcuts(o session_handle, a(sa{sv}) shortcuts, s parent_window, a{sv} options)
        msg.setArguments([self._session_handle, shortcuts, "", opts])
        self._dispatch(msg)

    def _on_bind_response(self, results: Dict) -> None:
        self._bound_shortcuts = results.get("shortcuts", []) or []
        if self._bound_shortcuts:
            self._available = True
            labels = [
                self._shortcut_label(s) for s in self._bound_shortcuts
            ]
            self._report(
                "ok",
                "Bluetooth volume shortcuts active: " + ", ".join(labels),
            )
        else:
            self._report(
                "warn",
                "Portal bound no shortcuts; check your desktop keybinding settings",
            )

    @staticmethod
    def _shortcut_label(entry) -> str:
        if isinstance(entry, (list, tuple)) and len(entry) > 1 and isinstance(entry[1], dict):
            return entry[1].get("trigger_description", entry[0])
        return str(entry)

    @pyqtSlot(QDBusMessage)
    def _on_activated(self, message: QDBusMessage) -> None:
        args = message.arguments()
        # Activated(o session_handle, s shortcut_id, t timestamp, a{sv} options)
        if len(args) < 2:
            return
        shortcut_id = str(args[1])
        action = _SHORTCUT_TO_ACTION.get(shortcut_id)
        handler = self._handlers.get(action) if action else None
        if handler is None:
            return
        try:
            handler()
        except Exception:
            logger.exception("Bluetooth volume shortcut handler failed")
