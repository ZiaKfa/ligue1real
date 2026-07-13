"""Procedural sound effects, mixed into a WAV track and muxed into the
exported MP4 alongside the video.

Placeholder synthesis for now (sine tones / noise bursts) - swap `_CLIPS`
for real audio files later (e.g. load with `wave.open(path).readframes()`
into the same float-sample-list shape) without touching the mixing code.
"""

import array
import math
import random
import wave

SAMPLE_RATE = 44100


def _tone(freq, duration, volume=0.5, fade=0.01):
    n = int(SAMPLE_RATE * duration)
    fade_n = max(1, int(SAMPLE_RATE * fade))
    samples = []
    for i in range(n):
        amp = volume
        if i < fade_n:
            amp *= i / fade_n
        elif i > n - fade_n:
            amp *= (n - i) / fade_n
        samples.append(amp * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
    return samples


def _sweep(freq_start, freq_end, duration, volume=0.5):
    n = int(SAMPLE_RATE * duration)
    samples = []
    phase = 0.0
    for i in range(n):
        t = i / n
        freq = freq_start + (freq_end - freq_start) * t
        phase += 2 * math.pi * freq / SAMPLE_RATE
        samples.append(volume * (1 - t) * math.sin(phase))
    return samples


def _noise_burst(duration, volume=0.4):
    n = int(SAMPLE_RATE * duration)
    return [volume * (1 - i / n) * random.uniform(-1, 1) for i in range(n)]


def _chord(freqs, duration, volume=0.5):
    layers = [_tone(f, duration, volume / len(freqs)) for f in freqs]
    n = max(len(layer) for layer in layers)
    out = [0.0] * n
    for layer in layers:
        for i, s in enumerate(layer):
            out[i] += s
    return out


_CLIPS = {
    "whistle": _tone(2200, 0.35, volume=0.35),
    "goal": _chord([523.25, 659.25, 783.99], 0.6, volume=0.5),  # C-E-G, triumphant
    "shot": _sweep(900, 200, 0.15, volume=0.4),
    "tackle": _noise_burst(0.12, volume=0.35),
    "pass": _tone(1200, 0.05, volume=0.2),
}


def event_sound(text):
    """Map an event_log caption to a sound name in `_CLIPS`, or None to skip it."""
    if text.startswith("GOAL!"):
        return "goal"
    if text.startswith("TACKLE!"):
        return "tackle"
    if text.endswith("shoots!"):
        return "shot"
    if text.endswith("passes"):
        return "pass"
    return None


def build_audio_track(events, duration_seconds):
    """events: list of (time_seconds, sound_name). Returns float samples
    (mono, may exceed [-1, 1] where sounds overlap - clamped on write)."""
    n_total = int(duration_seconds * SAMPLE_RATE) + 1
    track = [0.0] * n_total
    for t, name in events:
        clip = _CLIPS.get(name)
        if clip is None:
            continue
        start = int(t * SAMPLE_RATE)
        for i, s in enumerate(clip):
            idx = start + i
            if idx >= n_total:
                break
            track[idx] += s
    return track


def write_wav(path, samples, sample_rate=SAMPLE_RATE):
    ints = array.array("h", (max(-32767, min(32767, int(s * 32767))) for s in samples))
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(ints.tobytes())
