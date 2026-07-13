"""Simulate + render a match to a scaled-down preview window, piping
frames into ffmpeg to produce a finished MP4 (export currently disabled -
see the commented-out block below)."""

import os
import subprocess
import time

import pygame

from sim.config import (
    VIDEO_W, VIDEO_H, FPS, MATCH_SECONDS, STEPS_PER_FRAME, OUTPUT_DIR,
    FINAL_SCORE_HOLD_SECONDS,
)
from .draw import draw_frame, draw_final_score


def run_preview(match):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"match_{int(time.time())}.mp4")

    pygame.init()
    surface = pygame.Surface((VIDEO_W, VIDEO_H))
    font_big = pygame.font.SysFont("arial", 64, bold=True)
    font_med = pygame.font.SysFont("arial", 36)

    # Preview window, scaled down since VIDEO_H (1920) is taller than most screens.
    preview_scale = 0.42
    screen = pygame.display.set_mode((int(VIDEO_W * preview_scale), int(VIDEO_H * preview_scale)))
    pygame.display.set_caption("Futsal Sim - Preview")
    clock = pygame.time.Clock()

    # ffmpeg export disabled temporarily for preview.
    # ffmpeg_cmd = [
    #     "ffmpeg", "-y",
    #     "-f", "rawvideo", "-vcodec", "rawvideo",
    #     "-pix_fmt", "rgb24",
    #     "-s", f"{VIDEO_W}x{VIDEO_H}",
    #     "-r", str(FPS),
    #     "-i", "-",
    #     "-an",
    #     "-vcodec", "libx264",
    #     "-pix_fmt", "yuv420p",
    #     "-preset", "fast",
    #     "-crf", "20",
    #     out_path,
    # ]
    # proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

    dt = 1.0 / FPS

    frame_i = 0
    while match.match_clock < MATCH_SECONDS:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return

        for _ in range(STEPS_PER_FRAME):
            match.step(dt / STEPS_PER_FRAME)

        draw_frame(surface, match, font_big, font_med)

        # show preview window
        preview = pygame.transform.smoothscale(surface, screen.get_size())
        screen.blit(preview, (0, 0))
        pygame.display.flip()
        clock.tick(FPS)

        # pygame surface -> raw RGB bytes -> ffmpeg stdin
        # frame_bytes = pygame.image.tobytes(surface, "RGB")
        # proc.stdin.write(frame_bytes)

        if frame_i % (FPS * 5) == 0:
            print(f"  ...{match.match_clock:0.0f}s simulated "
                  f"(score {match.score['red']}-{match.score['blue']})")
        frame_i += 1

    # proc.stdin.close()
    # proc.wait()
    # print(f"\nDone. Video saved to: {out_path}")

    # hold a full-time score screen for a few seconds before closing
    draw_final_score(surface, match, font_big, font_med)
    preview = pygame.transform.smoothscale(surface, screen.get_size())
    screen.blit(preview, (0, 0))
    pygame.display.flip()

    for _ in range(int(FINAL_SCORE_HOLD_SECONDS * FPS)):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
        clock.tick(FPS)

    pygame.quit()
    print(f"\nFull time: RED {match.score['red']} - {match.score['blue']} BLUE")
