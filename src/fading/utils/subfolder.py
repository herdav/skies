import os
from typing import Dict, List, Tuple

from utils.datamodel import ImageData
from utils.fading import FadingLogic, ImageHelper


class SubfolderManager:
    """
    This class manages subfolders, scanning them for images, handling missing offsets,
    and providing the final mapping for each subfolder.
    """

    def __init__(self):
        # Subfolder names found in the selected root folder
        self.subfolder_names: List[str] = []
        # Each subfolder maps offset -> (filepath, is_proxy)
        self.subfolder_data: Dict[str, Dict[float, Tuple[str, bool]]] = {}

    def select_subfolders(self, folder: str) -> None:
        """
        Emulates the logic of scanning a root folder for subfolders (originally in the UI).
        This method populates subfolder_names and subfolder_data accordingly.
        """
        self.subfolder_names.clear()
        self.subfolder_data.clear()

        if not folder or not os.path.isdir(folder):
            return

        # Gather possible subfolders
        subs = []
        for entry in os.listdir(folder):
            path_sub = os.path.join(folder, entry)
            if os.path.isdir(path_sub):
                subs.append(entry)
        subs.sort()

        # Fill subfolder_data by scanning each subfolder for images named "*_fading.png"
        for sf in subs:
            sp = os.path.join(folder, sf)
            images_map = {}
            for itm in os.listdir(sp):
                if itm.lower().endswith("_fading.png"):
                    fpath = os.path.join(sp, itm)
                    off_val = FadingLogic.parse_utc_offset(fpath)
                    images_map[off_val] = (fpath, False)
            if images_map:
                self.subfolder_names.append(sf)
                self.subfolder_data[sf] = images_map

    def fill_missing_images(self) -> None:
        """
        Ensures each subfolder has entries for all known offsets.
        Missing offsets are replaced by fallback proxies or black dummy images.
        """
        if not self.subfolder_names:
            return

        # Collect all offsets from all subfolders
        all_offsets = set()
        for sf in self.subfolder_names:
            all_offsets.update(self.subfolder_data[sf].keys())
        sorted_offsets = sorted(all_offsets)

        # Fill each subfolder's map with missing offsets
        for i, sf in enumerate(self.subfolder_names):
            sub_map = self.subfolder_data[sf]
            new_map = {}
            for off_val in sorted_offsets:
                if off_val in sub_map:
                    new_map[off_val] = sub_map[off_val]
                else:
                    # create or find fallback
                    fallback_path, px_flag = FadingLogic.fallback_for_offset(
                        i, off_val, self.subfolder_names, self.subfolder_data
                    )
                    new_map[off_val] = (fallback_path, px_flag)
            self.subfolder_data[sf] = new_map

    def get_subfolder_image_data(
        self, subfolder_name: str, gamma_val: float
    ) -> List[ImageData]:
        """
        Returns a list of ImageData for the specified subfolder, computing brightness with the given gamma.
        """
        if subfolder_name not in self.subfolder_data:
            return []

        offset_map = self.subfolder_data[subfolder_name]
        image_data_list = []
        for off_val, (fpath, px) in sorted(offset_map.items(), key=lambda x: x[0]):
            br = ImageHelper.calculate_brightness(fpath, gamma_val)
            image_data_list.append(
                ImageData(
                    file_path=fpath,
                    check_var=None,  # Will be set in the UI as a tk.BooleanVar
                    brightness_value=br,
                    offset=off_val,
                    is_proxy=px,
                )
            )
        return image_data_list
