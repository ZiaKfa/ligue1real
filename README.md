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
python main.py
```

This will:
1. Simulate a 45-second 5v5 futsal match with scripted AI
2. Render it top-down in 1080x1920 (vertical, TikTok/Reels-ready)
3. Pipe frames directly into ffmpeg -> `output/match_<timestamp>.mp4`

No manual editing needed - the MP4 that comes out is postable as-is.
Run it again for a new random match; every run is different because
player positions and ball physics vary.

## Tuning knobs (top of main.py)

- `MATCH_SECONDS` - length of the simulated match
- `players_per_team` (in `FutsalMatch(players_per_team=3)`) - team size
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

To generate a queue of videos to review before posting, wrap a call to
`main()` in a loop with different seeds:

```python
for i in range(5):
    match = FutsalMatch(players_per_team=3, seed=i)
    ...
```

You could also automate *generation* (not upload) with a free
scheduler like GitHub Actions on a cron trigger, so a fresh batch of
match videos is waiting in your output folder every morning for you
to review and post by hand.
