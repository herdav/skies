import os
import json

from routines.staticimg import download_staticimg
from routines.dynamicimg import download_dynamicimg
from routines.youtube import download_youtube
from routines.faratel import download_faratel
from routines.redspira import download_redspira
from routines.snerpa import download_snerpa
from routines.kt import download_kt
from routines.rtsp import download_rtsp
from routines.ufanet import download_ufanet
from routines.usap import download_usap
from routines.windy import download_windy


output_folder = "img"
os.makedirs(output_folder, exist_ok=True)
download_map = {}
camera_routines = {
    "faratel": ("faratelcams", download_faratel),
    "staticimg": ("staticimg", download_staticimg),
    "dynamicimg": ("dynamicimg", download_dynamicimg),
    "youtube": ("youtube", download_youtube),
    "redspira": ("redspira", download_redspira),
    "snerpa": ("snerpa", download_snerpa),
    "kt": ("kt", download_kt),
    "rtsp": ("rtsp", download_rtsp),
    "ufanet": ("ufanet", download_ufanet),
    "usap": ("usap", download_usap),
    "windy": ("windy", download_windy),
}


def format_utc(i):
    """Format string like UTC+2 or UTC-3."""
    s = "+" if i >= 0 else ""
    return f"UTC{s}{i}"


def load_cameras_from_json():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, "webcams.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def register_downloads(camera_data):
    """
    Fill the global download_map by reading each relevant JSON key from camera_routines
    and matching it with the correct download function.
    """
    for routine_name, (json_key, download_func) in camera_routines.items():
        # e.g. json_key = "faratelcams"
        # camera_data.get(json_key, []) = the list of objects
        cam_list = camera_data.get(json_key, [])
        download_map[routine_name] = (cam_list, download_func)


def dispatch_download(item, logger):
    """
    Dispatch the download to the correct function based on item ID presence
    in one of the known lists in download_map. Returns (ok, new_file).
    logger is a callable for logging (e.g. self.log).
    """
    item_id = item["id"]
    prev_files = set(os.listdir(output_folder))

    for routine_name, (cam_list, download_func) in download_map.items():
        if any(x["id"] == item_id for x in cam_list):
            try:
                if routine_name == "dynamicimg":
                    src_pattern = item.get("src", None)
                    element_class = item.get("imgclass", None)
                    element_id = item.get("imgid", None)
                    img_format = item.get("imgformat", None)
                    res = download_func(
                        url=item["url"],
                        image_id=item["id"],
                        src_pattern=src_pattern,
                        element_class=element_class,
                        element_id=element_id,
                        img_format=img_format,
                    )
                elif routine_name == "staticimg":
                    res = download_func(
                        url=item["url"],
                        image_id=item["id"],
                    )
                elif routine_name == "usap":
                    element_id = item.get("imgid", None)
                    tab_id = item.get("tabid", None)
                    res = download_func(
                        url=item["url"],
                        image_id=item["id"],
                        element_id=element_id,
                        tab_id=tab_id,
                    )
                elif routine_name == "windy":
                    res = download_func(
                        url=item["url"],
                        image_id=item["id"],
                    )
                else:
                    # Default behavior for other routines
                    res = download_func(item["url"], item["id"])

                return check_new_file(item_id, res, prev_files, routine_name, logger)

            except Exception as e:
                logger(f"Error in {routine_name}: {e}")
                return (False, False)

    return (False, False)


def check_new_file(item_id, result, prev_files, routine_name, logger):
    """
    Compare file lists before/after to detect new files. Returns (ok, new_file).
    """
    if not result:
        return (False, False)

    new_files = set(os.listdir(output_folder)) - prev_files
    found_new = any(f.startswith(item_id + "_") for f in new_files)
    if found_new:
        # logger(f"{routine_name}: {item_id}")
        return (True, True)
    return (True, False)
