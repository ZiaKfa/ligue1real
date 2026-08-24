Drop player photos here to replace the flat kit-color dot with a face.

- Path referenced by each roster entry's `"face"` field (see `team_france.json` / `team_spain.json`).
- Any format `pygame.image.load` supports works: PNG (with or without transparency) or JPG.
- Square, front-facing crops work best - they get scaled and cropped to a circle automatically.
- Missing or unreadable files just fall back to the plain colored circle, so it's safe to leave slots empty.
