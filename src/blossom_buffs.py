"""Auto-pop glitched buffs (port of Noteab auto_pop_buffs).

Triggered when the biome watcher detects GLITCHED. For each enabled buff in
config["auto_buff_glitched"], open the inventory, search the buff name, set the
amount, and use it. Priority potions are popped first, then any remaining
enabled buffs; Heavenly/Oblivion add a per-potion settle wait (shortened when a
Warp Potion is also queued).
"""

from __future__ import annotations

from typing import Callable

from macro_engine import _sleep_sec, github_original_click_at, inventory_click_delay_sec

CalibrationPoint = tuple[int, int] | None
GetPoint = Callable[[str], CalibrationPoint]
ConfigEnabled = Callable[[dict, str], bool]

# Noteab priority order — these potions are popped before any other enabled buff.
BUFF_PRIORITY_ORDER: tuple[str, ...] = (
    "Xyz Potion",
    "Warp Potion",
    "Heavenly Potion II",
    "Oblivion Potion",
)
# Per-potion settle wait (seconds) for potions that apply a stack: 0.85s each.
BUFF_HEAVENLY_OBLIVION_WAIT_PER_POTION_SEC = 0.85
# Warp Potion speeds up game actions, so the settle wait is shortened.
BUFF_WARP_WAIT_MULTIPLIER = 0.12

_BUFF_CALIBRATION_SPECS: tuple[tuple[str, str | None], ...] = (
    ("inventory_menu", None),
    ("search_bar", "potion_search_bar"),
    ("first_item_inventory_slot_pos", None),
    ("use_button", None),
)


def _click_delay_sec(config: dict) -> float:
    return inventory_click_delay_sec(config, default_ms=650)


def _resolve_point(get_point: GetPoint, key: str, fallback: str | None = None) -> CalibrationPoint:
    point = get_point(key)
    if point is None and fallback:
        point = get_point(fallback)
    return point


def _enabled_buffs(config: dict) -> list[tuple[str, int]]:
    """Return [(buff_name, amount)] for enabled entries, priority potions first."""
    raw = config.get("auto_buff_glitched", {})
    enabled: dict[str, int] = {}
    if not isinstance(raw, dict):
        return []
    for buff, spec in raw.items():
        is_enabled = False
        amount = 1
        if isinstance(spec, (list, tuple)):
            if len(spec) >= 1:
                is_enabled = bool(spec[0])
            if len(spec) >= 2:
                try:
                    amount = int(spec[1])
                except (TypeError, ValueError):
                    amount = 1
        elif isinstance(spec, dict):
            is_enabled = bool(spec.get("enabled", False))
            try:
                amount = int(spec.get("amount", 1))
            except (TypeError, ValueError):
                amount = 1
        if is_enabled:
            enabled[str(buff)] = max(1, amount)
    ordered: list[tuple[str, int]] = []
    for buff in BUFF_PRIORITY_ORDER:
        if buff in enabled:
            ordered.append((buff, enabled.pop(buff)))
    for buff, amount in enabled.items():
        ordered.append((buff, amount))
    return ordered


def auto_buff_glitched_enabled(config: dict, *, config_enabled: ConfigEnabled) -> bool:
    return bool(_enabled_buffs(config))


def buffs_ready(get_point: GetPoint) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for key, fallback in _BUFF_CALIBRATION_SPECS:
        if _resolve_point(get_point, key, fallback) is None:
            missing.append(key if not fallback else f"{key}/{fallback}")
    return (not missing, missing)


def _autoit_send(token: str) -> bool:
    try:
        import autoit

        autoit.send(token)
        return True
    except Exception as error:
        print(f"[main macro] buffs: autoit send {token!r} failed: {error}")
        return False


def run_auto_pop_buffs(
    *,
    config: dict,
    get_point: GetPoint,
    focus_roblox: Callable[[], bool],
    cancel_event,
    reason: str,
) -> str:
    buffs = _enabled_buffs(config)
    if not buffs:
        return "Skipped: no enabled glitched buffs"
    ready, missing = buffs_ready(get_point)
    if not ready:
        return "Skipped: buffs not calibrated — " + ", ".join(missing)
    if cancel_event.is_set():
        return "Cancelled"

    print(f"[main macro] auto-pop buffs ({reason}): {[b for b, _ in buffs]}")
    if not focus_roblox():
        return "Error: Roblox not focused"

    click_delay = _click_delay_sec(config)
    inventory_menu = _resolve_point(get_point, "inventory_menu")
    search_bar = _resolve_point(get_point, "search_bar", "potion_search_bar")
    first_slot = _resolve_point(get_point, "first_item_inventory_slot_pos")
    amount_box = _resolve_point(get_point, "amount_box")
    use_button = _resolve_point(get_point, "use_button")

    used = 0
    warp_enabled = any(buff == "Warp Potion" for buff, _ in buffs)
    for buff, amount in buffs:
        if cancel_event.is_set():
            return "Cancelled"
        print(f"[main macro] using buff {buff} x{amount}")
        if not focus_roblox():
            return "Error: Roblox not focused"
        _sleep_sec(0.35, cancel_event)

        if not github_original_click_at(*inventory_menu, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
            return "Cancelled"
        _sleep_sec(0.22 + click_delay, cancel_event)

        if not github_original_click_at(*search_bar, click=2, pre_sleep_sec=click_delay, cancel=cancel_event):
            return "Cancelled"
        _sleep_sec(0.23 + click_delay, cancel_event)

        _autoit_send("^{a}")
        _autoit_send("{BACKSPACE}")
        _autoit_send(buff.lower())
        _sleep_sec(0.22 + click_delay, cancel_event)

        if not github_original_click_at(*first_slot, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
            return "Cancelled"
        _sleep_sec(0.22 + click_delay, cancel_event)

        if amount_box is not None:
            if not github_original_click_at(*amount_box, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
                return "Cancelled"
            _sleep_sec(0.22 + click_delay, cancel_event)
            _autoit_send("^{a}")
            _sleep_sec(0.285 + click_delay, cancel_event)
            _autoit_send("{BACKSPACE}")
            _sleep_sec(0.285 + click_delay, cancel_event)
            _autoit_send(str(amount))
            _sleep_sec(0.285 + click_delay, cancel_event)

        if not github_original_click_at(*use_button, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
            return "Cancelled"
        _sleep_sec(0.3 + click_delay, cancel_event)

        if not github_original_click_at(*inventory_menu, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
            return "Cancelled"
        _sleep_sec(0.32 + click_delay, cancel_event)

        # Per-potion settle wait (Noteab additional_wait_time): Heavenly/Oblivion
        # apply a stack, so wait ~0.85s per potion — shortened when a Warp Potion
        # is also queued (warp speeds up game actions).
        if buff in ("Heavenly Potion II", "Oblivion Potion"):
            wait_sec = BUFF_HEAVENLY_OBLIVION_WAIT_PER_POTION_SEC * amount
            if warp_enabled:
                wait_sec *= BUFF_WARP_WAIT_MULTIPLIER
            if not _sleep_sec(wait_sec, cancel_event):
                return "Cancelled"
        used += 1

    return f"OK: popped {used} buff type(s)"
