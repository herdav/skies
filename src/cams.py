# cams.py

import os
import json
from datetime import datetime

# Import your download routines
from routines.webcamimage import download_webcam
from routines.dynamicjpg import download_dynamicjpg
from routines.youtube import download_youtube
from routines.faratel import download_faratel
from routines.redspira import download_redspira
from routines.snerpa import download_snerpa
from routines.kt import download_kt
from routines.livechina import download_livechina
from routines.rt import download_rt
from routines.rtsp import download_rtsp
from routines.ufanet import download_ufanet
#from routines.windy import download_windy

output_folder = "img"
os.makedirs(output_folder, exist_ok=True)

def format_utc(i):
  """Format string like UTC+2 or UTC-3."""
  s = "+" if i >= 0 else ""
  return f"UTC{s}{i}"

camera_routines = {
  "faratel":      ("faratelcams",  download_faratel),
  "webcamimage":  ("webcamimage",  download_webcam),
  "dynamicjpg":   ("dynamicjpg",   download_dynamicjpg),
  "youtube":      ("youtube",      download_youtube),
  "redspira":     ("redspira",     download_redspira),
  "snerpa":       ("snerpa",       download_snerpa),
  "kt":           ("kt",           download_kt),
  "livechina":    ("livechina",    download_livechina),
  "rt":           ("rt",           download_rt),
  "rtsp":         ("rtsp",         download_rtsp),
  "ufanet":       ("ufanet",       download_ufanet),
  #"windy":        ("windy",        download_windy),
}

# Global dict to store the final mapping from "routine_name" -> (list_of_items, download_func)
download_map = {}

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

  # Loop over each entry in the dictionary
  for routine_name, (cam_list, download_func) in download_map.items():
    # Check if the item is part of the current list
    if any(x["id"] == item_id for x in cam_list):
      try:
        # If routine_name is dynamicjpg or webcamimage, we may pass extra parameters
        if routine_name == "dynamicjpg" or routine_name == "windy":
          src_pattern = item.get("src", None)
          element_class = item.get("class", None)
          res = download_func(
            url=item["url"],
            image_id=item["id"],
            src_pattern=src_pattern,
            element_class=element_class
          )
        elif routine_name == "webcamimage":
          # Direct URL-based download for webcamimage
          res = download_func(url=item["url"], image_id=item["id"])
        else:
          # Default behavior for other routines
          # e.g. download_faratel(url, image_id)
          res = download_func(item["url"], item["id"])

        return check_new_file(item_id, res, prev_files, routine_name, logger)

      except Exception as e:
        logger(f"Error in {routine_name}: {e}")
        return (False, False)

  # If no matching routine was found
  return (False, False)

def check_new_file(item_id, result, prev_files, msg, logger):
  """
  Compare file lists before/after to detect new files.
  Returns (ok, new_file).
  """
  if not result:
    return (False, False)

  new_files = set(os.listdir(output_folder)) - prev_files
  found_new = any(f.startswith(item_id + "_") for f in new_files)
  if found_new:
    logger(f"{msg}: {item_id}")
    return (True, True)
  return (True, False)
