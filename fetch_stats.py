"""Fills in roster "stats" from a FIFA/sofifa player ratings CSV, matched by
name to each roster entry.

sofifa.com itself blocks scripted requests (403, Cloudflare), so this reads
a CSV you've downloaded yourself - e.g. one of the Kaggle FIFA player rating
dumps (search "FIFA complete player dataset"). Column names aren't fully
standardized across those datasets, so a few common aliases are tried for
each stat.

Usage:
    python fetch_stats.py fifa_players.csv team_france.json team_spain.json
"""

import csv
import difflib
import json
import sys
import unicodedata

NAME_COLUMNS = ["long_name", "short_name", "name", "player_name"]
STAT_COLUMNS = {
    "pace": ["pace", "movement_acceleration"],
    "shooting": ["shooting", "attacking_finishing"],
    "tackling": ["defending", "defending_standing_tackle"],
}
GK_REFLEX_COLUMNS = ["goalkeeping_reflexes", "gk_reflexes"]


def _normalize(s):
    # strip accents ("Mbappé" -> "Mbappe") and case, so roster names typed
    # without diacritics still match the CSV's real-name spelling
    stripped = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return stripped.lower().strip()


def _first_present(row, columns):
    for col in columns:
        value = row.get(col)
        if value:
            return value
    return None


def _find_player(rows, name):
    target = _normalize(name)
    candidates = [(row, [_normalize(row[c]) for c in NAME_COLUMNS if row.get(c)]) for row in rows]

    for row, names in candidates:
        if target in names:
            return row
    for row, names in candidates:
        if any(target in n or n in target for n in names):
            return row

    # the CSV's long_name is often a full legal name with extra middle
    # names ("Mike Peterson Maignan", "Dayotchanculle Oswald Upamecano"),
    # so a common "First Last" roster name isn't a contiguous substring of
    # it - match on the first and last word both appearing instead
    words = target.split()
    if len(words) >= 2:
        first, last = words[0], words[-1]
        for row, names in candidates:
            if any(first in n and last in n for n in names):
                return row

    # some of these CSV exports have mangled accented characters (e.g.
    # "Mbappe" turns into a stray replacement char), which breaks an exact
    # or substring match - fall back to fuzzy similarity for those
    best_row, best_ratio = None, 0.85  # below this, it's not the same player
    for row, names in candidates:
        for n in names:
            ratio = difflib.SequenceMatcher(None, target, n).ratio()
            if ratio > best_ratio:
                best_row, best_ratio = row, ratio
    return best_row


def main():
    if len(sys.argv) < 3:
        print("Usage: python fetch_stats.py <fifa_players.csv> <team.json> [team2.json ...]")
        return

    csv_path, team_paths = sys.argv[1], sys.argv[2:]
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for path in team_paths:
        with open(path, encoding="utf-8") as f:
            team = json.load(f)

        roster = team.get("roster", [])
        changed = False
        for i, entry in enumerate(roster):
            name = entry.get("name")
            if not name:
                continue

            row = _find_player(rows, name)
            if row is None:
                print(f"skip {name} (not found in {csv_path})")
                continue

            if i == 0:
                # goalkeeper - the real goalkeeping rating matters here, not
                # outfield pace/shooting/defending
                value = _first_present(row, GK_REFLEX_COLUMNS)
                stats = {"reflex": int(float(value))} if value is not None else {}
            else:
                stats = {}
                for stat, columns in STAT_COLUMNS.items():
                    value = _first_present(row, columns)
                    if value is not None:
                        stats[stat] = int(float(value))

            if stats:
                entry["stats"] = stats
                changed = True
                print(f"{name}: {stats}")
            else:
                print(f"skip {name} (matched row but no usable stat columns)")

        if changed:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(team, f, indent=2)
                f.write("\n")
            print(f"updated {path}")


if __name__ == "__main__":
    main()
