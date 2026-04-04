"""Flatpak: login autostart via org.freedesktop.portal.Background (RequestBackground)."""
from __future__ import annotations

import logging
import secrets
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtDBus import (
    QDBusConnection,
    QDBusError,
    QDBusInterface,
    QDBusMessage,
    QDBusPendingCallWatcher,
    QDBusPendingReply,
)

try:
    from PyQt6.QtGui import QGuiApplication, QNativeInterface
except ImportError:  # pragma: no cover
    QGuiApplication = None  # type: ignore[misc, assignment]
    QNativeInterface = None  # type: ignore[misc, assignment]


def portal_parent_window(widget) -> str:
    """Window identifier for xdg-desktop-portal (empty string is valid)."""
    try:
        wh = widget.windowHandle()
        if wh is None or QGuiApplication is None or QNativeInterface is None:
            return ""
        xapp = QGuiApplication.nativeInterface(QNativeInterface.QX11Application)
        if xapp is not None and getattr(xapp, "display", lambda: None)():
            return f"x11:{hex(int(wh.winId()))}"
    except Exception:
        pass
    return ""


def _flatpak_commandline(start_minimized: bool) -> List[str]:
    # Portal prepends flatpak run; use the desktop entry Exec name + args.
    cl = ["sinkswitch"]
    if start_minimized:
        cl.append("--minimized")
    return cl


class PortalBackgroundRequest(QObject):
    """Async RequestBackground + listen for org.freedesktop.portal.Request::Response."""

    def __init__(
        self,
        parent: Optional[QObject],
        parent_window: str,
        autostart: bool,
        start_minimized: bool,
        on_done: Callable[[bool, str], None],
    ):
        super().__init__(parent)
        self._on_done = on_done
        self._requested_autostart = autostart
        self._handle_path: Optional[str] = None
        self._bus = QDBusConnection.sessionBus()
        self._connected = False

        token = "sw" + secrets.token_hex(6)
        reason = (
            "Start SinkSwitch at login so audio routing rules apply automatically."
            if autostart
            else "Do not start SinkSwitch automatically at login."
        )
        opts = {
            "handle_token": token,
            "reason": reason,
            "autostart": autostart,
            "commandline": _flatpak_commandline(start_minimized),
        }
        msg = QDBusMessage.createMethodCall(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Background",
            "RequestBackground",
        )
        msg.setArguments([parent_window, opts])

        pending = self._bus.asyncCall(msg)
        self._watcher = QDBusPendingCallWatcher(pending)
        self._watcher.setParent(self)
        self._watcher.finished.connect(self._on_request_finished)

    def _on_request_finished(self, watcher: QDBusPendingCallWatcher) -> None:
        pending = watcher.pendingCall()
        watcher.deleteLater()
        pr = QDBusPendingReply(pending)
        if not pr.isFinished():
            self._finish(False, "Portal call did not complete.")
            return
        if pr.isError():
            de: QDBusError = pr.error()
            err = de.message() if de.type() != QDBusError.ErrorType.NoError else "unknown D-Bus error"
            self._finish(False, f"Portal error: {err}")
            return
        reply = pr.reply()

        if reply.type() != QDBusMessage.Type.ReplyMessage:
            err = reply.errorMessage() or "unknown D-Bus error"
            logger.warning("RequestBackground failed: %s", err)
            self._finish(False, f"Could not open system dialog: {err}")
            return
        args = reply.arguments()
        if not args:
            self._finish(False, "Portal returned an empty reply.")
            return
        h = args[0]
        path = h.path() if hasattr(h, "path") else str(h)
        self._handle_path = path
        ok = self._bus.connect(
            "org.freedesktop.portal.Desktop",
            path,
            "org.freedesktop.portal.Request",
            "Response",
            self._on_response,
        )
        if not ok:
            self._finish(False, "Could not listen for portal response.")
            return
        self._connected = True

    def _finish(self, ok: bool, message: str) -> None:
        self._disconnect_response()
        self._close_request()
        try:
            self._on_done(ok, message)
        except Exception:
            logger.exception("portal on_done failed")
        self.deleteLater()

    def _disconnect_response(self) -> None:
        if self._connected and self._handle_path:
            try:
                self._bus.disconnect(
                    "org.freedesktop.portal.Desktop",
                    self._handle_path,
                    "org.freedesktop.portal.Request",
                    "Response",
                    self._on_response,
                )
            except Exception:
                pass
            self._connected = False

    def _close_request(self) -> None:
        if not self._handle_path:
            return
        try:
            iface = QDBusInterface(
                "org.freedesktop.portal.Desktop",
                self._handle_path,
                "org.freedesktop.portal.Request",
                self._bus,
            )
            iface.call("Close")
        except Exception:
            pass

    @pyqtSlot("uint", "QVariantMap")
    def _on_response(self, response: int, results: dict) -> None:
        if int(response) != 0:
            self._finish(False, "Autostart was not changed (dialog cancelled or denied).")
            return
        try:
            auto = bool(results.get("autostart", False))
        except Exception:
            auto = False
        if self._requested_autostart:
            if auto:
                self._finish(
                    True,
                    "Login autostart enabled. You can change this in system settings if needed.",
                )
            else:
                self._finish(False, "Login autostart was not enabled (check system settings).")
        else:
            self._finish(True, "Login autostart disabled (or left unchanged by the system).")


def request_flatpak_login_autostart(
    parent_widget,
    autostart: bool,
    start_minimized: bool,
    on_done: Callable[[bool, str], None],
) -> bool:
    """Start a portal RequestBackground flow. Parents the request to parent_widget."""
    try:
        PortalBackgroundRequest(
            parent_widget,
            portal_parent_window(parent_widget),
            autostart,
            start_minimized,
            on_done,
        )
        return True
    except Exception as e:
        logger.exception("request_flatpak_login_autostart: %s", e)
        on_done(False, str(e))
        return False
