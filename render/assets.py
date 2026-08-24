"""Player face images - drawn on top of the team-color circle instead of a
flat color, so a roster entry can carry a real photo/portrait. Falls back
to the plain colored circle (see draw.py) whenever a player has no "face"
set or the file can't be loaded - so this is purely additive."""

import os

import pygame

_face_cache = {}

# our face sources are head-and-shoulders portraits (subject centered, head
# near the top) - crop down to just the head before the circle mask, or the
# face reads as a tiny smudge inside a jersey once shrunk to player-dot size
FACE_CROP_SIZE_FRACTION = 0.55   # crop box side, relative to the image's shorter dimension
FACE_CROP_TOP_FRACTION = 0.03    # crop box top, relative to that same dimension


def get_face_surface(path, diameter):
    """Returns a circular-cropped, diameter x diameter Surface for the image
    at `path`, or None if `path` is falsy or the image can't be loaded.
    Cached per (path, diameter) since this runs every frame for every player."""
    if not path:
        return None
    key = (path, diameter)
    if key in _face_cache:
        return _face_cache[key]

    surface = None
    if os.path.isfile(path):
        try:
            raw = pygame.image.load(path)
            # smoothscale requires a 24/32-bit surface - normalize first since
            # some sources (e.g. paletted PNGs) load as 8-bit
            full = pygame.Surface(raw.get_size(), pygame.SRCALPHA)
            full.blit(raw, (0, 0))

            w, h = full.get_size()
            side = int(min(w, h) * FACE_CROP_SIZE_FRACTION)
            top = int(min(w, h) * FACE_CROP_TOP_FRACTION)
            left = (w - side) // 2
            head = full.subsurface(pygame.Rect(left, top, side, side))

            img = pygame.transform.smoothscale(head, (diameter, diameter))

            surface = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
            surface.blit(img, (0, 0))
            mask = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
            pygame.draw.circle(mask, (255, 255, 255, 255), (diameter // 2, diameter // 2), diameter // 2)
            surface.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        except (pygame.error, ValueError) as e:
            print(f"warning: couldn't load face image '{path}': {e}")
            surface = None

    _face_cache[key] = surface
    return surface
