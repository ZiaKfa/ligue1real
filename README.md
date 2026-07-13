# Futsal Sim

Automated futsal match simulation -> rendered video, ready to post manually
to TikTok/Reels. Recording is fully automatic; uploading is up to you.

## Setup (one-time)

1. Install Python 3.10+
2. Install ffmpeg and make sure it's on your PATH:
   - Windows: https://www.gyan.dev/ffmpeg/builds/ (add the `bin` folder to PATH)
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`
3. Install Python packages:
   ```
   pip install -r requirements.txt
   ```

## Run

```
python main.py                          # live preview window while it records
python main.py --no-preview             # no window, runs faster (good for unattended generation)
python main.py --no-preview --batch 5   # generates 5 matches in parallel (4 workers by default)
python main.py --no-preview --batch 5 --jobs 8   # raise/lower the worker count
python main.py --no-preview --batch 10 --min-goals 2
python main.py --no-preview --batch 10 --min-goals-red 2 --min-goals-blue 0
```

`--batch` with `--no-preview` renders matches across parallel worker processes
(`--jobs`, default 4) instead of one at a time - each ffmpeg encode is already
multi-threaded, so going much higher than your core count tends to slow things
down rather than speed them up.

`--min-goals N` sets how many goals *each* team must score for the match to be
kept (default: 1 - so scoreless or one-sided 3-0 blowouts get auto-deleted,
not just posted as-is). `--min-goals-red`/`--min-goals-blue` override that
per team slot if you want an asymmetric threshold (note: "red"/"blue" are
just internal team ids here, not the actual kit color - that's randomized
per match).

This will:
1. Simulate a 45-second 5v5 futsal match with scripted AI
2. Render it top-down in 1080x1920 (vertical, TikTok/Reels-ready)
3. Pipe frames directly into ffmpeg -> `output/goals<total>_<red>-<blue>_<timestamp>.mp4`

The goal count leads the filename (zero-padded) so sorting by name in your
file browser surfaces the highest-scoring, most postable matches first.

No manual editing needed - the MP4 that comes out is postable as-is.
Run it again for a new random match; every run is different because
player positions, ball physics, and kit colors all vary.

## Tuning knobs (top of main.py)

- `MATCH_SECONDS` - length of the simulated match
- `players_per_team` (in `FutsalMatch(players_per_team=5)`) - team size
- `COURT_W` / `COURT_H` - court size on screen
- `GOAL_WIDTH` - how easy it is to score

## Next steps: adding RL

Right now `FutsalMatch.choose_action()` uses simple scripted behavior
(chase the ball, hold formation, kick toward goal). To swap in a
trained RL agent:

1. Wrap this sim as a Gymnasium environment: define `observation`
   (e.g. own position, ball position/velocity, teammate/opponent
   positions) and `action` (e.g. desired velocity direction) spaces.
2. Train with Stable-Baselines3 (PPO) via self-play - one shared
   policy controls all players on a team, mirrored for the opponent.
   Free compute: Google Colab or Kaggle Notebooks (both have free
   GPU/CPU hours).
3. Once trained, replace the body of `choose_action()` with
   `action = model.predict(obs)` for players on the RL-controlled
   team. Everything else (physics, rendering, ffmpeg export) stays
   exactly the same - the sim/render pipeline doesn't care whether
   the actions come from a script or a neural net.

## Batch-generating multiple videos

```
python main.py --no-preview --batch 10
```

Generates a queue of videos to review before posting. `--no-preview` skips
the window so each match renders as fast as your machine can encode it
instead of being paced to real time, and matches are rendered 4-at-a-time
in parallel by default (`--jobs N` to change that). Filenames sort by goal
count, so the liveliest matches are easy to spot in the output folder.

You could also automate *generation* (not upload) with a free
scheduler like GitHub Actions on a cron trigger, so a fresh batch of
match videos is waiting in your output folder every morning for you
to review and post by hand.
