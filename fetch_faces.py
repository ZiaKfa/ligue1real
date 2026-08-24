"""Fills in missing player face photos for a team JSON's roster.

For each roster entry with a "face" path that isn't already on disk, looks
the player up on Wikipedia (via MediaWiki search + pageimages) and falls
back to TheSportsDB if that comes up empty, then saves the photo to that
path. Entries whose file already exists are left alone.

Usage:
    python fetch_faces.py team_france.json team_spain.json
"""

import json
import os
import sys
import urllib.parse
import urllib.request

USER_AGENT = "Ligue1RealAssetFetcher/1.0 (personal project, non-commercial)"


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def _wikipedia_photo(name):
    query = urllib.parse.quote(f"{name} footballer")
    url = (
        "https://en.wikipedia.org/w/api.php?action=query&generator=search"
        f"&gsrsearch={query}&gsrlimit=1&prop=pageimages&piprop=thumbnail"
        "&pithumbsize=500&format=json"
    )
    pages = _get_json(url).get("query", {}).get("pages", {})
    for page in pages.values():
        thumb = page.get("thumbnail", {}).get("source")
        if thumb:
            return thumb
    return None


def _sportsdb_photo(name):
    query = urllib.parse.quote(name.replace(" ", "_"))
    url = f"https://www.thesportsdb.com/api/v1/json/123/searchplayers.php?p={query}"
    for player in _get_json(url).get("player") or []:
        photo = player.get("strCutout") or player.get("strThumb")
        if photo:
            return photo
    return None


def fetch_face_url(name):
    for lookup in (_wikipedia_photo, _sportsdb_photo):
        try:
            url = lookup(name)
        except Exception as e:
            print(f"  ({lookup.__name__} failed: {e})")
            continue
        if url:
            return url
    return None


def fetch_missing_faces(team_json_path):
    """Fills in any roster "face" path in this team JSON that isn't already
    on disk - the shared worker behind both this script's CLI and other
    scripts (e.g. auto_match.py) that generate a roster and want photos
    fetched for it in the same step."""
    with open(team_json_path, encoding="utf-8") as f:
        team = json.load(f)

    for entry in team.get("roster", []):
        face_path, name = entry.get("face"), entry.get("name")
        if not face_path or not name:
            continue
        if os.path.isfile(face_path):
            print(f"skip {name} (already have {face_path})")
            continue

        print(f"fetching {name}...")
        url = fetch_face_url(name)
        if not url:
            print("  no photo found")
            continue

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()

        os.makedirs(os.path.dirname(face_path), exist_ok=True)
        with open(face_path, "wb") as out:
            out.write(data)
        print(f"  saved {face_path} ({len(data)} bytes) <- {url}")


def main():
    paths = sys.argv[1:]
    if not paths:
        print("Usage: python fetch_faces.py <team.json> [team2.json ...]")
        return
    for path in paths:
        fetch_missing_faces(path)


if __name__ == "__main__":
    main()
