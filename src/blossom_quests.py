"""Daily quest claiming for the main macro loop."""

from __future__ import annotations

from typing import Callable

from macro_engine import _sleep_sec, github_original_click_at, UI_CLICK_SPEED_MULTIPLIER

CalibrationPoint = tuple[int, int] | None
GetPoint = Callable[[str], CalibrationPoint]
ConfigEnabled = Callable[[dict, str], bool]

QUEST_CLICK_DELAY = 0.16 * UI_CLICK_SPEED_MULTIPLIER
QUEST_MENU_SETTLE_SEC = 0.45 * UI_CLICK_SPEED_MULTIPLIER
QUEST_SLOT_KEYS = ("quest1_button", "quest2_button", "quest3_button")
CLAIM_PASSES = 2

_QUEST_CALIBRATION_SPECS: tuple[tuple[str, str | None], ...] = (
    ("quest_menu", None),
    ("claim_quest_button", None),
    ("quest1_button", None),
)


def daily_quests_enabled(config: dict, *, config_enabled: ConfigEnabled) -> bool:
    if config_enabled(config, "fishing_mode"):
        return False
    return config_enabled(config, "auto_claim_daily_quests")


def quest_interval_seconds(config: dict) -> int:
    raw = config.get("auto_claim_interval", 30)
    try:
        minutes = float(raw)
    except (TypeError, ValueError):
        minutes = 30.0
    return max(60, int(minutes * 60))


def _resolve_point(get_point: GetPoint, key: str, fallback: str | None = None) -> CalibrationPoint:
    point = get_point(key)
    if point is None and fallback:
        point = get_point(fallback)
    return point


def daily_quests_ready(get_point: GetPoint) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for key, fallback in _QUEST_CALIBRATION_SPECS:
        if _resolve_point(get_point, key, fallback) is None:
            missing.append(key if not fallback else f"{key}/{fallback}")
    return (not missing, missing)


def run_daily_quest_claim(
    *,
    get_point: GetPoint,
    focus_roblox: Callable[[], bool],
    cancel_event,
    reason: str,
) -> str:
    ready, missing = daily_quests_ready(get_point)
    if not ready:
        return "Skipped: daily quests not calibrated — " + ", ".join(missing)

    if cancel_event.is_set():
        return "Cancelled"

    print(f"[main macro] daily quests ({reason})")
    if not focus_roblox():
        return "Error: Roblox not focused"

    menu = _resolve_point(get_point, "quest_menu")
    claim_btn = _resolve_point(get_point, "claim_quest_button")
    if menu is None or claim_btn is None:
        return "Error: missing quest_menu or claim_quest_button"

    if not github_original_click_at(
        *menu, click=1, pre_sleep_sec=QUEST_CLICK_DELAY, cancel=cancel_event
    ):
        return "Cancelled"
    print(f"[main macro] quests: opened daily quests menu at {menu}")
    if not _sleep_sec(QUEST_MENU_SETTLE_SEC, cancel_event):
        return "Cancelled"

    claimed_slots = 0
    for slot_key in QUEST_SLOT_KEYS:
        slot = _resolve_point(get_point, slot_key)
        if slot is None:
            continue
        if cancel_event.is_set():
            return "Cancelled"
        if not github_original_click_at(
            *slot, click=1, pre_sleep_sec=QUEST_CLICK_DELAY, cancel=cancel_event
        ):
            return "Cancelled"
        print(f"[main macro] quests: selected {slot_key} at {slot}")
        if not _sleep_sec(QUEST_CLICK_DELAY, cancel_event):
            return "Cancelled"

        for pass_idx in range(1, CLAIM_PASSES + 1):
            if cancel_event.is_set():
                return "Cancelled"
            if not github_original_click_at(
                *claim_btn,
                click=1,
                pre_sleep_sec=QUEST_CLICK_DELAY,
                cancel=cancel_event,
            ):
                return "Cancelled"
            print(
                f"[main macro] quests: claim ({pass_idx}/{CLAIM_PASSES}) "
                f"for {slot_key} at {claim_btn}"
            )
            if not _sleep_sec(QUEST_CLICK_DELAY, cancel_event):
                return "Cancelled"
        claimed_slots += 1

    if claimed_slots == 0:
        return "Error: no quest slot calibrations (quest1/2/3_button)"

    if cancel_event.is_set():
        return "Cancelled"
    if not github_original_click_at(
        *menu, click=1, pre_sleep_sec=QUEST_CLICK_DELAY, cancel=cancel_event
    ):
        return "Cancelled"
    print(f"[main macro] quests: closed daily quests menu")

    return f"OK: claimed daily quests ({claimed_slots} slots)"
