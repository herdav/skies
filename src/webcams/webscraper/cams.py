# src/webscraper/cams.py
"""Camera-to-routine dispatcher."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .downloads import (  # pylint: disable=no-name-in-module
    download_dyna,
    download_stat,
    download_ytbe,
    download_fatl,
    download_rdpa,
    download_snpa,
    download_onkt,
    download_rtsp,
    download_ufnt,
    download_usap,
    download_wndy,
)

OUTPUT_FOLDER = "img"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

camera_routines: Dict[str, Tuple[str, Any]] = {
    "stat": ("stat", download_stat),
    "dyna": ("dyna", download_dyna),
    "ytbe": ("ytbe", download_ytbe),
    "fatl": ("fatl", download_fatl),
    "rdpa": ("rdpa", download_rdpa),
    "snpa": ("snpa", download_snpa),
    "onkt": ("onkt", download_onkt),
    "rtsp": ("rtsp", download_rtsp),
    "ufnt": ("ufnt", download_ufnt),
    "usap": ("usap", download_usap),
    "wndy": ("wndy", download_wndy),
}

download_map: Dict[str, Tuple[List[Dict[str, Any]], Any]] = {}


def format_utc(offset: int) -> str:
    """Format UTC strings."""
    sign = "+" if offset >= 0 else ""
    return f"UTC{sign}{offset}"


def load_cameras_from_json(fname: str = "webcams.json") -> Dict[str, Any]:
    """Load camara data from json file."""
    path = Path(__file__).with_name(fname)
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def register_downloads(camera_data: Dict[str, Any]) -> None:
    """Register downloads."""
    for routine_name, (json_key, download_func) in camera_routines.items():
        cam_list = camera_data.get(json_key, [])
        download_map[routine_name] = (cam_list, download_func)


def dispatch_download(item: Dict[str, Any], logger) -> Tuple[bool, bool]:  # noqa: ANN001
    "Dispatch download."
    item_id = item["image_id"]
    prev_files = set(os.listdir(OUTPUT_FOLDER))

    for routine_name, (cam_list, download_func) in download_map.items():
        if any(c["image_id"] == item_id for c in cam_list):
            try:
                result = download_func(
                    **{k: v for k, v in item.items() if k != "image_id"}, image_id=item_id
                )
                return _check_new_file(item_id, result, prev_files, routine_name, logger)
            except Exception as e:
                logger(f"{routine_name}: {e}")
                return False, False
    return False, False


def _check_new_file(
    item_id: str, result: Any, prev_files: set[str], routine: str, logger
) -> Tuple[bool, bool]:  # noqa: ANN001
    if not result:
        return False, False
    new_files = set(os.listdir(OUTPUT_FOLDER)) - prev_files
    changed = any(f.startswith(f"{item_id}_") for f in new_files)
    return True, changed


check_new_file = _check_new_file
