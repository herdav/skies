import json
import os
import tkinter as tk
from ui import FadingUI


def load_config() -> dict:
    """
    Tries to load a local config.json. Returns a dict with e.g. {"ffmpeg_path": "..."}.
    If not found or invalid, returns an empty dict.
    """
    config_path = "config.json"
    if not os.path.isfile(config_path):
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    """
    Main entry point: loads config.json (optional), then starts the Tkinter UI.
    """
    config = load_config()
    ffmpeg_path = config.get("ffmpeg_path", "")

    root = tk.Tk()
    FadingUI(root, ffmpeg_path=ffmpeg_path)
    root.mainloop()


if __name__ == "__main__":
    main()
