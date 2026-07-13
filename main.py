"""
Futsal Sim - automated match simulation + video recording
-----------------------------------------------------------
Simulates a 3v3 futsal match with simple physics (pymunk) and
scripted AI, renders it top-down (pygame), and pipes the frames
directly into ffmpeg to produce a finished vertical MP4 -
no manual editing step needed.

Run:
    python main.py

Output:
    output/match_<timestamp>.mp4

Later, swap `choose_action()` for a trained RL policy and the
rest of the pipeline (rendering, recording) stays identical.
"""

import math
import random
import subprocess
import time
import os

import pygame
import pymunk

# ---------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------
VIDEO_W, VIDEO_H = 1080, 1920      # vertical output (TikTok/Reels)
FPS = 30
MATCH_SECONDS = 45                 # sim length; trim/loop as you like
STEPS_PER_FRAME = 4                # physics substeps for stability

COURT_MARGIN_TOP = 320             # room for scoreboard text
COURT_MARGIN_BOTTOM = 140
COURT_W = 820
COURT_H = VIDEO_H - COURT_MARGIN_TOP - COURT_MARGIN_BOTTOM
COURT_X = (VIDEO_W - COURT_W) // 2
COURT_Y = COURT_MARGIN_TOP

PLAYER_RADIUS = 26
BALL_RADIUS = 14
GOAL_WIDTH = 220                   # goal opening centered on top/bottom edge

TEAM_RED = (230, 70, 70)
TEAM_BLUE = (70, 130, 230)
BALL_COLOR = (240, 240, 240)
COURT_COLOR = (35, 110, 60)
LINE_COLOR = (235, 235, 235)
BG_COLOR = (18, 18, 22)

OUTPUT_DIR = "output"


# ---------------------------------------------------------------
# PHYSICS WORLD
# ---------------------------------------------------------------
class FutsalMatch:
    def __init__(self, players_per_team=3, seed=None):
        if seed is not None:
            random.seed(seed)

        self.space = pymunk.Space()
        self.space.damping = 0.55  # friction-like slowdown each step

        self.score = {"red": 0, "blue": 0}
        self.event_log = []  # (time, text) for on-screen captions
        self.time_elapsed = 0.0

        self._build_walls()
        self.ball_body, self.ball_shape = self._make_ball()
        self.players = []  # list of dicts: body, shape, team, role

        self._spawn_team("red", players_per_team, side=-1)
        self._spawn_team("blue", players_per_team, side=1)

    # -- setup -----------------------------------------------------
    def _build_walls(self):
        thickness = 10
        left = COURT_X
        right = COURT_X + COURT_W
        top = COURT_Y
        bottom = COURT_Y + COURT_H
        mid_x = COURT_X + COURT_W / 2

        segments = [
            # left wall (split around... not needed, no side goals)
            ((left, top), (left, bottom)),
            ((right, top), (right, bottom)),
            # top wall, with a gap for the goal
            ((left, top), (mid_x - GOAL_WIDTH / 2, top)),
            ((mid_x + GOAL_WIDTH / 2, top), (right, top)),
            # bottom wall, with a gap for the goal
            ((left, bottom), (mid_x - GOAL_WIDTH / 2, bottom)),
            ((mid_x + GOAL_WIDTH / 2, bottom), (right, bottom)),
        ]
        for a, b in segments:
            seg = pymunk.Segment(self.space.static_body, a, b, thickness)
            seg.elasticity = 0.8
            seg.friction = 0.4
            self.space.add(seg)

        self.goal_top_x_range = (mid_x - GOAL_WIDTH / 2, mid_x + GOAL_WIDTH / 2)
        self.goal_bottom_x_range = self.goal_top_x_range
        self.court_bounds = (left, top, right, bottom)

    def _make_ball(self):
        mass = 1
        moment = pymunk.moment_for_circle(mass, 0, BALL_RADIUS)
        body = pymunk.Body(mass, moment)
        body.position = (COURT_X + COURT_W / 2, COURT_Y + COURT_H / 2)
        shape = pymunk.Circle(body, BALL_RADIUS)
        shape.elasticity = 0.85
        shape.friction = 0.3
        shape.collision_type = 1
        self.space.add(body, shape)
        return body, shape

    def _spawn_team(self, team, count, side):
        # side = -1 -> defends top goal, attacks bottom; side = 1 -> mirrored
        mid_x = COURT_X + COURT_W / 2
        for i in range(count):
            mass = 4
            moment = pymunk.moment_for_circle(mass, 0, PLAYER_RADIUS)
            body = pymunk.Body(mass, moment)
            x = mid_x + (i - (count - 1) / 2) * 140
            y = COURT_Y + COURT_H / 2 + side * (COURT_H / 4)
            body.position = (x, y)
            shape = pymunk.Circle(body, PLAYER_RADIUS)
            shape.elasticity = 0.6
            shape.friction = 0.6
            shape.collision_type = 2
            self.space.add(body, shape)
            self.players.append({
                "body": body, "shape": shape, "team": team,
                "home_side": side, "id": f"{team}_{i}",
            })

    # -- AI (scripted for now; replace with RL policy later) -------
    def choose_action(self, player):
        """Returns a desired velocity vector (dx, dy) for this player.
        Swap this function out for `rl_policy.predict(obs)` once you
        have a trained model - the rest of the sim doesn't change."""
        body = player["body"]
        bx, by = self.ball_body.position
        px, py = body.position
        team = player["team"]

        attack_dir = -1 if team == "red" else 1  # red attacks toward bottom(+1)? see below
        # red spawned side=-1 (upper half) attacks the bottom goal (+1 direction)
        attack_dir = 1 if team == "red" else -1

        dist_to_ball = math.hypot(bx - px, by - py)

        if dist_to_ball < 260:
            # chase the ball and nudge it toward the attacking goal
            target_x, target_y = bx, by
        else:
            # hold a loose formation on your own half, biased toward the ball's x
            mid_y = COURT_Y + COURT_H / 2
            home_y = mid_y - attack_dir * (COURT_H / 4)
            target_x = bx * 0.6 + px * 0.4
            target_y = home_y

        dx, dy = target_x - px, target_y - py
        dist = math.hypot(dx, dy) or 1
        speed = 260
        return (dx / dist * speed, dy / dist * speed)

    # -- step --------------------------------------------------------
    def step(self, dt):
        for p in self.players:
            vx, vy = self.choose_action(p)
            p["body"].velocity = (vx, vy)

        # if a player is close to the ball, give it a kick toward the goal
        for p in self.players:
            bx, by = self.ball_body.position
            px, py = p["body"].position
            if math.hypot(bx - px, by - py) < PLAYER_RADIUS + BALL_RADIUS + 6:
                attack_dir = 1 if p["team"] == "red" else -1
                goal_x = COURT_X + COURT_W / 2
                goal_y = self.court_bounds[3] if attack_dir == 1 else self.court_bounds[1]
                kx, ky = goal_x - bx, goal_y - by
                kd = math.hypot(kx, ky) or 1
                power = 420
                self.ball_body.velocity = (
                    self.ball_body.velocity[0] * 0.3 + kx / kd * power,
                    self.ball_body.velocity[1] * 0.3 + ky / kd * power,
                )

        self.space.step(dt)
        self.time_elapsed += dt
        self._check_goal()

    def _check_goal(self):
        bx, by = self.ball_body.position
        left, top, right, bottom = self.court_bounds
        lo, hi = self.goal_top_x_range
        scored = None
        if by <= top + BALL_RADIUS and lo <= bx <= hi:
            scored = "blue"   # ball entered top goal -> blue scored (red defends top)
        elif by >= bottom - BALL_RADIUS and lo <= bx <= hi:
            scored = "red"    # ball entered bottom goal -> red scored

        if scored:
            self.score[scored] += 1
            self.event_log.append((self.time_elapsed, f"GOAL! {scored.upper()} scores!"))
            self.ball_body.position = (COURT_X + COURT_W / 2, COURT_Y + COURT_H / 2)
            self.ball_body.velocity = (0, 0)


# ---------------------------------------------------------------
# RENDERING
# ---------------------------------------------------------------
def draw_frame(surface, match: FutsalMatch, font_big, font_med):
    surface.fill(BG_COLOR)

    # court
    court_rect = pygame.Rect(COURT_X, COURT_Y, COURT_W, COURT_H)
    pygame.draw.rect(surface, COURT_COLOR, court_rect)
    pygame.draw.rect(surface, LINE_COLOR, court_rect, 4)
    pygame.draw.line(
        surface, LINE_COLOR,
        (COURT_X, COURT_Y + COURT_H / 2), (COURT_X + COURT_W, COURT_Y + COURT_H / 2), 3,
    )
    pygame.draw.circle(
        surface, LINE_COLOR,
        (int(COURT_X + COURT_W / 2), int(COURT_Y + COURT_H / 2)), 70, 3,
    )

    # goals (visual only)
    mid_x = COURT_X + COURT_W / 2
    pygame.draw.line(surface, (255, 220, 80),
                      (mid_x - GOAL_WIDTH / 2, COURT_Y), (mid_x + GOAL_WIDTH / 2, COURT_Y), 6)
    pygame.draw.line(surface, (255, 220, 80),
                      (mid_x - GOAL_WIDTH / 2, COURT_Y + COURT_H), (mid_x + GOAL_WIDTH / 2, COURT_Y + COURT_H), 6)

    # players
    for p in match.players:
        color = TEAM_RED if p["team"] == "red" else TEAM_BLUE
        x, y = p["body"].position
        pygame.draw.circle(surface, color, (int(x), int(y)), PLAYER_RADIUS)
        pygame.draw.circle(surface, (0, 0, 0), (int(x), int(y)), PLAYER_RADIUS, 2)

    # ball
    bx, by = match.ball_body.position
    pygame.draw.circle(surface, BALL_COLOR, (int(bx), int(by)), BALL_RADIUS)
    pygame.draw.circle(surface, (0, 0, 0), (int(bx), int(by)), BALL_RADIUS, 2)

    # scoreboard
    score_text = font_big.render(
        f"RED {match.score['red']}  -  {match.score['blue']} BLUE", True, LINE_COLOR
    )
    surface.blit(score_text, score_text.get_rect(center=(VIDEO_W // 2, 140)))

    timer_text = font_med.render(f"{match.time_elapsed:0.1f}s", True, (180, 180, 180))
    surface.blit(timer_text, timer_text.get_rect(center=(VIDEO_W // 2, 210)))

    # most recent goal caption, shown for 2s after it happens
    if match.event_log:
        t, text = match.event_log[-1]
        if match.time_elapsed - t < 2.0:
            cap = font_big.render(text, True, (255, 220, 80))
            surface.blit(cap, cap.get_rect(center=(VIDEO_W // 2, VIDEO_H - 90)))


# ---------------------------------------------------------------
# MAIN: simulate, render, pipe to ffmpeg
# ---------------------------------------------------------------
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"match_{int(time.time())}.mp4")

    pygame.init()
    surface = pygame.Surface((VIDEO_W, VIDEO_H))
    font_big = pygame.font.SysFont("arial", 64, bold=True)
    font_med = pygame.font.SysFont("arial", 36)

    match = FutsalMatch(players_per_team=3)

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{VIDEO_W}x{VIDEO_H}",
        "-r", str(FPS),
        "-i", "-",
        "-an",
        "-vcodec", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "20",
        out_path,
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

    dt = 1.0 / FPS
    total_frames = MATCH_SECONDS * FPS

    for frame_i in range(total_frames):
        for _ in range(STEPS_PER_FRAME):
            match.step(dt / STEPS_PER_FRAME)

        draw_frame(surface, match, font_big, font_med)

        # pygame surface -> raw RGB bytes -> ffmpeg stdin
        frame_bytes = pygame.image.tobytes(surface, "RGB")
        proc.stdin.write(frame_bytes)

        if frame_i % (FPS * 5) == 0:
            print(f"  ...{frame_i // FPS}s simulated "
                  f"(score {match.score['red']}-{match.score['blue']})")

    proc.stdin.close()
    proc.wait()
    print(f"\nDone. Video saved to: {out_path}")


if __name__ == "__main__":
    main()
