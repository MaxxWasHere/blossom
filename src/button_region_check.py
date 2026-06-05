"""Sample a calibrated screen region to see if it is mostly green (recipe Auto on)."""

from __future__ import annotations

from typing import Iterable


def parse_calibration_region(value) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        left = int(round(float(value[0])))
        top = int(round(float(value[1])))
        if len(value) >= 4:
            width = int(round(float(value[2])))
            height = int(round(float(value[3])))
        else:
            width = 0
            height = 0

        if width <= 2 or height <= 2:
            center_x = left + max(width, 1) // 2
            center_y = top + max(height, 1) // 2
            width = 120
            height = 48
            left = center_x - width // 2
            top = center_y - height // 2

        width = max(8, width)
        height = max(8, height)
        return left, top, width, height
    except (TypeError, ValueError):
        return None


def _pixel_class(r: int, g: int, b: int) -> str:
    """Classify a pixel as green fill, other state, or ignorable chrome/text."""
    peak = max(r, g, b)
    floor = min(r, g, b)
    if peak >= 200 and floor >= 150:
        return "ignore"
    if peak <= 14:
        return "ignore"
    if g >= 50 and g >= r + 18 and g >= b + 18:
        return "green"
    return "other"


def _iter_sample_pixels(
    width: int,
    height: int,
    *,
    text_margin_x: float = 0.22,
    text_margin_y: float = 0.18,
) -> Iterable[tuple[int, int]]:
    x0 = int(width * text_margin_x)
    x1 = int(width * (1.0 - text_margin_x))
    y0 = int(height * text_margin_y)
    y1 = int(height * (1.0 - text_margin_y))
    step_x = max(1, width // 24)
    step_y = max(1, height // 12)
    for y in range(0, height, step_y):
        for x in range(0, width, step_x):
            if x0 <= x <= x1 and y0 <= y <= y1:
                continue
            yield x, y


def region_mostly_green(
    region: tuple[int, int, int, int],
    *,
    green_threshold: float = 0.52,
) -> tuple[bool, dict]:
    """Return (is_mostly_green, debug_stats) for the calibrated bbox."""

    left, top, width, height = region
    stats: dict = {
        "region": [left, top, width, height],
        "sampled": 0,
        "green": 0,
        "green_ratio": 0.0,
        "green_threshold": green_threshold,
        "error": None,
    }

    try:
        from PIL import ImageGrab
    except ImportError as error:
        stats["error"] = f"Pillow missing: {error}"
        return False, stats

    try:
        shot = ImageGrab.grab(bbox=(left, top, left + width, top + height))
    except Exception as error:
        stats["error"] = str(error)
        return False, stats

    pixels = shot.load()
    green = 0
    other = 0
    ignored = 0
    for x, y in _iter_sample_pixels(width, height):
        r, g, b = pixels[x, y][:3]
        kind = _pixel_class(r, g, b)
        if kind == "green":
            green += 1
        elif kind == "other":
            other += 1
        else:
            ignored += 1

    compared = green + other
    ratio = (green / compared) if compared else 0.0
    stats["sampled"] = compared
    stats["green"] = green
    stats["other"] = other
    stats["ignored"] = ignored
    stats["green_ratio"] = round(ratio, 4)
    return ratio >= green_threshold, stats


def region_has_ui_content(
    region: tuple[int, int, int, int],
    *,
    bright_threshold: int = 55,
    content_threshold: float = 0.12,
) -> tuple[bool, dict]:
    """Return whether a screen region has enough non-dark pixels (UI likely visible)."""

    left, top, width, height = region
    stats: dict = {
        "region": [left, top, width, height],
        "sampled": 0,
        "bright": 0,
        "bright_ratio": 0.0,
        "content_threshold": content_threshold,
        "error": None,
    }

    try:
        from PIL import ImageGrab
    except ImportError as error:
        stats["error"] = f"Pillow missing: {error}"
        return False, stats

    try:
        shot = ImageGrab.grab(bbox=(left, top, left + width, top + height))
    except Exception as error:
        stats["error"] = str(error)
        return False, stats

    pixels = shot.load()
    bright = 0
    sampled = 0
    step_x = max(1, width // 16)
    step_y = max(1, height // 8)
    for y in range(0, height, step_y):
        for x in range(0, width, step_x):
            r, g, b = pixels[x, y][:3]
            sampled += 1
            if max(r, g, b) >= bright_threshold:
                bright += 1

    ratio = (bright / sampled) if sampled else 0.0
    stats["sampled"] = sampled
    stats["bright"] = bright
    stats["bright_ratio"] = round(ratio, 4)
    return ratio >= content_threshold, stats
