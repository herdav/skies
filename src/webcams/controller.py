# src/controller.py
"""Application controller – keeps GUI and webscraper separated."""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Tuple

from webscraper import (
    dispatch_download,
    format_utc,
    load_cameras_from_json,
    register_downloads,
)


class WebcamController:
    """Central MVC controller."""

    def __init__(self) -> None:
        data = load_cameras_from_json()
        register_downloads(data)

        self.item_dict: Dict[str, Dict[str, Any]] = {
            it["image_id"]: it for v in data.values() if isinstance(v, list) for it in v
        }
        self.view = None
        self._worker: threading.Thread | None = None

    def attach_view(self, view) -> None:
        self.view = view
        self.view.populate_slots(self.all_utc_ids(), self.item_dict)

    def all_utc_ids(self) -> List[str]:
        return [format_utc(i) for i in range(-11, 13)]

    def start_downloads(self, selected_ids: List[str]) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._worker = threading.Thread(
            target=self._run_downloads, args=(selected_ids,), daemon=True
        )
        self._worker.start()

    def _run_downloads(self, ids: List[str]) -> None:
        for utcid in ids:
            item = self.item_dict[utcid]
            ok, new_file = self._download_item(item)
            if self.view:
                self.view.notify_download_finished(utcid, ok, new_file)

    def _download_item(self, item: Dict[str, Any]) -> Tuple[bool, bool]:
        ok, new_file = dispatch_download(item, print)
        return ok, new_file
