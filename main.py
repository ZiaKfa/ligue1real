"""
Ligue1Real - automated match simulation + video recording
-----------------------------------------------------------
Simulates a 5v5 futsal match with simple physics (pymunk) and
scripted AI, renders it top-down (pygame), and pipes the frames
directly into ffmpeg to produce a finished vertical MP4 -
no manual editing step needed.

Run:
    python main.py
    python main.py --no-preview
    python main.py --no-preview --batch 5             # 4 parallel workers by default
    python main.py --no-preview --batch 20 --jobs 8   # raise it on a beefier machine
    python main.py --no-preview --batch 10 --min-goals 2               # e.g. keeps a 2-0 result
    python main.py --no-preview --batch 10 --min-goals-red 2 --min-goals-blue 0   # red must score >=2 AND blue >=0
    python main.py --team-a-config myteam.json         # {"name": "FC Merah", "color": [230,70,70]}

Output:
    output/goals<total>_<red>-<blue>_<timestamp>.mp4

Later, swap the sim's `policy_fn` (see sim/scripted_ai.py) for a trained
RL policy and the rest of the pipeline (rendering, recording) stays
identical - see RL_SCALABILITY_PLAN.md.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed

from sim import FutsalMatch
from sim.config import MIN_GOALS_DEFAULT, MIN_GOALS_RED_DEFAULT, MIN_GOALS_BLUE_DEFAULT
from sim.team_config import load_team_config
from render.preview import run_preview


def _generate_one(_index, min_goals, min_goals_red, min_goals_blue, team_a, team_b):
    """Runs in a worker process - builds and renders one match headlessly."""
    match = FutsalMatch(players_per_team=5, teams=(team_a, team_b))
    return run_preview(match, show_preview=False, min_goals=min_goals,
                        min_goals_red=min_goals_red, min_goals_blue=min_goals_blue)


def main():
    parser = argparse.ArgumentParser(description="Simulate and render futsal matches.")
    parser.add_argument(
        "--no-preview", action="store_true",
        help="skip the live preview window - runs faster, good for batch generation",
    )
    parser.add_argument(
        "--batch", type=int, default=1, metavar="N",
        help="generate N matches in this run (default: 1)",
    )
    parser.add_argument(
        "--jobs", type=int, default=4, metavar="N",
        help="with --no-preview and --batch > 1, render matches in parallel across "
             "N worker processes (default: 4 - each ffmpeg encode is already "
             "multi-threaded, so going much higher tends to oversubscribe the CPU)",
    )
    parser.add_argument(
        "--min-goals", type=int, default=MIN_GOALS_DEFAULT, metavar="N",
        help="the match's total combined goals (both sides added together) must reach "
             "this many, or the recording is discarded - so --min-goals 2 keeps a 2-0 "
             f"result just as readily as a 1-1 (default: {MIN_GOALS_DEFAULT}); this is "
             "independent of --min-goals-red/--min-goals-blue below, which check each "
             "side individually on top of this",
    )
    parser.add_argument(
        "--min-goals-red", type=int, default=MIN_GOALS_RED_DEFAULT, metavar="N",
        help="additionally require the 'red' team slot to individually reach this many "
             f"goals (default: {MIN_GOALS_RED_DEFAULT}; note: 'red'/'blue' are just "
             "internal team ids, not the actual kit color - that's randomized per match)",
    )
    parser.add_argument(
        "--min-goals-blue", type=int, default=MIN_GOALS_BLUE_DEFAULT, metavar="N",
        help="additionally require the 'blue' team slot to individually reach this many "
             f"goals (default: {MIN_GOALS_BLUE_DEFAULT})",
    )
    parser.add_argument(
        "--team-a-config", type=str, default=None, metavar="PATH",
        help='JSON file with {"name": ..., "color": [r,g,b]} for the "red" team slot '
             "(both fields optional; omit this flag to keep the default random identity)",
    )
    parser.add_argument(
        "--team-b-config", type=str, default=None, metavar="PATH",
        help="same as --team-a-config, for the 'blue' team slot",
    )
    args = parser.parse_args()

    team_a = load_team_config(args.team_a_config) if args.team_a_config else None
    team_b = load_team_config(args.team_b_config) if args.team_b_config else None

    if args.no_preview and args.batch > 1:
        # each match is independent and CPU-bound (physics + ffmpeg encode),
        # so parallelizing across processes is a straight wall-clock win
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures = [
                pool.submit(_generate_one, i, args.min_goals, args.min_goals_red,
                            args.min_goals_blue, team_a, team_b)
                for i in range(args.batch)
            ]
            for future in as_completed(futures):
                future.result()  # re-raise if a worker crashed
        return

    for i in range(args.batch):
        if args.batch > 1:
            print(f"\n=== Match {i + 1}/{args.batch} ===")
        match = FutsalMatch(players_per_team=5, teams=(team_a, team_b))
        run_preview(match, show_preview=not args.no_preview, min_goals=args.min_goals,
                    min_goals_red=args.min_goals_red, min_goals_blue=args.min_goals_blue)


if __name__ == "__main__":
    main()
