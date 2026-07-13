"""Simulate + render a match to a scaled-down preview window, piping
frames into ffmpeg to produce a finished MP4."""

import os
import subprocess
import time

import pygame

from sim.config import (
    VIDEO_W, VIDEO_H, FPS, MATCH_SECONDS, STEPS_PER_FRAME, OUTPUT_DIR,
    FINAL_SCORE_HOLD_SECONDS,
)
from .draw import draw_frame, draw_final_score


def run_preview(match, show_preview=True):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = int(time.time())
    # include the pid - parallel batch runs can start within the same
    # wall-clock second, and a bare timestamp would collide between workers
    run_id = f"{timestamp}_{os.getpid()}"
    # final filename needs the score, which isn't known until the match ends -
    # record to a temp name and rename once full time is reached
    tmp_path = os.path.join(OUTPUT_DIR, f"_recording_{run_id}.mp4")

    pygame.init()
    surface = pygame.Surface((VIDEO_W, VIDEO_H))
    font_big = pygame.font.SysFont("arial", 64, bold=True)
    font_med = pygame.font.SysFont("arial", 36)

    screen = None
    clock = pygame.time.Clock()
    if show_preview:
        # Preview window, scaled down since VIDEO_H (1920) is taller than most screens.
        preview_scale = 0.42
        screen = pygame.display.set_mode((int(VIDEO_W * preview_scale), int(VIDEO_H * preview_scale)))
        pygame.display.set_caption("Futsal Sim - Preview")

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
        tmp_path,
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

    def write_frame():
        proc.stdin.write(pygame.image.tobytes(surface, "RGB"))

    def show_and_pace():
        if screen is not None:
            preview = pygame.transform.smoothscale(surface, screen.get_size())
            screen.blit(preview, (0, 0))
            pygame.display.flip()
            clock.tick(FPS)  # only throttle to real time when there's a human watching

    def quit_requested():
        if screen is None:
            return False
        return any(event.type == pygame.QUIT for event in pygame.event.get())

    def abort_recording():
        pygame.quit()
        proc.stdin.close()
        proc.wait()
        os.remove(tmp_path)  # incomplete match - not worth keeping

    dt = 1.0 / FPS

    frame_i = 0
    while match.match_clock < MATCH_SECONDS:
        if quit_requested():
            abort_recording()
            return

        for _ in range(STEPS_PER_FRAME):
            match.step(dt / STEPS_PER_FRAME)

        draw_frame(surface, match, font_big, font_med)
        show_and_pace()
        write_frame()

        if frame_i % (FPS * 5) == 0:
            print(f"  ...{match.match_clock:0.0f}s simulated "
                  f"(score {match.score['red']}-{match.score['blue']})")
        frame_i += 1

    # hold a full-time score screen for a few seconds before closing - and
    # keep it in the recorded video too, it's a nice beat to end a clip on
    draw_final_score(surface, match, font_big, font_med)
    show_and_pace()
    for _ in range(int(FINAL_SCORE_HOLD_SECONDS * FPS)):
        if quit_requested():
            abort_recording()
            return
        show_and_pace()
        write_frame()

    pygame.quit()
    proc.stdin.close()
    proc.wait()

    red, blue = match.score["red"], match.score["blue"]
    print(f"\nFull time: {match.team_labels['red']} {red} - {blue} {match.team_labels['blue']}")

    if red + blue == 0:
        # a scoreless match isn't worth posting - discard the recording
        os.remove(tmp_path)
        print("No goals scored - discarding recording.")
        return None

    # goal count leads the filename (zero-padded) so sorting by name in a
    # file browser surfaces the highest-scoring, most postable matches first
    out_path = os.path.join(OUTPUT_DIR, f"goals{red + blue:02d}_{red}-{blue}_{run_id}.mp4")
    os.replace(tmp_path, out_path)
    print(f"Saved: {out_path}")
    return out_path
