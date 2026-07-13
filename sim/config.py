"""All tunable constants for the sim and its rendering."""

import math

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
BALL_RADIUS = 14
GOAL_WIDTH = 220                   # goal opening centered on top/bottom edge
GOAL_POST_RADIUS = 9               # physical post at each corner of the goal mouth -
                                    # blocks shots sneaking in from a sharp side angle

# ---------------------------------------------------------------
# BALL / POSSESSION
# ---------------------------------------------------------------
CONTROL_RADIUS = PLAYER_RADIUS + BALL_RADIUS + 6   # pickup range for a loose ball
DRIBBLE_LEAD = PLAYER_RADIUS + BALL_RADIUS + 4      # ball's offset in front of its carrier
TACKLE_RADIUS = PLAYER_RADIUS * 2 + 6               # how close a defender must get to contest
TACKLE_COOLDOWN = 0.8                               # seconds before the same carrier can be tackled again
PASS_INTERVAL = 1.4                                 # max seconds a player holds the ball before releasing it
SHOT_DIST_MIN = 90                                  # closest a shot attempt range can roll to
SHOT_DIST_MAX = 260                                 # farthest a shot attempt range can roll to (tune to taste)
SHOT_ANGLE_SPREAD = math.radians(40)                # max random aim error either side of dead-center (radians)
SHOT_POWER_MIN = 460
SHOT_POWER_MAX = 720

CONTROL_CHANCE = 0.6                                # chance a touch is cleanly controlled, not fumbled loose
DEFLECT_SPEED = 190                                 # how fast a fumbled/tackled ball squirts away

STUN_CHANCE = 0.35                                  # chance EACH player in a failed tackle gets stunned
STUN_DURATION = 0.5                                 # seconds a stunned player can't act
STUN_KNOCKBACK = 140                                # speed a stunned player is knocked away at

KEEPER_SLIP_CHANCE = 0.12                           # chance the keeper loses their footing facing a shot
KEEPER_SLIP_DURATION = 0.4                          # seconds a slipped keeper can't react

BACK_LINE = COURT_H * 0.36                          # how deep backs sit in their own half at rest
FWD_LINE = COURT_H * 0.12                           # how deep forwards sit in their own half at rest

BACK_SPACING = 200                                  # lateral gap between the two backs

# forwards form a winger + central striker pair rather than two symmetric
# wingers - only one hugs the touchline (toned down from before), the
# other always sits centrally as the focal point of the attack
FWD_WING_OFFSET = 220
FWD_STRIKER_OFFSET = 0
FWD_SPACING = 600                                   # fallback spacing if players_per_team ever gives >2 forwards

CELEBRATION_DURATION = 2.0                          # seconds the scoring team celebrates before kickoff resets

# ---------------------------------------------------------------
# COLORS
# ---------------------------------------------------------------
TEAM_RED = (230, 70, 70)
TEAM_BLUE = (70, 130, 230)
BALL_COLOR = (240, 240, 240)
COURT_COLOR = (35, 110, 60)
LINE_COLOR = (235, 235, 235)
BG_COLOR = (18, 18, 22)

OUTPUT_DIR = "output"
