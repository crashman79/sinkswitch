#!/usr/bin/env python3
"""Helpers for persistent routing latency diagnostics."""

import logging
import os
from pathlib import Path
from typing import Optional

_LATENCY_LOGGER: Optional[logging.Logger] = None


def _default_log_path() -> Path:
    cfg_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(cfg_home) if cfg_home else (Path.home() / ".config")
    return base / "sinkswitch" / "routing_latency.log"


def get_latency_log_path() -> Path:
    custom = os.environ.get("SINKSWITCH_LATENCY_LOG", "").strip()
    if custom:
        return Path(custom).expanduser()
    return _default_log_path()


def get_latency_logger() -> logging.Logger:
    global _LATENCY_LOGGER
    if _LATENCY_LOGGER is not None:
        return _LATENCY_LOGGER

    logger = logging.getLogger("sinkswitch.routing_latency")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_path = get_latency_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
        logger.addHandler(handler)
    except Exception:
        # Keep logger usable even if file setup fails.
        logger.addHandler(logging.NullHandler())

    _LATENCY_LOGGER = logger
    return logger


def log_latency_event(message: str) -> None:
    try:
        get_latency_logger().info(message)
    except Exception:
        # Never let debug logging affect runtime routing.
        pass
