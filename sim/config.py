"""All tunable constants for the sim and its rendering."""

import colorsys
import math
import random

# ---------------------------------------------------------------
# VIDEO / TIMING
# ---------------------------------------------------------------
VIDEO_W, VIDEO_H = 1080, 1920      # vertical output (TikTok/Reels)
FPS = 30
MATCH_SECONDS = 45                 # sim length; trim/loop as you like
STEPS_PER_FRAME = 4                # physics substeps for stability
FINAL_SCORE_HOLD_SECONDS = 3       # how long the full-time score screen stays up before closing

# ---------------------------------------------------------------
# COURT
# ---------------------------------------------------------------
COURT_MARGIN_TOP = 320             # room for scoreboard text
COURT_MARGIN_BOTTOM = 140
COURT_W = 820
COURT_H = VIDEO_H - COURT_MARGIN_TOP - COURT_MARGIN_BOTTOM
COURT_X = (VIDEO_W - COURT_W) // 2
COURT_Y = COURT_MARGIN_TOP

PLAYER_RADIUS = 26
PLAYER_COLLISION_RADIUS = PLAYER_RADIUS * 0.7      # smaller physics shape than the drawn circle,
                                                    # so two players can overlap ~0.3 of a diameter
BALL_RADIUS = 16
GOAL_WIDTH = 220                   # goal opening centered on top/bottom edge
GOAL_POST_RADIUS = 9               # physical post at each corner of the goal mouth -
                                    # blocks shots sneaking in from a sharp side angle

PENALTY_BOX_WIDTH = GOAL_WIDTH + 220   # width of the keeper's box, centered on the goal
PENALTY_BOX_DEPTH = 200                # how far the box extends into the pitch from the goal line

# ---------------------------------------------------------------
# BALL / POSSESSION
# ---------------------------------------------------------------
CONTROL_RADIUS = PLAYER_RADIUS + BALL_RADIUS       # pickup range for a loose ball - player must actually touch it
DRIBBLE_LEAD = PLAYER_RADIUS + BALL_RADIUS + 2    # ball's offset in front of its carrier
BALL_FOLLOW_EASE = 0.4                              # 0-1: how fast the ball eases toward the glue point per step
FACING_MIN_SPEED = 20                               # below this speed, keep the last facing instead of jittering
FACING_TURN_RATE = 0.15                             # 0-1: how fast facing pivots toward its target direction per step
TACKLE_RADIUS = PLAYER_RADIUS * 2 + 6               # how close a defender must get to contest
TACKLE_COOLDOWN = 0.8                               # seconds before the same carrier can be tackled again
PASS_INTERVAL = 0.7                                 # max seconds a player holds the ball before releasing it
SHOT_DIST_MIN = 90                                  # closest a shot attempt range can roll to
SHOT_DIST_MAX = 260                                 # farthest a shot attempt range can roll to (tune to taste)
SHOT_ANGLE_SPREAD = math.radians(40)                # max random aim error either side of dead-center (radians)
SHOT_POWER_MIN = 700
SHOT_POWER_MAX = 1000

CONTROL_CHANCE = 0.6                                # chance a touch is cleanly controlled, not fumbled loose
DEFLECT_SPEED = 190                                 # how fast a fumbled/tackled ball squirts away

STUN_CHANCE = 0.35                                  # chance EACH player in a failed tackle gets stunned
STUN_DURATION = 0.5                                 # seconds a stunned player can't act
STUN_KNOCKBACK = 140                                # speed a stunned player is knocked away at

KEEPER_SLIP_CHANCE = 0.12                           # chance the keeper loses their footing facing a shot
KEEPER_SLIP_DURATION = 0.4                          # seconds a slipped keeper can't react

BACK_LINE = COURT_H * 0.36                          # how deep backs sit in their own half at rest
FWD_LINE = COURT_H * 0.12                           # how deep forwards sit in their own half at rest

BACK_SPACING = 280                                  # lateral gap between the two backs

# forwards form a winger + central striker pair rather than two symmetric
# wingers - only one hugs the touchline (toned down from before), the
# other always sits centrally as the focal point of the attack
FWD_WING_OFFSET = 300
FWD_STRIKER_OFFSET = 0
FWD_SPACING = 600                                   # fallback spacing if players_per_team ever gives >2 forwards

CELEBRATION_DURATION = 2.0                          # seconds the scoring team celebrates before kickoff resets

# ---------------------------------------------------------------
# COLORS
# ---------------------------------------------------------------
# (name, hue) pairs, hand-picked so the name is always an accurate
# description of that exact hue - avoids picking a random continuous hue
# and then guessing its name afterward, which can land near a boundary
# and read as the wrong color for the label
_NAMED_HUES = [
    ("Red", 0.0), ("Orange", 0.07), ("Amber", 0.11), ("Yellow", 0.15),
    ("Lime", 0.25), ("Green", 0.33), ("Teal", 0.45), ("Cyan", 0.5),
    ("Azure", 0.58), ("Blue", 0.66), ("Violet", 0.75), ("Magenta", 0.83),
    ("Pink", 0.92),
]


def _hue_distance(a, b):
    d = abs(a - b) % 1.0
    return min(d, 1.0 - d)


def random_team_colors():
    """Two random, visually distinct kit colors + display names, keyed by
    the internal "red"/"blue" team ids (those ids are just opaque keys -
    not tied to the actual displayed color/name). Returns (colors, labels)."""
    name_a, hue_a = random.choice(_NAMED_HUES)
    candidates = [(n, h) for n, h in _NAMED_HUES if _hue_distance(h, hue_a) >= 0.25]
    name_b, hue_b = random.choice(candidates)

    r1, g1, b1 = colorsys.hsv_to_rgb(hue_a, 0.75, 0.85)
    r2, g2, b2 = colorsys.hsv_to_rgb(hue_b, 0.75, 0.85)
    colors = {
        "red": (int(r1 * 255), int(g1 * 255), int(b1 * 255)),
        "blue": (int(r2 * 255), int(g2 * 255), int(b2 * 255)),
    }
    labels = {"red": name_a, "blue": name_b}
    return colors, labels


BALL_COLOR = (240, 240, 240)
COURT_COLOR = (35, 110, 60)
LINE_COLOR = (235, 235, 235)
BG_COLOR = (18, 18, 22)

OUTPUT_DIR = "output"
