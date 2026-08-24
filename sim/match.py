"""Physics world and game rules for a futsal match."""

import math
import random

import pymunk

from .config import (
    COURT_X, COURT_Y, COURT_W, COURT_H, PLAYER_RADIUS, PLAYER_COLLISION_RADIUS,
    BALL_RADIUS, GOAL_WIDTH, GOAL_POST_RADIUS, CONTROL_RADIUS, DRIBBLE_LEAD, BALL_FOLLOW_EASE, TACKLE_RADIUS,
    TACKLE_COOLDOWN, PASS_INTERVAL, PASS_POWER, SHOT_DIST_MIN, SHOT_DIST_MAX, SHOT_ANGLE_SPREAD,
    SHOT_POWER_MIN, SHOT_POWER_MAX, CONTROL_CHANCE, DEFLECT_SPEED, STUN_CHANCE,
    STUN_DURATION, STUN_KNOCKBACK, KEEPER_SLIP_CHANCE, KEEPER_SLIP_DURATION,
    BACK_LINE, FWD_LINE, BACK_SPACING, FWD_SPACING, FWD_WING_OFFSET, FWD_STRIKER_OFFSET,
    CELEBRATION_DURATION, FACING_MIN_SPEED, FACING_TURN_RATE, random_team_colors,
    DEFAULT_STATS, stat_scale,
)
from .scripted_ai import scripted_policy


def _normalize_team(team, default_name):
    """teams= elements can be None (default), a plain name string, or a
    dict {"name":..., "color":..., "roster":...} - normalize all three to one shape."""
    if team is None:
        return {"name": default_name, "color": None, "roster": None}
    if isinstance(team, str):
        return {"name": team, "color": None, "roster": None}
    return {
        "name": team.get("name") or default_name,
        "color": team.get("color"),
        "roster": team.get("roster"),
    }


class FutsalMatch:
    def __init__(self, players_per_team=5, seed=None, policy_fn=None, teams=(None, None)):
        if seed is not None:
            random.seed(seed)

        # the AI that decides each player's desired velocity every step.
        # swap this for a wrapper that calls a trained RL policy for some
        # players and falls back to scripted_policy for the rest - nothing
        # else in the sim needs to change (see RL_SCALABILITY_PLAN.md).
        self.policy_fn = policy_fn or scripted_policy

        self.space = pymunk.Space()
        self.space.damping = 0.55  # friction-like slowdown each step

        cfg_a = _normalize_team(teams[0], "red")
        cfg_b = _normalize_team(teams[1], "blue")
        name_a, name_b = cfg_a["name"], cfg_b["name"]
        # side = -1 -> defends top goal, attacks bottom; side = 1 -> mirrored
        self.team_names = (name_a, name_b)
        self.team_by_side = {-1: name_a, 1: name_b}
        self.home_side_by_team = {name_a: -1, name_b: 1}

        self.score = {name_a: 0, name_b: 0}
        self.team_colors, self.team_labels = random_team_colors(name_a, name_b)
        # a custom name replaces the auto-generated color-name label outright -
        # everything downstream (scoreboard, commentary) just reads team_labels,
        # so this is the only place that needs to know "was this customized?"
        if cfg_a["color"]:
            self.team_colors[name_a] = cfg_a["color"]
        if teams[0] is not None:
            self.team_labels[name_a] = name_a
        if cfg_b["color"]:
            self.team_colors[name_b] = cfg_b["color"]
        if teams[1] is not None:
            self.team_labels[name_b] = name_b

        self.event_log = []  # (time, text, team) for on-screen captions; team picks the caption's color
        self.time_elapsed = 0.0    # simulation clock - always runs, drives cooldowns
        self.match_clock = 0.0     # displayed match timer - pauses during celebrations

        self.possessor = None          # player dict currently carrying the ball, or None
        self.received_from_keeper = None   # player who must not immediately pass straight back to the keeper
        self.last_toucher = None       # player dict who last gained controlled possession - credited with a goal
                                        # if their team scores before anyone else takes control (covers shots,
                                        # dribble-ins, and loose passes that roll straight in untouched)
        self.pending_assist = None     # player dict who made the pass that put last_toucher through
        self.pending_assist_target = None  # who that pass was intended for - assist stays valid only if they're the one who ends up as last_toucher
        self.next_tackle_time = 0.0    # cooldown so a tackle isn't rolled every physics substep
        self.next_release_time = 0.0   # when the current carrier must pass/shoot
        self.pickup_exempt = []        # players who can't re-collect the just-released ball
        self.pickup_cooldown_until = 0.0   # ...until this time
        self.celebration_team = None   # team currently celebrating a goal, or None
        self.celebration_until = 0.0
        self.celebration_players = []  # players who actually join the celebration
        self.celebration_spot = (0.0, 0.0)   # single point everyone gathers at

        self._build_walls()
        self.ball_body, self.ball_shape = self._make_ball()
        self.players = []  # list of dicts: body, shape, team, role

        self._spawn_team(name_a, players_per_team, side=-1, roster=cfg_a["roster"])
        self._spawn_team(name_b, players_per_team, side=1, roster=cfg_b["roster"])

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

        # goal posts: real obstacles at each corner of the goal mouth, so a
        # shot from a sharp side angle clangs off the post instead of
        # sliding straight in along the goal line
        self.goal_posts = [
            (mid_x - GOAL_WIDTH / 2, top), (mid_x + GOAL_WIDTH / 2, top),
            (mid_x - GOAL_WIDTH / 2, bottom), (mid_x + GOAL_WIDTH / 2, bottom),
        ]
        for post_x, post_y in self.goal_posts:
            post = pymunk.Circle(self.space.static_body, GOAL_POST_RADIUS, (post_x, post_y))
            post.elasticity = 0.9
            post.friction = 0.3
            self.space.add(post)

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

    def _spawn_team(self, team, count, side, roster=None):
        # side = -1 -> defends top goal, attacks bottom; side = 1 -> mirrored
        # player 0 is the goalkeeper; the rest split evenly into backs (sit
        # deep, mark the ball) and forwards (push further upfield)
        mid_x = COURT_X + COURT_W / 2
        mid_y = COURT_Y + COURT_H / 2
        outfield_count = count - 1
        back_count = outfield_count // 2

        for i in range(count):
            mass = 4
            moment = pymunk.moment_for_circle(mass, 0, PLAYER_RADIUS)
            body = pymunk.Body(mass, moment)

            if i == 0:
                role = "GK"
                offset = 0
                x = mid_x
                y = (COURT_Y + PLAYER_RADIUS + 20 if side == -1
                     else COURT_Y + COURT_H - PLAYER_RADIUS - 20)
            else:
                if i - 1 < back_count:
                    role, slot, slot_count, line, spacing = "BACK", i - 1, back_count, BACK_LINE, BACK_SPACING
                    offset = (slot - (slot_count - 1) / 2) * spacing
                else:
                    role, slot, slot_count, line = (
                        "FWD", i - 1 - back_count, outfield_count - back_count, FWD_LINE)
                    if slot_count == 2:
                        # winger + central striker pair, not two symmetric wingers
                        offset = FWD_WING_OFFSET if slot == 0 else FWD_STRIKER_OFFSET
                    else:
                        offset = (slot - (slot_count - 1) / 2) * FWD_SPACING
                x = mid_x + offset
                y = mid_y + side * line

            body.position = (x, y)
            shape = pymunk.Circle(body, PLAYER_COLLISION_RADIUS)
            shape.elasticity = 0.6
            shape.friction = 0.6
            shape.collision_type = 2
            self.space.add(body, shape)
            attack_dir = -side

            # roster entries are matched positionally (index 0 = GK, then
            # spawn order) - missing/short roster or missing stat keys all
            # fall back to DEFAULT_STATS, so a partial roster never crashes
            entry = roster[i] if roster and i < len(roster) else None
            stats = {**DEFAULT_STATS, **(entry.get("stats", {}) if entry else {})}
            name = entry.get("name") if entry else None
            face = entry.get("face") if entry else None

            self.players.append({
                "body": body, "shape": shape, "team": team,
                "home_side": side, "id": f"{team}_{i}", "number": i + 1,
                "role": role,
                "formation_x_offset": offset,
                "spawn_pos": (x, y),
                "stunned_until": 0.0,
                "facing": (0.0, attack_dir),  # unit vector; starts facing the attacking goal
                "stats": stats,
                "name": name,
                "face": face,
                "goals": 0,
                "assists": 0,
            })

    def _name(self, p):
        """Human-readable player label for commentary, e.g. "Magenta Player 1" or a custom roster name."""
        return p["name"] or f"{self.team_labels[p['team']]} Player {p['number']}"

    def start_second_half(self):
        """Teams swap ends, like real football - flips each player's
        home_side and mirrors their kickoff position/facing across the
        halfway line. Ball resets to center; who gets it is decided the
        same way the match's very first kickoff is (closest player wins
        the loose ball), so no explicit kickoff-team bookkeeping is needed."""
        mid_y = COURT_Y + COURT_H / 2
        self.team_by_side = {-1: self.team_by_side[1], 1: self.team_by_side[-1]}
        self.home_side_by_team = {team: -side for team, side in self.home_side_by_team.items()}

        for p in self.players:
            p["home_side"] *= -1
            x, y = p["spawn_pos"]
            p["spawn_pos"] = (x, 2 * mid_y - y)
            p["body"].position = p["spawn_pos"]
            p["body"].velocity = (0, 0)
            p["facing"] = (0.0, -p["home_side"])

        self.ball_body.position = (COURT_X + COURT_W / 2, mid_y)
        self.ball_body.velocity = (0, 0)
        self.possessor = None
        self.pickup_exempt = []
        self.pickup_cooldown_until = 0.0

    # -- step --------------------------------------------------------
    def step(self, dt):
        bx, by = self.ball_body.position
        for p in self.players:
            desired_vx, desired_vy = self.policy_fn(self, p)
            cur_vx, cur_vy = p["body"].velocity
            turn = 0.25  # 0-1: how fast a player accelerates/turns toward its desired velocity
            new_vx = cur_vx + (desired_vx - cur_vx) * turn
            new_vy = cur_vy + (desired_vy - cur_vy) * turn
            p["body"].velocity = (new_vx, new_vy)

            if p["role"] == "GK":
                # keepers track the ball with their body even while
                # shuffling sideways along the goal line - basing facing on
                # velocity alone would make them "face" purely sideways
                px, py = p["body"].position
                target_fx, target_fy = bx - px, by - py
                fdist = math.hypot(target_fx, target_fy) or 1
                target_fx, target_fy = target_fx / fdist, target_fy / fdist
            else:
                speed = math.hypot(new_vx, new_vy)
                if speed >= FACING_MIN_SPEED:
                    target_fx, target_fy = new_vx / speed, new_vy / speed
                else:
                    target_fx, target_fy = p["facing"]  # no strong signal - hold current facing

            # pivot gradually toward the target facing instead of snapping
            # straight to it - a sharp juke/turn shouldn't instantly flip
            # which side the ball is glued to
            old_fx, old_fy = p["facing"]
            fx = old_fx + (target_fx - old_fx) * FACING_TURN_RATE
            fy = old_fy + (target_fy - old_fy) * FACING_TURN_RATE
            fdist2 = math.hypot(fx, fy) or 1
            p["facing"] = (fx / fdist2, fy / fdist2)

        self.space.step(dt)
        self.time_elapsed += dt
        if self.celebration_team is None:
            self.match_clock += dt
        # goal detection must run before possession pickup - otherwise a
        # keeper standing right on the line can "catch" a ball whose
        # position has already crossed it in this same frame, which wipes
        # last_toucher/pending_assist before _check_goal gets to credit them
        self._check_goal()
        self._update_possession()
        self._update_celebration()

    # -- ball possession: pickup, dribble, tackle, pass/shoot --------
    def _update_possession(self):
        if self.celebration_team is not None:
            # ball's parked at center for the celebration - nothing to pick
            # up until _update_celebration hands it to the kicker for kickoff
            return

        bx, by = self.ball_body.position

        if self.possessor is None:
            # loose ball: closest player within pickup range takes it
            # (whoever just released it, or was beaten by a shot, can't
            # immediately re-collect it - gives a strike a chance to travel)
            exempt = self.pickup_exempt if self.time_elapsed < self.pickup_cooldown_until else ()
            closest, closest_dist = None, CONTROL_RADIUS
            for p in self.players:
                if p in exempt:
                    continue
                px, py = p["body"].position
                dist = math.hypot(bx - px, by - py)
                if dist < closest_dist:
                    closest, closest_dist = p, dist
            if closest is not None:
                if random.random() < CONTROL_CHANCE:
                    # whoever just gained real control is now the one on the
                    # hook for the next goal - a shot that merely grazes past
                    # a keeper/defender without them taking it (see the
                    # fumble branch below) doesn't break the chain, only an
                    # actual change of possession does
                    if closest is not self.pending_assist_target:
                        self.pending_assist = None
                        self.pending_assist_target = None
                    self.last_toucher = closest

                    self.possessor = closest
                    self.next_release_time = self.time_elapsed + PASS_INTERVAL
                else:
                    # not everyone has perfect first touch - it squirts loose
                    # instead of being cleanly controlled
                    angle = random.uniform(0, 2 * math.pi)
                    self.ball_body.velocity = (math.cos(angle) * DEFLECT_SPEED, math.sin(angle) * DEFLECT_SPEED)
                    self.pickup_exempt = [closest]
                    self.pickup_cooldown_until = self.time_elapsed + 0.2
            return

        p = self.possessor
        px, py = p["body"].position
        attack_dir = -p["home_side"]

        # glue the ball to its carrier, slightly ahead of wherever they're
        # actually facing (last moving direction) - not always straight
        # toward the opponent's goal, so dribbling sideways/backward looks right
        fx, fy = p["facing"]
        bx_new = px + fx * DRIBBLE_LEAD
        by_new = py + fy * DRIBBLE_LEAD

        # a carrier near a wall can face straight into it - clamp so the
        # glued ball can't snap outside the court, except through the goal
        # mouth itself (dribbling the ball into the net is still allowed)
        left, top, right, bottom = self.court_bounds
        bx_new = min(max(bx_new, left + BALL_RADIUS), right - BALL_RADIUS)
        lo, hi = self.goal_top_x_range
        if not (lo <= bx_new <= hi):
            by_new = min(max(by_new, top + BALL_RADIUS), bottom - BALL_RADIUS)

        # ease toward the glue point instead of snapping straight to it -
        # a hard position reset every step is what made dribbling look rigid
        cur_bx, cur_by = self.ball_body.position
        bx_new = cur_bx + (bx_new - cur_bx) * BALL_FOLLOW_EASE
        by_new = cur_by + (by_new - cur_by) * BALL_FOLLOW_EASE

        self.ball_body.position = (bx_new, by_new)
        self.ball_body.velocity = p["body"].velocity

        # a defender close enough gets a shot at winning the ball - 50/50 at
        # equal tackling stat, shifted by the gap between the two players'
        if self.time_elapsed >= self.next_tackle_time:
            for opp in self.players:
                if opp["team"] == p["team"]:
                    continue
                ox, oy = opp["body"].position
                if math.hypot(px - ox, py - oy) < TACKLE_RADIUS:
                    self.next_tackle_time = self.time_elapsed + TACKLE_COOLDOWN
                    tackle_chance = 0.5 + (opp["stats"]["tackling"] - p["stats"]["tackling"]) / 200
                    tackle_chance = max(0.2, min(0.8, tackle_chance))
                    if random.random() < tackle_chance:
                        # the ball is knocked loose, not cleanly won - it
                        # squirts away for a genuine 50/50 second ball
                        self.event_log.append((self.time_elapsed, f"TACKLE! {self._name(opp)} knocks it loose", opp["team"]))
                        angle = random.uniform(0, 2 * math.pi)
                        self.ball_body.velocity = (math.cos(angle) * DEFLECT_SPEED, math.sin(angle) * DEFLECT_SPEED)
                        self.possessor = None
                        self.pickup_exempt = []
                        self.pickup_cooldown_until = 0.0
                    else:
                        # tackle failed - the challenge still had impact, each
                        # player has their own independent chance of being
                        # left stunned by the collision
                        if random.random() < STUN_CHANCE:
                            self._stun(p, away_from=(ox, oy))
                        if random.random() < STUN_CHANCE:
                            self._stun(opp, away_from=(px, py))
                    break
            if self.possessor is not p:
                return  # tackle succeeded; ball is loose for the taking

        # shoot once within (randomized) shooting range, otherwise pass on
        # when the hold time runs out
        goal_x = COURT_X + COURT_W / 2
        goal_y = self.court_bounds[3] if attack_dir == 1 else self.court_bounds[1]
        dist_to_goal = math.hypot(goal_x - px, goal_y - py)

        if dist_to_goal < random.uniform(SHOT_DIST_MIN, SHOT_DIST_MAX):
            self._release_ball(p, shoot=True)
        elif self.time_elapsed >= self.next_release_time:
            self._release_ball(p, shoot=False)

    def _release_ball(self, p, shoot):
        team = p["team"]
        attack_dir = -p["home_side"]
        bx, by = self.ball_body.position

        if shoot:
            # aim at the goal but with a random angle error - can miss wide.
            # a better shooter hits harder and straighter; a lower shooting
            # stat does the opposite - both scale from the same neutral point
            shooting = p["stats"]["shooting"]
            goal_x = COURT_X + COURT_W / 2
            goal_y = self.court_bounds[3] if attack_dir == 1 else self.court_bounds[1]
            angle = math.atan2(goal_y - by, goal_x - bx)
            angle += random.uniform(-SHOT_ANGLE_SPREAD, SHOT_ANGLE_SPREAD) * stat_scale(shooting, invert=True)
            target_x = bx + math.cos(angle) * 1000
            target_y = by + math.sin(angle) * 1000
            power = random.uniform(SHOT_POWER_MIN, SHOT_POWER_MAX) * stat_scale(shooting)
            self.event_log.append((self.time_elapsed, f"{self._name(p)} shoots!", team))

            keeper = next((q for q in self.players if q["team"] != team and q["role"] == "GK"), None)
            if keeper is not None:
                slip_chance = KEEPER_SLIP_CHANCE * stat_scale(keeper["stats"]["reflex"], invert=True)
                if random.random() < slip_chance:
                    keeper["stunned_until"] = self.time_elapsed + KEEPER_SLIP_DURATION
                    self.event_log.append((self.time_elapsed, f"{self._name(keeper)} slips!", keeper["team"]))
            self.received_from_keeper = None
        else:
            teammates = [q for q in self.players if q["team"] == team and q is not p]
            if self.received_from_keeper is p:
                # this player just got the ball from their own keeper - don't
                # shuttle it straight back (covering backs can sit deeper than
                # the keeper's line, which made "most advanced teammate" pick
                # the keeper and caused a back<->keeper loop). A normal
                # back-pass later in the move is still allowed.
                teammates = [q for q in teammates if q["role"] != "GK"]
            target = max(teammates, key=lambda q: attack_dir * q["body"].position[1])
            target_x, target_y = target["body"].position
            power = PASS_POWER
            self.event_log.append((self.time_elapsed, f"{self._name(p)} passes", team))
            self.received_from_keeper = target if p["role"] == "GK" else None
            self.pending_assist = p
            self.pending_assist_target = target

        kx, ky = target_x - bx, target_y - by
        kd = math.hypot(kx, ky) or 1
        self.ball_body.velocity = (kx / kd * power, ky / kd * power)
        self.possessor = None

        if shoot:
            # any marker standing right next to the shooter got beaten by
            # the strike - they don't get a free instant re-block
            beaten = [q for q in self.players if q["team"] != team and math.hypot(
                q["body"].position[0] - bx, q["body"].position[1] - by) < TACKLE_RADIUS]
            self.pickup_exempt = [p] + beaten
        else:
            self.pickup_exempt = [p]
        self.pickup_cooldown_until = self.time_elapsed + 0.35

    def _stun(self, player, away_from):
        # knock the player back along the real 2D line between the two
        # bodies (not just up/down the court) and freeze them briefly
        player["stunned_until"] = self.time_elapsed + STUN_DURATION
        ax, ay = player["body"].position
        fx, fy = away_from
        dx, dy = ax - fx, ay - fy
        d = math.hypot(dx, dy) or 1
        player["body"].velocity = (dx / d * STUN_KNOCKBACK, dy / d * STUN_KNOCKBACK)
        self.event_log.append((self.time_elapsed, f"{self._name(player)} is stunned!", player["team"]))

        if self.possessor is player:
            # can't stay in control while reeling from the hit - ball spills loose
            angle = random.uniform(0, 2 * math.pi)
            self.ball_body.velocity = (math.cos(angle) * DEFLECT_SPEED, math.sin(angle) * DEFLECT_SPEED)
            self.possessor = None
            self.pickup_exempt = [player]
            self.pickup_cooldown_until = self.time_elapsed + 0.3

    def _check_goal(self):
        bx, by = self.ball_body.position
        left, top, right, bottom = self.court_bounds
        lo, hi = self.goal_top_x_range
        scored = None
        if by <= top + BALL_RADIUS and lo <= bx <= hi:
            scored = self.team_by_side[1]    # ball entered top goal -> the team attacking top scored
        elif by >= bottom - BALL_RADIUS and lo <= bx <= hi:
            scored = self.team_by_side[-1]   # ball entered bottom goal -> the team attacking bottom scored

        if scored:
            self.score[scored] += 1

            # credit whoever last had the ball, but only if it's actually the
            # scoring team - an own goal or a stray deflection with no valid
            # chain simply isn't attributed to anyone
            scorer = self.last_toucher if (self.last_toucher is not None
                                            and self.last_toucher["team"] == scored) else None
            text = (f"GOAL! {self._name(scorer)} scores!" if scorer is not None
                    else f"GOAL! {self.team_labels[scored].upper()} scores!")
            self.event_log.append((self.time_elapsed, text, scored))

            if scorer is not None:
                scorer["goals"] += 1
                if (self.pending_assist is not None and self.pending_assist["team"] == scored
                        and self.pending_assist is not scorer):
                    self.pending_assist["assists"] += 1
            self.last_toucher = None
            self.pending_assist = None
            self.pending_assist_target = None

            # backs only join the celebration if they were already forward,
            # in the opponent's half, when the goal went in - forwards always join
            attack_dir = -self.home_side_by_team[scored]
            mid_y = COURT_Y + COURT_H / 2
            self.celebration_players = []
            for p in self.players:
                if p["team"] != scored or p["role"] == "GK":
                    continue
                if p["role"] == "FWD":
                    self.celebration_players.append(p)
                else:
                    py = p["body"].position[1]
                    in_opponent_half = py > mid_y if attack_dir == 1 else py < mid_y
                    if in_opponent_half:
                        self.celebration_players.append(p)

            # everyone who joins gathers at the same spot, near the corner
            # closest to where the ball actually went in
            mid_x = COURT_X + COURT_W / 2
            side_x = COURT_X + 60 if bx < mid_x else COURT_X + COURT_W - 60
            self.celebration_spot = (side_x, by)

            self.ball_body.position = (COURT_X + COURT_W / 2, COURT_Y + COURT_H / 2)
            self.ball_body.velocity = (0, 0)
            self.possessor = None
            self.celebration_team = scored
            self.celebration_until = self.time_elapsed + CELEBRATION_DURATION

    def _update_celebration(self):
        if self.celebration_team is not None and self.time_elapsed >= self.celebration_until:
            name_a, name_b = self.team_names
            conceding_team = name_b if self.celebration_team == name_a else name_a
            self.celebration_team = None
            self.celebration_players = []
            for p in self.players:
                p["body"].position = p["spawn_pos"]
                p["body"].velocity = (0, 0)

            # the team that conceded kicks off, not whoever reaches the
            # ball first - mirrors real kickoff rules after a goal
            kicker = next(p for p in self.players if p["team"] == conceding_team and p["role"] == "FWD")
            self.possessor = kicker
            self.next_release_time = self.time_elapsed + PASS_INTERVAL
