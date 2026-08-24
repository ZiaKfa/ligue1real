"""Rule-based AI (scripted for now; replace with RL policy later).

`scripted_policy` is the default `policy_fn` passed into `FutsalMatch`.
To control specific players with a trained model instead, write another
`policy_fn(match, player) -> (dx, dy)` that calls `model.predict(obs)`
for the controlled players and falls back to `scripted_policy` for the
rest - the rest of the sim (physics, rendering, recording) doesn't change.
"""

import math

from .config import (
    COURT_X, COURT_Y, COURT_W, COURT_H, PLAYER_RADIUS, BACK_LINE, FWD_LINE,
    FWD_WING_OFFSET, FWD_STRIKER_OFFSET, PENALTY_BOX_WIDTH, PENALTY_BOX_DEPTH,
    FWD_RUN_AHEAD_DISTANCE, stat_scale,
)


def scripted_policy(match, player):
    """Returns a desired velocity vector (dx, dy) for this player."""
    body = player["body"]

    if match.time_elapsed < player["stunned_until"]:
        # still reeling from a failed tackle - can't act
        return (0, 0)

    bx, by = match.ball_body.position
    px, py = body.position
    team = player["team"]

    # side=-1 (upper half) attacks the bottom goal (+1 direction), mirrored for side=1
    attack_dir = -player["home_side"]

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
        # roam the whole penalty box, not just the goal mouth width - shuffle
        # sideways to track the ball, and edge off the line as the ball gets
        # deeper into the box (classic "narrow the angle" positioning)
        side = player["home_side"]
        box_lo = mid_x - PENALTY_BOX_WIDTH / 2
        box_hi = mid_x + PENALTY_BOX_WIDTH / 2
        target_x = min(max(bx, box_lo + PLAYER_RADIUS), box_hi - PLAYER_RADIUS)

        rest_y = (COURT_Y + PLAYER_RADIUS + 20 if side == -1
                  else COURT_Y + COURT_H - PLAYER_RADIUS - 20)
        goal_line_y = COURT_Y if side == -1 else COURT_Y + COURT_H
        into_court_dir = 1 if side == -1 else -1
        ball_depth = max(0.0, min(PENALTY_BOX_DEPTH, (by - goal_line_y) * into_court_dir))
        target_y = rest_y + into_court_dir * ball_depth * 0.3

        dx, dy = target_x - px, target_y - py
        dist = math.hypot(dx, dy) or 1
        speed = 100 * stat_scale(player["stats"]["pace"])
        return (dx / dist * speed, dy / dist * speed)

    role = player["role"]

    if role == "FWD":
        # dynamic winger/striker pair, re-decided every step from the ball's
        # current position: whichever forward is nearer the ball's side
        # stretches wide onto that flank; the other tucks in as the central
        # striker. No fixed identity - either one can be the winger depending
        # on how play is developing right now.
        fwd_teammates = [q for q in match.players
                          if q["team"] == team and q["role"] == "FWD" and q is not player]
        if fwd_teammates:
            other = fwd_teammates[0]
            is_wide_one = abs(bx - px) <= abs(bx - other["body"].position[0])
            if is_wide_one:
                wing_side = 1 if bx >= mid_x else -1
                lateral_offset = wing_side * FWD_WING_OFFSET
            else:
                lateral_offset = FWD_STRIKER_OFFSET
        else:
            lateral_offset = player["formation_x_offset"]
    else:
        lateral_offset = player["formation_x_offset"]

    home_x = mid_x + lateral_offset
    home_y = mid_y - attack_dir * (BACK_LINE if role == "BACK" else FWD_LINE)

    if match.possessor is player:
        # carry the ball toward the attacking goal, but hold onto most of
        # the carrier's own lateral position instead of beelining straight
        # at the center - that's what makes wing play happen instead of
        # every attack funneling down the middle, and still gives a shot
        # an angle once they do cut inside
        goal_y = match.court_bounds[3] if attack_dir == 1 else match.court_bounds[1]
        target_x = mid_x + lateral_offset * 0.95
        target_y = goal_y

        # a defender closing in from ahead gets juked sideways/backward
        # instead of driven straight into - avoids crowding a defender
        # (or the wall behind them) head-on every single time
        nearest_opp = min(
            (q for q in match.players if q["team"] != team),
            key=lambda q: math.hypot(q["body"].position[0] - px, q["body"].position[1] - py),
        )
        ox, oy = nearest_opp["body"].position
        opp_dist = math.hypot(ox - px, oy - py)
        blocking_ahead = (oy - py) * attack_dir > 0
        if opp_dist < 100 and blocking_ahead:
            away_side = -1 if ox >= px else 1
            target_x = px + away_side * 150
            if abs(py - goal_y) < 80:
                # boxed in right against the goal line - step back for room
                target_y = py - attack_dir * 40
            # otherwise just sidestep (target_y stays goal_y) - combined
            # with the x shift that already reads as a diagonal juke

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
            target_y = match.possessor["body"].position[1] + attack_dir * FWD_RUN_AHEAD_DISTANCE
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

    # never send a player's target beyond the playable pitch - e.g. "push
    # forward ahead of the ball carrier" can otherwise extend past the goal
    # line, and the goal mouth is a real physical gap (so nothing stops a
    # player lined up with it from running straight out of bounds through it)
    margin = PLAYER_RADIUS
    target_x = min(max(target_x, COURT_X + margin), COURT_X + COURT_W - margin)
    target_y = min(max(target_y, COURT_Y + margin), COURT_Y + COURT_H - margin)

    dx, dy = target_x - px, target_y - py
    tdist = math.hypot(dx, dy) or 1
    dx, dy = dx / tdist, dy / tdist  # unit vector toward the target

    # nudge away from a teammate standing right on top of you - weighted
    # as a unit vector too, so it can actually outweigh target-seeking when
    # severely overlapped instead of being drowned out by a distant target.
    # covers every transition (e.g. both forwards separating after the
    # keeper picks up a save) without needing per-scenario spacing logic
    for mate in match.players:
        if mate is player or mate["team"] != team:
            continue
        mx, my = mate["body"].position
        mdist = math.hypot(px - mx, py - my)
        if 0 < mdist < PLAYER_RADIUS * 2:
            overlap = (PLAYER_RADIUS * 2 - mdist) / (PLAYER_RADIUS * 2)  # 0..1
            dx += (px - mx) / mdist * overlap * 2.0
            dy += (py - my) / mdist * overlap * 2.0

    dist = math.hypot(dx, dy) or 1
    speed = 260 * stat_scale(player["stats"]["pace"])
    return (dx / dist * speed, dy / dist * speed)
