"""Merchant teleporter + OCR-based auto-buy (adapted from Noteab Merchant_Handler).

Flow:
  use_merchant_teleporter -> inventory, items tab, search "teleport", first slot,
    amount=1, use, close inventory, then Merchant_Handler, then close inventory.
  Merchant_Handler -> 190s cooldown; interact (E×6) -> dialogue (8 clicks) ->
    OCR Mari/Jester/Rin -> Discord found alert -> open shop -> optional auto-buy ->
    optional shop screenshot webhook.

Blossom adapts the original to its Windows input layer (github_original_click_at,
AutoIt) while keeping the public function signatures used by run_local_ui.py.
"""

from __future__ import annotations

import time
from threading import Thread
from typing import Callable

import blossom_ocr
from macro_engine import (
    _sleep_sec,
    github_original_click_at,
    inventory_click_delay_sec,
    replay_key_action,
)
from macro_hotkeys import is_unbound_hotkey, normalize_hotkey

from blossom_brsc import run_use_item

try:
    from discord_webhooks import (
        normalize_webhook_urls,
        send_merchant_found_webhook,
        send_merchant_webhook,
    )
except Exception:  # pragma: no cover - webhook is optional
    normalize_webhook_urls = None  # type: ignore[assignment,misc]
    send_merchant_found_webhook = None  # type: ignore[assignment,misc]
    send_merchant_webhook = None  # type: ignore[assignment,misc]

CalibrationPoint = tuple[int, int] | None
CalibrationRegion = tuple[int, int, int, int] | None
GetPoint = Callable[[str], CalibrationPoint]
GetRegion = Callable[[str], CalibrationRegion]
ConfigEnabled = Callable[[dict, str], bool]

# Original Merchant_Handler constants.
MERCHANT_COOLDOWN_SEC = 190.0
MERCHANT_SLOT_X_OFFSET = 193
MERCHANT_SLOT_COUNT = 5
MERCHANT_INTERACT_PRESSES = 6
MERCHANT_INTERACT_PRESS_GAP = 0.38
MERCHANT_POST_INTERACT_SETTLE_SEC = 0.5
MERCHANT_DIALOGUE_CLICKS = 8
MERCHANT_DIALOGUE_CLICK_GAP = 0.35
MERCHANT_NAME_OCR_TRIES = 4
MERCHANT_NAME_OCR_GAP = 0.08
MERCHANT_OPEN_WAIT_SEC = 5.0
MERCHANT_PURCHASE_BUTTON_CLICKS = 3
MERCHANT_FOUND_WEBHOOK_THROTTLE_SEC = 45.0
MERCHANT_SLOT_CLICK_COUNT = 2
MERCHANT_SLOT_SETTLE_SEC = 0.12
MERCHANT_PURCHASE_TYPE_GAP_SEC = 0.18
MERCHANT_PURCHASE_SETTLE_SEC = 2.0
MERCHANT_POST_TELEPORT_SETTLE_SEC = 1.1
PORTABLE_CRACK_SEARCH = "crack"

# Per-slot calibration keys (preferred over the +178 offset when all set).
_MERCHANT_SLOT_KEYS = tuple(f"merchant_slot_{i}_pos" for i in range(1, MERCHANT_SLOT_COUNT + 1))

_MARI_NAME_VARIANTS = ("Mari", "Mori", "Marl", "Mar1", "MarI", "Mar!", "Maori")
_JESTER_NAME_VARIANTS = (
    "Jester",
    "Dester",
    "Jostor",
    "Jestor",
    "Joster",
    "Destor",
    "Doster",
    "Dostor",
    "jester",
    "dester",
)
_RIN_NAME_VARIANTS = ("Rin", "R1n", "R1N", "RIN", "RiN")

# Teleporter inventory-flow calibrations (get_point keys).
_MERCHANT_TP_CALIBRATION_SPECS: tuple[tuple[str, str | None], ...] = (
    ("inventory_menu", None),
    ("items_tab", "potion_items_tab"),
    ("search_bar", "potion_search_bar"),
    ("first_item_inventory_slot_pos", None),
    ("use_button", None),
    ("inventory_close_button", None),
)

_MERCHANT_SHOP_CALIBRATION_SPECS: tuple[tuple[str, str | None], ...] = (
    ("merchant_dialogue_box", None),
    ("merchant_open_button", None),
    ("first_item_merchant_slot_pos", "merchant_slot_1_pos"),
    ("purchase_amount_button", None),
    ("purchase_button", None),
)

# Merchants that never use a Max button.
_MERCHANT_NO_MAX = frozenset({"Rin"})

# Single shared Max-amount button used by every non-Rin merchant.
# `merchant_set_max_button` is the canonical key; the rest are read only as
# backward-compatibility fallbacks (including the old per-merchant keys, so any
# existing Mari/Jester Max calibration keeps working after the unify).
_MERCHANT_MAX_BUTTON_KEYS = (
    "merchant_set_max_button",
    "merchant_max_button",
    "purchase_max_button",
    "mari_set_max_button",
    "jester_set_max_button",
    "mari_max_button",
    "jester_max_button",
)

# OCR regions (get_region keys, 4-tuples).
_MERCHANT_OCR_REGION_KEYS = (
    "merchant_name_ocr_pos",
    "item_name_ocr_pos",
)

_MERCHANT_INTERACT_KEY_KEYS = (
    "merchant_interact_key",
    "interact_key",
    "e_keybind",
    "merchant_key",
)

# Module-level cooldown timestamp (mirrors self.last_merchant_interaction).
_last_merchant_interaction = 0.0
_last_found_webhook_at: dict[str, float] = {}


# --------------------------------------------------------------------------- #
# Enable / interval helpers (Blossom public API)
# --------------------------------------------------------------------------- #
def merchant_teleporter_enabled(config: dict, *, config_enabled: ConfigEnabled) -> bool:
    if config_enabled(config, "fishing_mode"):
        return False
    return config_enabled(config, "merchant_teleporter") or config_enabled(
        config, "auto_merchant_teleporter"
    )


def merchant_in_limbo_enabled(config: dict, *, config_enabled: ConfigEnabled) -> bool:
    if config_enabled(config, "fishing_mode"):
        return False
    return config_enabled(config, "auto_merchant_in_limbo")


def mt_interval_seconds(config: dict) -> int:
    raw = config.get("mt_duration", 1)
    try:
        minutes = float(raw)
    except (TypeError, ValueError):
        minutes = 1.0
    # Never schedule merchant faster than its own internal cooldown — otherwise it
    # is perpetually "due" and (since the loop runs one UI task per tick by
    # priority) it starves daily quests, potions, obby, BR/SC while just no-opping
    # on cooldown.
    return max(60, int(MERCHANT_COOLDOWN_SEC), int(minutes * 60))


def merchant_cooldown_remaining() -> float:
    """Seconds left on the shared 190s merchant cooldown (0 when actionable)."""
    return max(0.0, MERCHANT_COOLDOWN_SEC - (time.time() - _last_merchant_interaction))


def _click_delay_sec(config: dict) -> float:
    return inventory_click_delay_sec(config, default_ms=350)


def _resolve_point(get_point: GetPoint, key: str, fallback: str | None = None) -> CalibrationPoint:
    point = get_point(key)
    if point is None and fallback:
        point = get_point(fallback)
    return point


def _missing_calibration_labels(
    specs: tuple[tuple[str, str | None], ...], get_point: GetPoint
) -> list[str]:
    missing: list[str] = []
    for key, fallback in specs:
        if _resolve_point(get_point, key, fallback) is None:
            missing.append(key if not fallback else f"{key}/{fallback}")
    return missing


def merchant_teleporter_ready(config: dict, get_point: GetPoint) -> tuple[bool, list[str]]:
    missing = _missing_calibration_labels(_MERCHANT_TP_CALIBRATION_SPECS, get_point)
    missing.extend(_missing_calibration_labels(_MERCHANT_SHOP_CALIBRATION_SPECS, get_point))
    return (not missing, missing)


def _merchant_interact_key(config: dict) -> str:
    for key in _MERCHANT_INTERACT_KEY_KEYS:
        raw = config.get(key)
        if is_unbound_hotkey(raw):
            continue
        cleaned = str(raw or "").strip()
        if not cleaned:
            continue
        try:
            return normalize_hotkey(cleaned)
        except ValueError:
            continue
    return "e"


# --------------------------------------------------------------------------- #
# Low-level input helpers
# --------------------------------------------------------------------------- #
def _autoit_send(token: str) -> bool:
    try:
        import autoit

        autoit.send(token)
        return True
    except Exception as error:
        print(f"[main macro] merchant: autoit send {token!r} failed: {error}")
        return False


def _press_interact_once(config: dict, cancel_event) -> bool:
    """Press the interact key once (AutoIt for simple keys, SendInput fallback)."""
    key = _merchant_interact_key(config)
    if cancel_event.is_set():
        return False
    if "+" not in key and len(key) <= 16:
        token = key if len(key) == 1 else f"{{{key}}}"
        if _autoit_send(token):
            return True
    if not replay_key_action(key, True):
        return False
    _sleep_sec(0.06, cancel_event)
    replay_key_action(key, False)
    return True


def _type_text(text: str) -> None:
    """Clear the focused field and type `text` (mirrors pyautogui.write semantics)."""
    _autoit_send("^{a}")
    _autoit_send("{BACKSPACE}")
    _autoit_send(text)


def _set_amount_one(get_point: GetPoint, cancel_event, click_delay: float) -> None:
    amount_box = get_point("amount_box")
    if amount_box is None:
        return
    if not github_original_click_at(*amount_box, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
        return
    _sleep_sec(0.15 + click_delay, cancel_event)
    _autoit_send("^{a}")
    _sleep_sec(0.13, cancel_event)
    _autoit_send("{BACKSPACE}")
    _sleep_sec(0.13, cancel_event)
    _autoit_send("1")
    _sleep_sec(0.13 + click_delay, cancel_event)


# --------------------------------------------------------------------------- #
# Auto-buy item list adapter
# --------------------------------------------------------------------------- #
def _normalize_item_list(raw) -> dict[str, tuple[bool, int, bool]]:
    """Return {lower_name: (enabled, quantity, rebuy)} from either UI or original format."""
    items: dict[str, tuple[bool, int, bool]] = {}
    if isinstance(raw, dict):
        for name, spec in raw.items():
            try:
                enabled, quantity, rebuy = spec
            except (TypeError, ValueError):
                continue
            items[str(name).strip().lower()] = (bool(enabled), int(quantity), bool(rebuy))
    elif isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip().lower()
            if not name:
                continue
            enabled = bool(entry.get("enabled", False))
            try:
                quantity = int(entry.get("amount", 1))
            except (TypeError, ValueError):
                quantity = 1
            rebuy = not bool(entry.get("stopAfterBuy", False))
            items[name] = (enabled, quantity, rebuy)
    return items


def _merchant_auto_buy_items(config: dict, merchant_name: str) -> dict[str, tuple[bool, int, bool]]:
    """Auto-buy list for the detected merchant (Mari_Items / Jester_Items / Rin_Items)."""
    return _normalize_item_list(config.get(f"{merchant_name}_Items"))


# --------------------------------------------------------------------------- #
# Merchant_Handler port
# --------------------------------------------------------------------------- #
def _match_merchant_name(ocr_text: str) -> str:
    """Detect Mari / Jester / Rin from OCR (fuzzy + substring fallback like Noteab)."""
    text = (ocr_text or "").strip()
    if not text:
        return ""
    try:
        if blossom_ocr.fuzzy_match_any(text, _MARI_NAME_VARIANTS, threshold=0.75):
            return "Mari"
        if blossom_ocr.fuzzy_match_any(text, _JESTER_NAME_VARIANTS, threshold=0.75):
            return "Jester"
        if blossom_ocr.fuzzy_match_any(text, _RIN_NAME_VARIANTS, threshold=0.75):
            return "Rin"
    except Exception:
        pass
    lower = text.lower()
    if any(name.lower() in lower for name in _MARI_NAME_VARIANTS):
        return "Mari"
    if any(name.lower() in lower for name in _JESTER_NAME_VARIANTS):
        return "Jester"
    if any(name.lower() in lower for name in _RIN_NAME_VARIANTS):
        return "Rin"
    return ""


def _ocr_merchant_name(
    region: CalibrationRegion,
    cancel_event,
) -> str:
    """OCR the merchant-name region; early exit on first Mari/Jester/Rin match."""
    for attempt in range(MERCHANT_NAME_OCR_TRIES):
        if cancel_event.is_set():
            return ""
        text = blossom_ocr.ocr_region(region)
        merchant_name = _match_merchant_name(text)
        if merchant_name:
            print(f"[main macro] merchant: {merchant_name} name found via OCR (try {attempt + 1})")
            return merchant_name
        is_last = attempt >= MERCHANT_NAME_OCR_TRIES - 1
        if is_last:
            print(f"[main macro] merchant: name OCR exhausted after {MERCHANT_NAME_OCR_TRIES} tries (last={text!r})")
        elif text:
            print(f"[main macro] merchant: name OCR try {attempt + 1} got {text!r}")
        if not is_last and not _sleep_sec(MERCHANT_NAME_OCR_GAP, cancel_event):
            return ""
    return ""


def _resolve_merchant_slot_points(get_point: GetPoint) -> list[tuple[int, int]]:
    """Prefer the 5 explicit per-slot calibrations; fall back to the +193 offset."""
    explicit = [get_point(key) for key in _MERCHANT_SLOT_KEYS]
    if all(p is not None for p in explicit):
        return explicit  # type: ignore[return-value]
    points = [p for p in explicit if p is not None]
    if len(points) == MERCHANT_SLOT_COUNT:
        return points
    first = _resolve_point(get_point, "first_item_merchant_slot_pos", "merchant_slot_1_pos")
    if first is not None:
        x, y = first
        return [(x + i * MERCHANT_SLOT_X_OFFSET, y) for i in range(MERCHANT_SLOT_COUNT)]
    return points


def _merchant_slot_position(
    get_point: GetPoint,
    slot_index: int,
    slot_points: list[tuple[int, int]],
) -> tuple[int, int] | None:
    """Click position for slot_index (0-based), including merchant_extra_slot offsets."""
    if slot_index < len(slot_points):
        return slot_points[slot_index]
    if len(slot_points) >= MERCHANT_SLOT_COUNT:
        base_x, base_y = slot_points[MERCHANT_SLOT_COUNT - 1]
        extra = slot_index - (MERCHANT_SLOT_COUNT - 1)
        return (base_x + extra * MERCHANT_SLOT_X_OFFSET, base_y)
    if slot_points:
        base_x, base_y = slot_points[0]
        return (base_x + slot_index * MERCHANT_SLOT_X_OFFSET, base_y)
    first = _resolve_point(get_point, "first_item_merchant_slot_pos", "merchant_slot_1_pos")
    if first is None:
        return None
    x, y = first
    return (x + slot_index * MERCHANT_SLOT_X_OFFSET, y)


def _resolve_merchant_max_button(get_point: GetPoint, merchant_name: str = "") -> CalibrationPoint:
    """Max-amount button for this merchant, or None when it should be skipped.

    Rin never uses a Max button. Every other merchant shares the single
    `merchant_set_max_button` calibration; the remaining keys (including the old
    per-merchant Mari/Jester keys) are read only as backward-compat fallbacks.
    """
    if merchant_name in _MERCHANT_NO_MAX:
        return None
    for key in _MERCHANT_MAX_BUTTON_KEYS:
        point = get_point(key)
        if point is not None:
            return point
    return None


def _click_through_dialogue(get_point: GetPoint, cancel_event, click_delay: float) -> bool:
    dialogue = get_point("merchant_dialogue_box")
    if dialogue is None:
        print("[main macro] merchant: missing merchant_dialogue_box calibration")
        return False
    for _ in range(MERCHANT_DIALOGUE_CLICKS):
        if cancel_event.is_set():
            return False
        if not github_original_click_at(
            *dialogue,
            click=2,
            pre_sleep_sec=click_delay,
            cancel=cancel_event,
        ):
            return False
        if not _sleep_sec(MERCHANT_DIALOGUE_CLICK_GAP, cancel_event):
            return False
    return True


def _buy_item(
    *,
    get_point: GetPoint,
    cancel_event,
    quantity: int,
    click_delay: float,
    merchant_name: str = "",
) -> bool:
    """Buy flow: when a Max button is calibrated, press Max → Purchase (no amount
    typing). Otherwise fall back to the amount field + typed quantity → Purchase."""
    purchase_amount = get_point("purchase_amount_button")
    purchase = get_point("purchase_button")
    if purchase is None:
        print("[main macro] merchant: missing purchase_button — cannot buy")
        return False

    set_max = _resolve_merchant_max_button(get_point, merchant_name)
    if set_max is not None:
        # User-requested flow: instead of pressing the amount field and typing a
        # number, just press the calibrated Max button, then Purchase.
        if not github_original_click_at(*set_max, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
            return False
        if not _sleep_sec(MERCHANT_PURCHASE_TYPE_GAP_SEC + click_delay, cancel_event):
            return False
    elif purchase_amount is not None:
        if not github_original_click_at(*purchase_amount, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
            return False
        _type_text(str(quantity))
        if not _sleep_sec(MERCHANT_PURCHASE_TYPE_GAP_SEC, cancel_event):
            return False

    if not github_original_click_at(
        *purchase,
        click=MERCHANT_PURCHASE_BUTTON_CLICKS,
        pre_sleep_sec=click_delay,
        cancel=cancel_event,
    ):
        return False
    return _sleep_sec(MERCHANT_PURCHASE_SETTLE_SEC, cancel_event)


def _capture_merchant_screenshot() -> str | None:
    """Save a full-screen shot of the open shop for the webhook. None on failure."""
    try:
        import os

        import pyautogui

        screenshot_dir = os.path.join(os.getcwd(), "images")
        os.makedirs(screenshot_dir, exist_ok=True)
        path = os.path.join(screenshot_dir, "merchant_screenshot.png")
        pyautogui.screenshot().save(path)
        return path
    except Exception as error:
        print(f"[main macro] merchant screenshot failed: {error}")
        return None


def _webhook_urls(config: dict) -> list[str]:
    if normalize_webhook_urls is None:
        return []
    return normalize_webhook_urls(config.get("webhook_url") or config.get("webhooks"))


def _merchant_ping_id(config: dict, merchant_name: str) -> str | None:
    """Per-merchant Discord ping when the matching ping_* toggle and user id are set."""
    spec = {
        "Mari": ("ping_mari", "mari_user_id"),
        "Jester": ("ping_jester", "jester_user_id"),
        "Rin": ("ping_rin", "rin_user_id"),
    }.get(merchant_name)
    if not spec:
        return None
    toggle_key, id_key = spec
    if not config.get(toggle_key):
        return None
    ping_id = str(config.get(id_key, "") or "").strip()
    return ping_id or None


def _merchant_shop_webhook_enabled(config: dict) -> bool:
    flag = config.get("merchant_shop_webhook")
    return True if flag is None else bool(flag)


def _should_send_found_webhook(merchant_name: str) -> bool:
    now = time.time()
    last = _last_found_webhook_at.get(merchant_name, 0.0)
    if now - last < MERCHANT_FOUND_WEBHOOK_THROTTLE_SEC:
        remaining = MERCHANT_FOUND_WEBHOOK_THROTTLE_SEC - (now - last)
        print(
            f"[main macro] merchant: skipping duplicate found webhook for {merchant_name} "
            f"({remaining:.0f}s throttle)"
        )
        return False
    _last_found_webhook_at[merchant_name] = now
    return True


def _run_webhook_async(name: str, target) -> None:
    Thread(target=target, name=name, daemon=True).start()


def _send_merchant_found_webhook(config: dict, merchant_name: str) -> None:
    if send_merchant_found_webhook is None:
        return
    urls = _webhook_urls(config)
    if not urls:
        return
    if not _should_send_found_webhook(merchant_name):
        return
    ps_link = str(config.get("private_server_link", "") or "").strip() or None
    ping_id = _merchant_ping_id(config, merchant_name)

    def _send() -> None:
        try:
            sent = send_merchant_found_webhook(
                urls,
                merchant_name=merchant_name,
                ps_link=ps_link,
                ping_id=ping_id,
            )
            if sent:
                print(f"[main macro] merchant: found webhook sent for {merchant_name} ({sent} url(s))")
        except Exception as error:
            print(f"[main macro] merchant found webhook failed: {error}")

    _run_webhook_async("BlossomMerchantFoundWebhook", _send)


def _send_merchant_shop_webhook(
    config: dict,
    merchant_name: str,
    screenshot_path: str | None,
    *,
    purchased: list[str] | None = None,
) -> None:
    if send_merchant_webhook is None or not _merchant_shop_webhook_enabled(config):
        return
    urls = _webhook_urls(config)
    if not urls:
        return
    ps_link = str(config.get("private_server_link", "") or "").strip() or None
    ping_id = _merchant_ping_id(config, merchant_name)

    def _send() -> None:
        try:
            sent = send_merchant_webhook(
                urls,
                merchant_name=merchant_name,
                screenshot_path=screenshot_path,
                ps_link=ps_link,
                ping_id=ping_id,
                purchased=purchased,
            )
            if sent:
                print(f"[main macro] merchant: shop webhook sent for {merchant_name} ({sent} url(s))")
        except Exception as error:
            print(f"[main macro] merchant shop webhook failed: {error}")

    _run_webhook_async("BlossomMerchantShopWebhook", _send)


def _phase_press_interact(config: dict, cancel_event) -> bool:
    interact_key = _merchant_interact_key(config)
    print(
        f"[main macro] merchant: pressing {interact_key!r} "
        f"{MERCHANT_INTERACT_PRESSES}x (original macro)"
    )
    for _ in range(MERCHANT_INTERACT_PRESSES):
        if cancel_event.is_set():
            return False
        _press_interact_once(config, cancel_event)
        if not _sleep_sec(MERCHANT_INTERACT_PRESS_GAP, cancel_event):
            return False
    return _sleep_sec(MERCHANT_POST_INTERACT_SETTLE_SEC, cancel_event)


def _phase_detect_merchant(
    get_region: GetRegion | None,
    cancel_event,
) -> tuple[str, CalibrationRegion | None]:
    name_region = get_region("merchant_name_ocr_pos") if get_region else None
    if name_region is None:
        return "", None
    return _ocr_merchant_name(name_region, cancel_event), name_region


def _phase_open_shop(
    *,
    get_point: GetPoint,
    cancel_event,
    click_delay: float,
    merchant_name: str,
) -> bool:
    open_button = get_point("merchant_open_button")
    if open_button is None:
        return False
    print(f"[main macro] merchant: opening shop for {merchant_name}")
    if not github_original_click_at(
        *open_button,
        click=3,
        pre_sleep_sec=click_delay,
        cancel=cancel_event,
    ):
        return False
    return _sleep_sec(MERCHANT_OPEN_WAIT_SEC + click_delay, cancel_event)


def _phase_auto_buy(
    *,
    config: dict,
    get_point: GetPoint,
    get_region: GetRegion | None,
    cancel_event,
    click_delay: float,
    merchant_name: str,
) -> tuple[dict[str, int], str | None]:
    auto_buy_items = _merchant_auto_buy_items(config, merchant_name)
    if not any(enabled for enabled, _, _ in auto_buy_items.values()):
        return {}, None

    slot_points = _resolve_merchant_slot_points(get_point)
    if not slot_points:
        return {}, (
            "Error: calibrate merchant slots 1–5 (or first_item_merchant_slot_pos) for auto-buy"
        )
    item_region = get_region("item_name_ocr_pos") if get_region else None
    if item_region is None:
        return {}, "Error: calibrate item_name_ocr_pos for merchant auto-buy"

    try:
        extra_slots = int(config.get("merchant_extra_slot", 0) or 0)
    except (TypeError, ValueError):
        extra_slots = 0
    total_slots = MERCHANT_SLOT_COUNT + max(0, extra_slots)

    purchased: dict[str, int] = {}
    for slot_index in range(total_slots):
        if cancel_event.is_set():
            return purchased, "Cancelled"
        slot_pos = _merchant_slot_position(get_point, slot_index, slot_points)
        if slot_pos is None:
            continue
        slot_x, slot_y = slot_pos
        if not github_original_click_at(
            slot_x,
            slot_y,
            click=MERCHANT_SLOT_CLICK_COUNT,
            pre_sleep_sec=click_delay,
            cancel=cancel_event,
        ):
            return purchased, "Cancelled"
        if not _sleep_sec(MERCHANT_SLOT_SETTLE_SEC, cancel_event):
            return purchased, "Cancelled"

        raw_text = blossom_ocr.ocr_region(item_region)
        item_name = blossom_ocr.correct_item_text(raw_text)
        print(f"[main macro] merchant slot {slot_index + 1}: {raw_text!r} -> {item_name!r}")

        spec = auto_buy_items.get(item_name)
        if not spec:
            continue
        enabled, quantity, rebuy = spec
        if not enabled:
            continue
        count = purchased.get(item_name, 0)
        if not rebuy and count > 0:
            continue
        print(f"[main macro] merchant: buying {item_name} x{quantity} (rebuy={rebuy})")
        if _buy_item(
            get_point=get_point,
            cancel_event=cancel_event,
            quantity=quantity,
            click_delay=click_delay,
            merchant_name=merchant_name,
        ):
            purchased[item_name] = count + 1
    return purchased, None


def _run_merchant_handler(
    *,
    config: dict,
    get_point: GetPoint,
    get_region: GetRegion | None,
    cancel_event,
    reason: str,
    respect_cooldown: bool = True,
) -> str:
    global _last_merchant_interaction

    now = time.time()
    if respect_cooldown and now - _last_merchant_interaction < MERCHANT_COOLDOWN_SEC:
        remaining = MERCHANT_COOLDOWN_SEC - (now - _last_merchant_interaction)
        return f"Skipped: merchant cooldown ({remaining:.0f}s left)"

    click_delay = _click_delay_sec(config)
    print(f"[main macro] merchant handler ({reason})")

    # Phase 1 — interact (E×6 + settle)
    if not _phase_press_interact(config, cancel_event):
        return "Cancelled"

    # Phase 2 — dialogue clicks
    if not _click_through_dialogue(get_point, cancel_event, click_delay):
        return "Error: calibrate merchant_dialogue_box for merchant detection"

    # Phase 3 — name OCR (early exit on match)
    merchant_name, name_region = _phase_detect_merchant(get_region, cancel_event)
    if not merchant_name:
        _last_merchant_interaction = time.time()
        _abort_merchant_no_shop(get_point, cancel_event, click_delay)
        if name_region is None:
            print("[main macro] merchant: cannot confirm shop — calibrate 'Merchant Name' region")
            return "Skipped: calibrate the Merchant Name region to enable detection"
        print("[main macro] merchant: no shop detected (name OCR empty)")
        return "Skipped: no merchant shop detected"

    _send_merchant_found_webhook(config, merchant_name)

    # Phase 4 — open shop
    if get_point("merchant_open_button") is None:
        return "Error: missing calibration merchant_open_button"
    if not _phase_open_shop(
        get_point=get_point,
        cancel_event=cancel_event,
        click_delay=click_delay,
        merchant_name=merchant_name,
    ):
        return "Cancelled"

    screenshot_path = _capture_merchant_screenshot()

    # Phase 5 — auto-buy (optional)
    purchased, buy_error = _phase_auto_buy(
        config=config,
        get_point=get_point,
        get_region=get_region,
        cancel_event=cancel_event,
        click_delay=click_delay,
        merchant_name=merchant_name,
    )
    if buy_error:
        if buy_error.startswith("Error"):
            return buy_error
        return buy_error

    purchased_labels = [f"{name} x{cnt}" for name, cnt in purchased.items()]
    _send_merchant_shop_webhook(
        config,
        merchant_name,
        screenshot_path,
        purchased=purchased_labels or None,
    )

    _last_merchant_interaction = time.time()
    _close_merchant(get_point, cancel_event, click_delay, clicks=3)
    if not purchased:
        return f"OK: {merchant_name} shop opened, no enabled auto-buy items"
    return f"OK: {merchant_name} auto-buy complete ({sum(purchased.values())} purchases)"


def _abort_merchant_no_shop(get_point: GetPoint, cancel_event, click_delay: float) -> None:
    """Original recovery when OCR finds no merchant: close, then click open again."""
    close_btn = get_point("merchant_close_button")
    open_btn = get_point("merchant_open_button")
    if close_btn is not None and not cancel_event.is_set():
        github_original_click_at(*close_btn, click=3, pre_sleep_sec=click_delay, cancel=cancel_event)
    if open_btn is not None and not cancel_event.is_set():
        github_original_click_at(*open_btn, click=3, pre_sleep_sec=click_delay, cancel=cancel_event)


def _close_merchant(
    get_point: GetPoint,
    cancel_event,
    click_delay: float,
    *,
    clicks: int = 1,
) -> None:
    close_btn = get_point("merchant_close_button")
    if close_btn is None or cancel_event.is_set():
        return
    github_original_click_at(
        *close_btn,
        click=clicks,
        pre_sleep_sec=click_delay,
        cancel=cancel_event,
    )
    print(f"[main macro] merchant: closed shop (X) at {close_btn}")


def merchant_return_to_limbo_enabled(config: dict) -> bool:
    """After merchant teleporter + shop, use Portable Crack from inventory to return to Limbo."""
    raw = config.get("merchant_return_to_limbo")
    if raw is None:
        return True
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return bool(raw)


def return_to_limbo_via_portable_crack(
    *,
    config: dict,
    get_point: GetPoint,
    focus_roblox: Callable[[], bool],
    cancel_event,
    reason: str,
) -> str:
    """Inventory flow: search crack → use Portable Crack → return to Limbo."""
    print(f"[main macro] portable crack return to limbo ({reason})")
    return run_use_item(
        PORTABLE_CRACK_SEARCH,
        config=config,
        get_point=get_point,
        focus_roblox=focus_roblox,
        cancel_event=cancel_event,
        reason=reason,
    )


# --------------------------------------------------------------------------- #
# Public entry points (Blossom API)
# --------------------------------------------------------------------------- #
def run_merchant_teleporter(
    *,
    config: dict,
    get_point: GetPoint,
    focus_roblox: Callable[[], bool],
    cancel_event,
    reason: str,
    get_region: GetRegion | None = None,
) -> str:
    ready, missing = merchant_teleporter_ready(config, get_point)
    if not ready:
        return "Skipped: merchant teleporter not calibrated — " + ", ".join(missing)
    if cancel_event.is_set():
        return "Cancelled"

    # Respect the 190s cooldown before doing the (slow) inventory teleport.
    now = time.time()
    if now - _last_merchant_interaction < MERCHANT_COOLDOWN_SEC:
        remaining = MERCHANT_COOLDOWN_SEC - (now - _last_merchant_interaction)
        return f"Skipped: merchant cooldown ({remaining:.0f}s left)"

    print(f"[main macro] merchant teleporter ({reason}): inventory use flow")
    if not focus_roblox():
        return "Error: Roblox not focused"

    click_delay = _click_delay_sec(config)
    if not _sleep_sec(MERCHANT_POST_TELEPORT_SETTLE_SEC, cancel_event):
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
        print(f"[main macro] merchant teleporter: {label} at {point}")
        if not _sleep_sec(click_delay, cancel_event):
            return "Cancelled"

    _type_text("teleport")
    print("[main macro] merchant teleporter: searched 'teleport'")
    if not _sleep_sec(0.3 + click_delay, cancel_event):
        return "Cancelled"

    first_slot = _resolve_point(get_point, "first_item_inventory_slot_pos")
    if first_slot is not None:
        if not github_original_click_at(*first_slot, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
            return "Cancelled"
        print(f"[main macro] merchant teleporter: select search result at {first_slot}")
        if not _sleep_sec(0.25 + click_delay, cancel_event):
            return "Cancelled"

    _set_amount_one(get_point, cancel_event, click_delay)

    use_button = _resolve_point(get_point, "use_button")
    if use_button is None:
        return "Error: missing calibration use_button"
    if not github_original_click_at(*use_button, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
        return "Cancelled"
    print("[main macro] merchant teleporter: used Merchant Teleporter")
    if not _sleep_sec(0.23 + click_delay, cancel_event):
        return "Cancelled"

    close_button = _resolve_point(get_point, "inventory_close_button")
    if close_button is not None:
        github_original_click_at(*close_button, click=1, pre_sleep_sec=click_delay, cancel=cancel_event)

    print(f"[main macro] merchant teleporter: waiting {MERCHANT_POST_TELEPORT_SETTLE_SEC:.1f}s after teleport")
    if not _sleep_sec(MERCHANT_POST_TELEPORT_SETTLE_SEC, cancel_event):
        return "Cancelled"

    handler_result = _run_merchant_handler(
        config=config,
        get_point=get_point,
        get_region=get_region,
        cancel_event=cancel_event,
        reason=f"after teleporter ({reason})",
        respect_cooldown=False,
    )

    # Close inventory after handling (original closes twice).
    if close_button is not None:
        _sleep_sec(0.33 + click_delay, cancel_event)
        github_original_click_at(*close_button, click=1, pre_sleep_sec=click_delay, cancel=cancel_event)
        _sleep_sec(0.33 + click_delay, cancel_event)
        github_original_click_at(*close_button, click=1, pre_sleep_sec=click_delay, cancel=cancel_event)

    if handler_result.startswith("Error") or handler_result == "Cancelled":
        return handler_result

    if merchant_return_to_limbo_enabled(config):
        if not _sleep_sec(0.6 + click_delay, cancel_event):
            return "Cancelled"
        crack_result = return_to_limbo_via_portable_crack(
            config=config,
            get_point=get_point,
            focus_roblox=focus_roblox,
            cancel_event=cancel_event,
            reason=f"after teleporter ({reason})",
        )
        if crack_result.startswith("Error") or crack_result == "Cancelled":
            return (
                f"OK: merchant teleporter — {handler_result}; "
                f"limbo return failed: {crack_result}"
            )
        print(f"[main macro] merchant teleporter: {crack_result}")
        if not _sleep_sec(MERCHANT_POST_TELEPORT_SETTLE_SEC, cancel_event):
            return "Cancelled"
        return f"OK: merchant teleporter — {handler_result}; {crack_result}"

    return f"OK: merchant teleporter — {handler_result}"


def run_merchant_limbo_interact(
    *,
    config: dict,
    get_point: GetPoint,
    focus_roblox: Callable[[], bool],
    cancel_event,
    reason: str,
    get_region: GetRegion | None = None,
) -> str:
    if cancel_event.is_set():
        return "Cancelled"

    print(f"[main macro] merchant limbo ({reason})")
    if not focus_roblox():
        return "Error: Roblox not focused"

    return _run_merchant_handler(
        config=config,
        get_point=get_point,
        get_region=get_region,
        cancel_event=cancel_event,
        reason=f"limbo ({reason})",
        respect_cooldown=True,
    )
