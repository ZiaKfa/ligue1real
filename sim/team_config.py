"""Load an optional team config (custom name + kit color + roster) from a JSON file.

Format: {
    "name": "FC Merah", "color": [230, 70, 70],   (both optional)
    "roster": [{"name": "Messi", "stats": {"pace": 95}, "face": "assets/faces/messi.png"}, ...]
               (optional; index 0 = GK, then spawn order; "name", "stats" and "face" all optional -
               "face" is a path to an image, drawn cropped to a circle on top of the player dot,
               with the kit color kept as a ring around it; missing/unreadable file just falls
               back to the flat color circle)
}
"""

import json


def load_team_config(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    color = data.get("color")
    return {
        "name": data.get("name"),
        "color": tuple(color) if color else None,
        "roster": data.get("roster"),
    }
