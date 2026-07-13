"""Top-down rendering of a single frame."""

import pygame

from sim.config import (
    VIDEO_W, VIDEO_H, COURT_X, COURT_Y, COURT_W, COURT_H, COURT_COLOR,
    LINE_COLOR, GOAL_WIDTH, TEAM_RED, TEAM_BLUE, PLAYER_RADIUS, BALL_COLOR,
    BALL_RADIUS, BG_COLOR,
)
from sim.match import FutsalMatch


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

    timer_text = font_med.render(f"{match.match_clock:0.1f}s", True, (180, 180, 180))
    surface.blit(timer_text, timer_text.get_rect(center=(VIDEO_W // 2, 210)))

    # most recent goal caption, shown for 2s after it happens
    if match.event_log:
        t, text = match.event_log[-1]
        if match.time_elapsed - t < 2.0:
            cap = font_big.render(text, True, (255, 220, 80))
            surface.blit(cap, cap.get_rect(center=(VIDEO_W // 2, VIDEO_H - 90)))
