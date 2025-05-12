# src/webscraper/downloads.py
"""Adapter layer between configuration JSON and low-level downloaders."""

from __future__ import annotations

import inspect
from functools import wraps
from pathlib import Path
from typing import Callable, List
from urllib.parse import urlparse

from .routines import ImageDownloader as _ID
from .routines import SeleniumDownloader as _SD


_ALL_DL_NAMES: List[str] = [
    n for n in dir(_SD) if callable(getattr(_SD, n)) and n.startswith("download_")
]
_SELENIUM_NAMES: List[str] = _ALL_DL_NAMES


_IMG_EXTS = {"jpg", "jpeg", "png", "gif", "bmp", "webp"}


def _derive_format(url: str | None, fallback: str = "jpg") -> str:
    """Guess an image file extension from *url* (fallback to *fallback*)."""
    ext = Path(urlparse(url or "").path).suffix.lstrip(".").lower()
    return ext if ext in _IMG_EXTS else fallback


def _filter_kwargs(func: Callable) -> Callable:
    """Decorator: call *func* with only the keyword args it explicitly accepts."""
    allowed = set(inspect.signature(func).parameters)

    @wraps(func)
    def inner(*args, **kw):
        return func(*args, **{k: v for k, v in kw.items() if k in allowed})

    return inner


@_filter_kwargs
def download_stat(url: str, image_id: str, *, output_folder: str = "img"):
    """Download a single static image given its direct URL."""
    return _ID.download_stat(url, image_id, output_folder=output_folder)


@_filter_kwargs
def download_dyna(
    url: str,
    image_id: str,
    *,
    img_format: str | None = None,
    src_pattern: str | None = None,
    element_class: str | None = None,
    element_id: str | None = None,
    output_folder: str = "img",
):
    """Download an image that requires simple HTML parsing."""
    fmt = img_format or _derive_format(src_pattern or url)
    return _ID.download_dyna(
        url,
        image_id,
        fmt,
        src_pattern=src_pattern,
        element_class=element_class,
        element_id=element_id,
        output_folder=output_folder,
    )


def _wrap_selenium(name: str) -> Callable:
    core = getattr(_SD, name)

    @_filter_kwargs
    @wraps(core)
    def wrapper(*args, **kw):
        return core(*args, **kw)

    return wrapper


globals().update({n: _wrap_selenium(n) for n in _SELENIUM_NAMES})


__all__: List[str] = [
    "download_stat",
    "download_dyna",
    *_SELENIUM_NAMES,
]
