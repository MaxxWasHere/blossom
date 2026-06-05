"""Global potion crafting rules used across the Blossom macro."""

from __future__ import annotations

from button_region_check import parse_calibration_region, region_mostly_green

# Buttons that must be checked for the active (green) state before clicking.
GREEN_GUARD_CALIBRATION_KEYS: frozenset[str] = frozenset(
    {
        "potion_recipe_auto_button",
    }
)


def submit_potion_search_text(potion_name: str) -> None:
    """Type a potion name in the focused search field and confirm with Enter."""
    import autoit

    autoit.send("^{a}")
    autoit.send("{BACKSPACE}")
    autoit.send(potion_name)
    autoit.send("{ENTER}")


def calibration_region_is_green(config: dict, key: str) -> tuple[bool, dict]:
    """Return whether a calibrated region is mostly green (already active)."""
    value = config.get(key)
    region = parse_calibration_region(value)
    if region is None:
        return False, {"error": "no_region", "key": key, "region": None}
    return region_mostly_green(region)


def should_skip_click_for_green_guard(key: str) -> bool:
    return key in GREEN_GUARD_CALIBRATION_KEYS


def green_guard_allows_click(config: dict, key: str) -> tuple[bool, dict]:
    """If key is green-guarded and already green, return (False, stats) to skip click."""
    if not should_skip_click_for_green_guard(key):
        return True, {"guarded": False, "key": key}
    is_green, stats = calibration_region_is_green(config, key)
    stats = {**stats, "guarded": True, "key": key, "is_green": is_green}
    return (not is_green), stats
