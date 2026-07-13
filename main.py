"""
Ligue1Real - automated match simulation + video recording
-----------------------------------------------------------
Simulates a 5v5 futsal match with simple physics (pymunk) and
scripted AI, renders it top-down (pygame), and pipes the frames
directly into ffmpeg to produce a finished vertical MP4 -
no manual editing step needed.

Run:
    python main.py

Output:
    output/match_<timestamp>.mp4

Later, swap the sim's `policy_fn` (see sim/scripted_ai.py) for a trained
RL policy and the rest of the pipeline (rendering, recording) stays
identical - see RL_SCALABILITY_PLAN.md.
"""

from sim import FutsalMatch
from render.preview import run_preview


def main():
    match = FutsalMatch(players_per_team=5)
    run_preview(match)


if __name__ == "__main__":
    main()
