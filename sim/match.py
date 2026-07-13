"""Physics world and game rules for a futsal match."""

import math
import random

import pymunk

from .config import (
    COURT_X, COURT_Y, COURT_W, COURT_H, PLAYER_RADIUS, PLAYER_COLLISION_RADIUS,
    BALL_RADIUS, GOAL_WIDTH, GOAL_POST_RADIUS, CONTROL_RADIUS, DRIBBLE_LEAD, TACKLE_RADIUS,
    TACKLE_COOLDOWN, PASS_INTERVAL, SHOT_DIST_MIN, SHOT_DIST_MAX, SHOT_ANGLE_SPREAD,
    SHOT_POWER_MIN, SHOT_POWER_MAX, CONTROL_CHANCE, DEFLECT_SPEED, STUN_CHANCE,
    STUN_DURATION, STUN_KNOCKBACK, KEEPER_SLIP_CHANCE, KEEPER_SLIP_DURATION,
    BACK_LINE, FWD_LINE, BACK_SPACING, FWD_SPACING, FWD_WING_OFFSET, FWD_STRIKER_OFFSET,
    CELEBRATION_DURATION,
)
from .scripted_ai import scripted_policy


class FutsalMatch:
    def __init__(self, players_per_team=5, seed=None, policy_fn=None):
        if seed is not None:
            random.seed(seed)

        # the AI that decides each player's desired velocity every step.
        # swap this for a wrapper that calls a trained RL policy for some
        # players and falls back to scripted_policy for the rest - nothing
        # else in the sim needs to change (see RL_SCALABILITY_PLAN.md).
        self.policy_fn = policy_fn or scripted_policy

        self.space = pymunk.Space()
        self.space.damping = 0.55  # friction-like slowdown each step

        self.score = {"red": 0, "blue": 0}
        self.event_log = []  # (time, text) for on-screen captions
        self.time_elapsed = 0.0    # simulation clock - always runs, drives cooldowns
        self.match_clock = 0.0     # displayed match timer - pauses during celebrations

        self.possessor = None          # player dict currently carrying the ball, or None
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

    def _spawn_team(self, team, count, side):
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
            self.players.append({
                "body": body, "shape": shape, "team": team,
                "home_side": side, "id": f"{team}_{i}",
                "role": role,
                "formation_x_offset": offset,
                "spawn_pos": (x, y),
                "stunned_until": 0.0,
            })

    # -- step --------------------------------------------------------
    def step(self, dt):
        for p in self.players:
            desired_vx, desired_vy = self.policy_fn(self, p)
            cur_vx, cur_vy = p["body"].velocity
            turn = 0.25  # 0-1: how fast a player accelerates/turns toward its desired velocity
            p["body"].velocity = (
                cur_vx + (desired_vx - cur_vx) * turn,
                cur_vy + (desired_vy - cur_vy) * turn,
            )

        self.space.step(dt)
        self.time_elapsed += dt
        if self.celebration_team is None:
            self.match_clock += dt
        self._update_possession()
        self._check_goal()
        self._update_celebration()

    # -- ball possession: pickup, dribble, tackle, pass/shoot --------
    def _update_possession(self):
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
        attack_dir = 1 if p["team"] == "red" else -1

        # glue the ball to its carrier, slightly ahead in the attack direction
        self.ball_body.position = (px, py + attack_dir * DRIBBLE_LEAD)
        self.ball_body.velocity = p["body"].velocity

        # a defender close enough gets a 50/50 shot at winning the ball
        if self.time_elapsed >= self.next_tackle_time:
            for opp in self.players:
                if opp["team"] == p["team"]:
                    continue
                ox, oy = opp["body"].position
                if math.hypot(px - ox, py - oy) < TACKLE_RADIUS:
                    self.next_tackle_time = self.time_elapsed + TACKLE_COOLDOWN
                    if random.random() < 0.5:
                        # the ball is knocked loose, not cleanly won - it
                        # squirts away for a genuine 50/50 second ball
                        self.event_log.append((self.time_elapsed, f"TACKLE! {opp['id']} knocks it loose"))
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
        attack_dir = 1 if team == "red" else -1
        bx, by = self.ball_body.position

        if shoot:
            # aim at the goal but with a random angle error - can miss wide
            goal_x = COURT_X + COURT_W / 2
            goal_y = self.court_bounds[3] if attack_dir == 1 else self.court_bounds[1]
            angle = math.atan2(goal_y - by, goal_x - bx)
            angle += random.uniform(-SHOT_ANGLE_SPREAD, SHOT_ANGLE_SPREAD)
            target_x = bx + math.cos(angle) * 1000
            target_y = by + math.sin(angle) * 1000
            power = random.uniform(SHOT_POWER_MIN, SHOT_POWER_MAX)
            self.event_log.append((self.time_elapsed, f"{p['id']} shoots!"))

            keeper = next((q for q in self.players if q["team"] != team and q["role"] == "GK"), None)
            if keeper is not None and random.random() < KEEPER_SLIP_CHANCE:
                keeper["stunned_until"] = self.time_elapsed + KEEPER_SLIP_DURATION
                self.event_log.append((self.time_elapsed, f"{keeper['id']} slips!"))
        else:
            teammates = [q for q in self.players if q["team"] == team and q is not p]
            target = max(teammates, key=lambda q: attack_dir * q["body"].position[1])
            target_x, target_y = target["body"].position
            power = 380
            self.event_log.append((self.time_elapsed, f"{p['id']} passes"))

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
        self.event_log.append((self.time_elapsed, f"{player['id']} is stunned!"))

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

            # backs only join the celebration if they were already forward,
            # in the opponent's half, when the goal went in - forwards always join
            attack_dir = 1 if scored == "red" else -1
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
            conceding_team = "blue" if self.celebration_team == "red" else "red"
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
