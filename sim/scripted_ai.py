"""Rule-based AI (scripted for now; replace with RL policy later).

`scripted_policy` is the default `policy_fn` passed into `FutsalMatch`.
To control specific players with a trained model instead, write another
`policy_fn(match, player) -> (dx, dy)` that calls `model.predict(obs)`
for the controlled players and falls back to `scripted_policy` for the
rest - the rest of the sim (physics, rendering, recording) doesn't change.
"""

import math

from .config import COURT_X, COURT_Y, COURT_W, COURT_H, PLAYER_RADIUS, BACK_LINE, FWD_LINE


def scripted_policy(match, player):
    """Returns a desired velocity vector (dx, dy) for this player."""
    body = player["body"]

    if match.time_elapsed < player["stunned_until"]:
        # still reeling from a failed tackle - can't act
        return (0, 0)

    bx, by = match.ball_body.position
    px, py = body.position
    team = player["team"]

    # red spawned side=-1 (upper half) attacks the bottom goal (+1 direction)
    attack_dir = 1 if team == "red" else -1

    if match.celebration_team is not None:
        if player not in match.celebration_players:
            # not part of the celebration - just wait for kickoff
            return (0, 0)
        # everyone who's celebrating gathers at the same spot
        target_x, target_y = match.celebration_spot
        dx, dy = target_x - px, target_y - py
        dist = math.hypot(dx, dy) or 1
        speed = 220
        return (dx / dist * speed, dy / dist * speed)

    mid_x = COURT_X + COURT_W / 2
    mid_y = COURT_Y + COURT_H / 2

    if player["role"] == "GK":
        # stay on the goal line, shuffling sideways to track the ball
        side = player["home_side"]
        lo, hi = match.goal_top_x_range
        target_x = min(max(bx, lo + PLAYER_RADIUS), hi - PLAYER_RADIUS)
        target_y = (COURT_Y + PLAYER_RADIUS + 20 if side == -1
                    else COURT_Y + COURT_H - PLAYER_RADIUS - 20)
        dx, dy = target_x - px, target_y - py
        dist = math.hypot(dx, dy) or 1
        speed = 100
        return (dx / dist * speed, dy / dist * speed)

    role = player["role"]
    home_x = mid_x + player["formation_x_offset"]
    home_y = mid_y - attack_dir * (BACK_LINE if role == "BACK" else FWD_LINE)

    if match.possessor is player:
        # carry the ball toward the attacking goal, but keep some of the
        # carrier's own lateral position instead of always beelining
        # straight at the center - that's what gives a shot an angle
        goal_y = match.court_bounds[3] if attack_dir == 1 else match.court_bounds[1]
        target_x = mid_x + player["formation_x_offset"] * 0.6
        target_y = goal_y

    elif match.possessor is not None and match.possessor["team"] != team:
        if match.possessor["role"] == "GK":
            # don't crowd the keeper - hold defensive shape and wait
            target_x, target_y = home_x, home_y
        elif role == "BACK":
            # backs mark the ball: the closest one presses, the other covers
            carrier_x, carrier_y = match.possessor["body"].position
            backs = [q for q in match.players if q["team"] == team and q["role"] == "BACK"]
            closest = min(backs, key=lambda q: math.hypot(
                q["body"].position[0] - carrier_x, q["body"].position[1] - carrier_y))
            if player is closest:
                target_x, target_y = carrier_x, carrier_y
            else:
                # stay in their own lateral zone rather than collapsing
                # onto the ball's x - that just walls off the shot lane
                own_goal_y = COURT_Y if player["home_side"] == -1 else COURT_Y + COURT_H
                target_x = home_x
                target_y = own_goal_y + (carrier_y - own_goal_y) * 0.35
        else:
            # forwards track back to a moderate holding line instead of
            # camping upfield or piling onto the tackle
            target_x, target_y = home_x, home_y

    elif match.possessor is not None:
        # own team has the ball
        if role == "FWD":
            # push forward, ahead of the ball carrier
            target_x = home_x
            target_y = match.possessor["body"].position[1] + attack_dir * 220
        else:
            # backs hold their line - an outlet option and cover against a turnover
            target_x = home_x
            target_y = home_y * 0.7 + match.possessor["body"].position[1] * 0.3

    else:
        dist_to_ball = math.hypot(bx - px, by - py)
        if dist_to_ball < 260:
            # chase the loose ball
            target_x, target_y = bx, by
        else:
            # hold a loose formation on your own half, biased toward the ball's x
            target_x = bx * 0.35 + home_x * 0.65
            target_y = by * 0.35 + home_y * 0.65

    dx, dy = target_x - px, target_y - py
    dist = math.hypot(dx, dy) or 1
    speed = 260
    return (dx / dist * speed, dy / dist * speed)
