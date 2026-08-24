"""One command, two team names: builds both squads from the FIFA ratings CSV
(top-rated keeper + top 4 outfield, matched against nationality or club),
fetches any missing face photos, writes team_<name>.json for each, and runs
the match.

Usage:
    python auto_match.py --team-a France --team-b Spain --no-preview
    python auto_match.py --team-a "Real Madrid" --team-b "FC Barcelona" --no-preview
    (any other main.py flag - --batch, --min-goals, --jobs, etc. - passes straight through)
"""

import argparse
import csv
import json
import sys
import unicodedata

from fetch_faces import fetch_missing_faces
from fetch_stats import STAT_COLUMNS, GK_REFLEX_COLUMNS, _first_present

CSV_PATH = "FC26_20250921.csv"
PLAYERS_PER_TEAM = 5

# real primary kit colors, hand-picked - not exhaustive, just the teams
# people are likely to type. A team missing from here just keeps the sim's
# default random distinct-color assignment. A few swap in the away/trim
# color instead of the true home color, since white or near-black reads
# poorly against the pitch's white lines / dark background (Real Madrid,
# Germany, Juventus).
TEAM_COLORS = {
    "france": (0, 85, 164),
    "spain": (196, 30, 58),
    "argentina": (104, 195, 235),
    "england": (207, 20, 43),
    "brazil": (255, 205, 0),
    "germany": (221, 0, 21),
    "italy": (0, 66, 148),
    "portugal": (196, 30, 58),
    "netherlands": (255, 89, 0),
    "belgium": (206, 17, 38),
    "real madrid": (91, 42, 130),
    "fc barcelona": (145, 26, 52),
    "manchester united": (218, 41, 28),
    "manchester city": (108, 171, 221),
    "liverpool": (200, 16, 46),
    "chelsea": (3, 70, 148),
    "arsenal": (239, 1, 7),
    "bayern munich": (220, 0, 26),
    "juventus": (30, 30, 30),
    "paris saint-germain": (0, 32, 91),
}


# letters like O with stroke aren't combining-mark accents, so NFKD doesn't
# decompose them - encode('ascii', 'ignore') would just delete them outright
# (e.g. "degaard" instead of "Odegaard") instead of falling back to the
# closest ASCII letter
_NON_DECOMPOSING = str.maketrans("ØøÐð", "OoDd")


def _strip_accents(s):
    s = s.translate(_NON_DECOMPOSING)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _clean_name(row):
    # long_name is a full legal name, often with two surnames (paternal +
    # maternal) - e.g. "Federico Santiago Valverde Dipetta" is really
    # Federico VALVERDE, not "Federico Dipetta" (his mother's surname),
    # so blindly taking the long_name's last word picks the wrong one.
    # short_name already knows which surname is the famous one ("F.
    # Valverde") - only fall back to guessing when it's abbreviated to a
    # bare initial and isn't already a usable display name on its own
    # ("Lamine Yamal", "Cristiano Ronaldo" come through short_name as-is).
    short = row["short_name"]
    first_token = short.split()[0]
    if len(first_token) <= 2 and first_token.endswith("."):
        candidate = f"{row['long_name'].split()[0]} {short.split()[-1]}"
    else:
        candidate = short
    return _strip_accents(candidate)


BACK_POSITIONS = {"CB", "RB", "LB", "RWB", "LWB", "CDM"}


def _is_back(row):
    primary = row["player_positions"].split(",")[0].strip()
    return primary in BACK_POSITIONS


def _stats_for(row, is_keeper):
    if is_keeper:
        value = _first_present(row, GK_REFLEX_COLUMNS)
        return {"reflex": int(float(value))} if value is not None else {}
    stats = {}
    for stat, columns in STAT_COLUMNS.items():
        value = _first_present(row, columns)
        if value is not None:
            stats[stat] = int(float(value))
    return stats


def build_roster(rows, team_name):
    """team_name can be a nationality ("France") or a club ("Real Madrid") -
    whichever column matches. If both a country and a club share the name,
    the nationality is preferred (nations are the more common use case here)."""
    key = team_name.lower()
    pool = [r for r in rows if r["nationality_name"].lower() == key]
    if not pool:
        pool = [r for r in rows if r["club_name"].lower() == key]
    if not pool:
        raise SystemExit(f'no players found for nation or club "{team_name}" in {CSV_PATH}')

    keepers = [r for r in pool if "GK" in r["player_positions"]]
    gk = max(keepers or pool, key=lambda r: int(r["overall"]))

    # sim/match.py's _spawn_team assigns role purely by position in this
    # list (first half of the outfield entries -> BACK, rest -> FWD), so a
    # real defender has to actually land in the first half - sorting the
    # whole outfield pool by overall rating alone can rank an attacker
    # (e.g. an 85-rated winger) above a defender (an 82-rated center-back)
    # and hand them the BACK slot instead
    outfield_count = PLAYERS_PER_TEAM - 1
    back_count = outfield_count // 2
    remaining = [r for r in pool if r is not gk]
    defenders = sorted((r for r in remaining if _is_back(r)), key=lambda r: int(r["overall"]), reverse=True)
    attackers = sorted((r for r in remaining if not _is_back(r)), key=lambda r: int(r["overall"]), reverse=True)

    backs, fwds = defenders[:back_count], attackers[:outfield_count - back_count]
    leftover = sorted((r for r in remaining if r not in backs and r not in fwds),
                       key=lambda r: int(r["overall"]), reverse=True)
    while len(backs) < back_count and leftover:
        backs.append(leftover.pop(0))
    while len(backs) + len(fwds) < outfield_count and leftover:
        fwds.append(leftover.pop(0))

    outfield = backs + fwds

    slug = team_name.lower().replace(" ", "_")
    roster = []
    for i, row in enumerate([gk] + outfield):
        name = _clean_name(row)
        player_slug = name.lower().replace(" ", "_").replace(".", "")
        roster.append({
            "name": name,
            "stats": _stats_for(row, is_keeper=(i == 0)),
            "face": f"assets/faces/{slug}/{player_slug}.png",
        })
    return roster


def build_team_json(rows, team_name):
    roster = build_roster(rows, team_name)
    team = {"name": team_name, "roster": roster}
    color = TEAM_COLORS.get(team_name.lower())
    if color:
        team["color"] = list(color)

    path = f"team_{team_name.lower().replace(' ', '_')}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(team, f, indent=2)
        f.write("\n")
    return path


def main():
    parser = argparse.ArgumentParser(description="Auto-build two squads (national or club) and run the match.")
    parser.add_argument("--team-a", required=True, metavar="TEAM", help='nation or club, e.g. "France" or "Real Madrid"')
    parser.add_argument("--team-b", required=True, metavar="TEAM", help='nation or club, e.g. "Spain" or "FC Barcelona"')
    args, passthrough = parser.parse_known_args()

    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    paths = []
    for team_name in (args.team_a, args.team_b):
        print(f"Building squad for {team_name}...")
        path = build_team_json(rows, team_name)
        fetch_missing_faces(path)
        paths.append(path)

    sys.argv = [sys.argv[0], "--team-a-config", paths[0], "--team-b-config", paths[1], *passthrough]
    from main import main as run_main
    run_main()


if __name__ == "__main__":
    main()
