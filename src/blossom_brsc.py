"""Biome Randomizer / Strange Controller item use (port of Noteab use_br_sc)."""

from __future__ import annotations

from typing import Callable

from macro_engine import _sleep_sec, github_original_click_at, inventory_click_delay_sec

CalibrationPoint = tuple[int, int] | None
GetPoint = Callable[[str], CalibrationPoint]
ConfigEnabled = Callable[[dict, str], bool]

BR_ITEM_NAME = "biome randomizer"
SC_ITEM_NAME = "strange controller"

# Calibrations needed for the inventory use flow.
_BRSC_CALIBRATION_SPECS: tuple[tuple[str, str | None], ...] = (
    ("inventory_menu", None),
    ("items_tab", "potion_items_tab"),
    ("search_bar", "potion_search_bar"),
    ("first_item_inventory_slot_pos", None),
    ("use_button", None),
)

BRSC_PRE_USE_SETTLE_SEC = 1.3


def biome_randomizer_enabled(config: dict, *, config_enabled: ConfigEnabled) -> bool:
    if config_enabled(config, "fishing_mode"):
        return False
    return config_enabled(config, "biome_randomizer")


def strange_controller_enabled(config: dict, *, config_enabled: ConfigEnabled) -> bool:
    if config_enabled(config, "fishing_mode"):
        return False
    return config_enabled(config, "strange_controller")


def _interval_seconds(config: dict, key: str, default_minutes: float) -> int:
    raw = config.get(key, default_minutes)
    try:
        minutes = float(raw)
    except (TypeError, ValueError):
        minutes = default_minutes
    return max(60, int(minutes * 60))


def br_interval_seconds(config: dict) -> int:
    return _interval_seconds(config, "br_duration", 30.0)


def sc_interval_seconds(config: dict) -> int:
    return _interval_seconds(config, "sc_duration", 15.0)


def _click_delay_sec(config: dict) -> float:
    return inventory_click_delay_sec(config, default_ms=650)


def _resolve_point(get_point: GetPoint, key: str, fallback: str | None = None) -> CalibrationPoint:
    point = get_point(key)
    if point is None and fallback:
        point = get_point(fallback)
    return point


def brsc_ready(get_point: GetPoint) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for key, fallback in _BRSC_CALIBRATION_SPECS:
        if _resolve_point(get_point, key, fallback) is None:
            missing.append(key if not fallback else f"{key}/{fallback}")
    return (not missing, missing)


def _autoit_send(token: str) -> bool:
    try:
        import autoit

        autoit.send(token)
        return True
    except Exception as error:
        print(f"[main macro] br/sc: autoit send {token!r} failed: {error}")
        return False


def _type_text(text: str) -> None:
    _autoit_send("^{a}")
    _autoit_send("{BACKSPACE}")
    _autoit_send(text)


def run_use_item(
    item_name: str,
    *,
    config: dict,
    get_point: GetPoint,
    focus_roblox: Callable[[], bool],
    cancel_event,
    reason: str,
) -> str:
    """Port of use_br_sc: open inventory, search item, set amount 1, use, close."""
    ready, missing = brsc_ready(get_point)
    if not ready:
        return f"Skipped: {item_name} not calibrated — " + ", ".join(missing)
    if cancel_event.is_set():
        return "Cancelled"

    print(f"[main macro] use item '{item_name}' ({reason})")
    if not focus_roblox():
        return "Error: Roblox not focused"

    click_delay = _click_delay_sec(config)
    if not _sleep_sec(BRSC_PRE_USE_SETTLE_SEC, cancel_event):
        return "Cancelled"

    steps: list[tuple[str, str | None, int, str]] = [
        ("inventory_menu", None, 1, "open inventory"),
        ("items_tab", "potion_items_tab", 1, "items tab"),
        ("search_bar", "potion_search_bar", 2, "search bar"),
    ]
    for key, fallback, clicks, label in steps:
        point = _resolve_point(get_point, key, fallback)
        if point is None:
            return f"Error: missing calibration {key}"
        if not github_original_click_at(*point, click=clicks, pre_sleep_sec=click_delay, cancel=cancel_event):
            return "Cancelled"
        print(f"[main macro] use item: {label} at {point}")
        if not _sleep_sec(0.2 + click_delay, cancel_event):
            return "Cancelled"

    _type_text(item_name)
    if not _sleep_sec(0.3 + click_delay, cancel_event):
        return "Cancelled"

    first_slot = _resolve_point(get_point, "first_item_inventory_slot_pos")
    if first_slot is None:
        return "Error: missing first_item_inventory_slot_pos calibration"
    if not github_original_click_at(*first_slot, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
        return "Cancelled"
    if not _sleep_sec(0.3 + click_delay, cancel_event):
        return "Cancelled"

    amount_box = _resolve_point(get_point, "amount_box")
    if amount_box is not None:
        if not github_original_click_at(*amount_box, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
            return "Cancelled"
        _sleep_sec(0.16 + click_delay, cancel_event)
        _autoit_send("^{a}")
        _sleep_sec(0.13 + click_delay, cancel_event)
        _autoit_send("{BACKSPACE}")
        _sleep_sec(0.13 + click_delay, cancel_event)
        _autoit_send("1")
        _sleep_sec(0.13 + click_delay, cancel_event)

    use_button = _resolve_point(get_point, "use_button")
    if use_button is None:
        return "Error: missing use_button calibration"
    if not github_original_click_at(*use_button, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
        return "Cancelled"
    if not _sleep_sec(0.22 + click_delay, cancel_event):
        return "Cancelled"

    close_button = _resolve_point(get_point, "inventory_close_button") or _resolve_point(get_point, "inventory_menu")
    if close_button is not None:
        github_original_click_at(*close_button, click=1, pre_sleep_sec=click_delay, cancel=cancel_event)
        _sleep_sec(0.22 + click_delay, cancel_event)

    return f"OK: used {item_name}"
