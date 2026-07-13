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

Output:
    output/goals<total>_<red>-<blue>_<timestamp>.mp4

Later, swap the sim's `policy_fn` (see sim/scripted_ai.py) for a trained
RL policy and the rest of the pipeline (rendering, recording) stays
identical - see RL_SCALABILITY_PLAN.md.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed

from sim import FutsalMatch
from render.preview import run_preview


def _generate_one(_index):
    """Runs in a worker process - builds and renders one match headlessly."""
    match = FutsalMatch(players_per_team=5)
    return run_preview(match, show_preview=False)


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
    args = parser.parse_args()

    if args.no_preview and args.batch > 1:
        # each match is independent and CPU-bound (physics + ffmpeg encode),
        # so parallelizing across processes is a straight wall-clock win
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(_generate_one, i) for i in range(args.batch)]
            for future in as_completed(futures):
                future.result()  # re-raise if a worker crashed
        return

    for i in range(args.batch):
        if args.batch > 1:
            print(f"\n=== Match {i + 1}/{args.batch} ===")
        match = FutsalMatch(players_per_team=5)
        run_preview(match, show_preview=not args.no_preview)


if __name__ == "__main__":
    main()
