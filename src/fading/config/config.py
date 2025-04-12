import json
import os

_CONFIG = None


def _load_config(path="config/config.json"):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Missing config file: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tuple_values = data.get("TUPLE_VALUES", {})
    for key, val in tuple_values.items():
        if isinstance(val, list):
            tuple_values[key] = tuple(val)

    return data


def get_config():
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = _load_config()
    return _CONFIG


config = get_config()
