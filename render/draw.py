"""Top-down rendering of a single frame."""

import pygame

from sim.config import (
    VIDEO_W, VIDEO_H, COURT_X, COURT_Y, COURT_W, COURT_H, COURT_COLOR,
    LINE_COLOR, GOAL_WIDTH, GOAL_POST_RADIUS, PLAYER_RADIUS,
    BALL_COLOR, BALL_RADIUS, BG_COLOR, PENALTY_BOX_WIDTH, PENALTY_BOX_DEPTH,
)
from sim.match import FutsalMatch
from .assets import get_face_surface


def _fit_width(text_surface, max_w):
    """Shrinks a rendered text surface down to max_w (preserving aspect
    ratio) if it's wider than that - long club names ("MANCHESTER UNITED")
    or a goal caption naming a player otherwise render wide enough to get
    clipped by the frame's edges instead of just looking a little smaller."""
    if text_surface.get_width() <= max_w:
        return text_surface
    scale = max_w / text_surface.get_width()
    return pygame.transform.smoothscale(text_surface, (max_w, int(text_surface.get_height() * scale)))


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

    # goals
    mid_x = COURT_X + COURT_W / 2
    pygame.draw.line(surface, (255, 220, 80),
                      (mid_x - GOAL_WIDTH / 2, COURT_Y), (mid_x + GOAL_WIDTH / 2, COURT_Y), 6)
    pygame.draw.line(surface, (255, 220, 80),
                      (mid_x - GOAL_WIDTH / 2, COURT_Y + COURT_H), (mid_x + GOAL_WIDTH / 2, COURT_Y + COURT_H), 6)

    # penalty boxes
    box_left = mid_x - PENALTY_BOX_WIDTH / 2
    pygame.draw.rect(
        surface, LINE_COLOR,
        pygame.Rect(box_left, COURT_Y, PENALTY_BOX_WIDTH, PENALTY_BOX_DEPTH), 3,
    )
    pygame.draw.rect(
        surface, LINE_COLOR,
        pygame.Rect(box_left, COURT_Y + COURT_H - PENALTY_BOX_DEPTH, PENALTY_BOX_WIDTH, PENALTY_BOX_DEPTH), 3,
    )

    # goal posts - real physical obstacles (see FutsalMatch._build_walls),
    # drawn so it's clear why a wide-angle shot just clanged off one
    for post_x, post_y in match.goal_posts:
        pygame.draw.circle(surface, (245, 245, 245), (int(post_x), int(post_y)), GOAL_POST_RADIUS)
        pygame.draw.circle(surface, (0, 0, 0), (int(post_x), int(post_y)), GOAL_POST_RADIUS, 2)

    # players
    for p in match.players:
        color = match.team_colors[p["team"]]
        x, y = p["body"].position

        # facing pointer - a small triangle poking out of the circle's edge,
        # drawn first so the circle (below) trims its base to a neat cap
        fx, fy = p["facing"]
        perp_x, perp_y = -fy, fx
        tip = (x + fx * (PLAYER_RADIUS + 8), y + fy * (PLAYER_RADIUS + 8))
        base_x, base_y = x + fx * (PLAYER_RADIUS - 8), y + fy * (PLAYER_RADIUS - 8)
        left = (base_x + perp_x * 13, base_y + perp_y * 13)
        right = (base_x - perp_x * 13, base_y - perp_y * 13)
        pygame.draw.polygon(surface, color, [tip, left, right])
        pygame.draw.polygon(surface, (0, 0, 0), [tip, left, right], 2)

        # a roster "face" image is drawn over a team-color backing circle -
        # the color shows through any transparent pixels in the png (e.g. a
        # cutout photo) and still rings the edge so sides stay tellable apart
        face = get_face_surface(p.get("face"), PLAYER_RADIUS * 2)
        if face is not None:
            pygame.draw.circle(surface, color, (int(x), int(y)), PLAYER_RADIUS)
            surface.blit(face, face.get_rect(center=(int(x), int(y))))
            pygame.draw.circle(surface, color, (int(x), int(y)), PLAYER_RADIUS, 4)
        else:
            pygame.draw.circle(surface, color, (int(x), int(y)), PLAYER_RADIUS)
        pygame.draw.circle(surface, (0, 0, 0), (int(x), int(y)), PLAYER_RADIUS, 2)

    # ball
    bx, by = match.ball_body.position
    pygame.draw.circle(surface, BALL_COLOR, (int(bx), int(by)), BALL_RADIUS)
    pygame.draw.circle(surface, (0, 0, 0), (int(bx), int(by)), BALL_RADIUS, 2)

    # scoreboard
    max_text_w = VIDEO_W - 40  # frame margin - long club names shouldn't get clipped at the edges
    score_text = font_big.render(
        f"{match.team_labels[match.team_names[0]].upper()} {match.score[match.team_names[0]]}  -  "
        f"{match.score[match.team_names[1]]} {match.team_labels[match.team_names[1]].upper()}", True, LINE_COLOR
    )
    score_text = _fit_width(score_text, max_text_w)
    surface.blit(score_text, score_text.get_rect(center=(VIDEO_W // 2, 140)))

    timer_text = font_med.render(f"{match.match_clock:0.1f}s", True, (180, 180, 180))
    surface.blit(timer_text, timer_text.get_rect(center=(VIDEO_W // 2, 210)))

    # most recent goal caption, shown for 2s after it happens
    if match.event_log:
        t, text, team = match.event_log[-1]
        if match.time_elapsed - t < 2.0:
            cap_color = match.team_colors[team] if team is not None else (255, 220, 80)
            cap = font_big.render(text, True, cap_color)
            cap = _fit_width(cap, max_text_w)
            surface.blit(cap, cap.get_rect(center=(VIDEO_W // 2, VIDEO_H - 90)))


def _draw_score_panel(surface, match: FutsalMatch, font_big, font_med, title):
    """Shared broadcast-style panel (dimmed background + solid box) used for
    both the half-time and full-time breaks - only the title differs."""
    draw_frame(surface, match, font_big, font_med)

    overlay = pygame.Surface((VIDEO_W, VIDEO_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 120))
    surface.blit(overlay, (0, 0))

    title_text = font_big.render(title, True, (255, 220, 80))
    score_text = font_big.render(
        f"{match.team_labels[match.team_names[0]].upper()} {match.score[match.team_names[0]]}  -  "
        f"{match.score[match.team_names[1]]} {match.team_labels[match.team_names[1]].upper()}", True, LINE_COLOR
    )

    # top scorers: players with a goal or assist, ranked goals then assists
    scorers = sorted(
        (p for p in match.players if p["goals"] or p["assists"]),
        key=lambda p: (-p["goals"], -p["assists"]),
    )[:3]
    scorer_texts = []
    for p in scorers:
        line = f"{match._name(p)} - {p['goals']} gol"
        if p["assists"]:
            line += f", {p['assists']} assist"
        scorer_texts.append(font_med.render(line, True, match.team_colors[p["team"]]))

    # a lopsided, many-goal scoreline renders much wider text (double-digit
    # scores, longer team names) - shrink any line that would push the panel
    # past the frame's edges instead of letting it get clipped there
    max_line_w = VIDEO_W - 40 - 100  # frame margin, then the panel's own horizontal padding
    lines = [_fit_width(s, max_line_w) for s in [title_text, score_text] + scorer_texts]

    panel_w = max(s.get_width() for s in lines) + 100
    panel_h = sum(s.get_height() for s in lines) + 20 * len(lines) + 20
    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    pygame.draw.rect(panel, (18, 18, 22, 235), panel.get_rect(), border_radius=20)
    pygame.draw.rect(panel, (255, 220, 80), panel.get_rect(), width=3, border_radius=20)
    surface.blit(panel, panel.get_rect(center=(VIDEO_W // 2, VIDEO_H // 2)))

    y = VIDEO_H // 2 - panel_h // 2 + 10
    for s in lines:
        y += s.get_height() // 2 + 10
        surface.blit(s, s.get_rect(center=(VIDEO_W // 2, y)))
        y += s.get_height() // 2


def draw_half_time(surface, match: FutsalMatch, font_big, font_med):
    """Half-time break screen - same broadcast-panel look as full time, just
    shown mid-match before teams swap ends for the second half."""
    _draw_score_panel(surface, match, font_big, font_med, "HALF TIME")


def draw_final_score(surface, match: FutsalMatch, font_big, font_med):
    """Full-time screen: the last frame of play, dimmed, with a solid panel
    showing the final score - like a broadcast graphic, not text floating
    directly over the players."""
    _draw_score_panel(surface, match, font_big, font_med, "FULL TIME")
