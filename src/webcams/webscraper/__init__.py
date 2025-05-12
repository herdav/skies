# src/webscraper/__init__.py
"""Webscraper API."""

from __future__ import annotations

from . import downloads as _dl
from .downloads import *  # noqa: F401,F403


from .cams import (
    format_utc,
    load_cameras_from_json,
    register_downloads,
    dispatch_download,
    check_new_file,
)

__all__ = _dl.__all__ + [
    "format_utc",
    "load_cameras_from_json",
    "register_downloads",
    "dispatch_download",
    "check_new_file",
]
