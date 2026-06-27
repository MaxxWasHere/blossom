"""Biome Selector: inventory use + in-game drive list (OCR + layout math)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from macro_engine import _sleep_sec, github_original_click_at, inventory_click_delay_sec

import blossom_ocr
from blossom_runtime_deps import winocr_status

CalibrationPoint = tuple[int, int] | None
GetRegion = Callable[[str], tuple[int, int, int, int] | None]
GetPoint = Callable[[str], CalibrationPoint]
ConfigEnabled = Callable[[dict, str], bool]

BIOME_SELECTOR_SEARCH_TEXT = "biome selector"
UI_SETTLE_SEC = 1.8
CONFIRM_SETTLE_SEC = 0.55
ROW_OCR_PSM = 7

DEFAULT_DRIVES: tuple[str, ...] = (
    "Radiant Star Drive",
    "Infernal Flame Drive",
    "Unknown Void Drive",
    "Corrupt Ruin Drive",
    "Golden Dune Drive",
    "Chilling Frost Drive",
    "Abyss Curse Drive",
    "Raging Gale Drive",
)

_INVENTORY_POINT_SPECS: tuple[tuple[str, str | None], ...] = (
    ("inventory_menu", None),
    ("search_bar", "potion_search_bar"),
    ("first_item_inventory_slot_pos", None),
    ("use_button", None),
)

_UI_POINT_SPECS: tuple[tuple[str, str | None], ...] = (
    ("biome_selector_first_drive_pos", None),
    ("biome_selector_confirm_pos", None),
)

_UI_REGION_KEYS: tuple[str, ...] = ("biome_selector_frame_pos",)

PRE_USE_SETTLE_SEC = 1.3


@dataclass(frozen=True)
class DriveLayout:
    button_width: int
    button_height: int
    button_count: int
    button_spacing: int

    def row_center(self, first_center: tuple[int, int], index: int) -> tuple[int, int]:
        x, y0 = first_center
        step = self.button_height + self.button_spacing
        return (x, int(y0 + index * step))

    def row_ocr_region(self, first_center: tuple[int, int], index: int) -> tuple[int, int, int, int]:
        cx, cy = self.row_center(first_center, index)
        w = max(40, self.button_width)
        h = max(16, self.button_height)
        return (int(cx - w // 2), int(cy - h // 2), w, h)


def biome_selector_enabled(config: dict, *, config_enabled: ConfigEnabled) -> bool:
    if config_enabled(config, "fishing_mode"):
        return False
    return config_enabled(config, "biome_selector")


def biome_selector_interval_seconds(config: dict) -> int:
    raw = config.get("biome_selector_duration", 30.0)
    try:
        minutes = float(raw)
    except (TypeError, ValueError):
        minutes = 30.0
    return max(60, int(minutes * 60))


def default_drive_toggles() -> dict[str, bool]:
    return {name: False for name in DEFAULT_DRIVES}


def normalize_drive_toggles(raw) -> dict[str, bool]:
    out = default_drive_toggles()
    if not isinstance(raw, dict):
        return out
    for name in DEFAULT_DRIVES:
        value = raw.get(name)
        if isinstance(value, str):
            out[name] = value.strip().lower() in ("1", "true", "yes", "on")
        else:
            out[name] = bool(value)
    for key, value in raw.items():
        if key not in out:
            if isinstance(value, str):
                out[str(key)] = value.strip().lower() in ("1", "true", "yes", "on")
            else:
                out[str(key)] = bool(value)
    return out


def read_drive_layout(config: dict) -> DriveLayout:
    def _int(key: str, default: int, minimum: int = 1) -> int:
        try:
            return max(minimum, int(float(config.get(key, default))))
        except (TypeError, ValueError):
            return default

    return DriveLayout(
        button_width=_int("biome_selector_button_width", 280, 20),
        button_height=_int("biome_selector_button_height", 32, 12),
        button_count=_int("biome_selector_button_count", len(DEFAULT_DRIVES), 1),
        button_spacing=_int("biome_selector_button_spacing", 2, 0),
    )


def apply_calibration_side_effects(config: dict, key: str, value: list[int]) -> dict:
    """Return config patches after a drag calibration (button size from first drive mark)."""
    patch: dict = {}
    if key == "biome_selector_first_drive_pos" and len(value) >= 4:
        patch["biome_selector_button_width"] = max(20, int(round(value[2])))
        patch["biome_selector_button_height"] = max(12, int(round(value[3])))
    return patch


def layout_slot_preview(config: dict, get_point: GetPoint) -> list[dict]:
    layout = read_drive_layout(config)
    first = _resolve_point(get_point, "biome_selector_first_drive_pos")
    if first is None:
        return []
    rows: list[dict] = []
    for index in range(layout.button_count):
        cx, cy = layout.row_center(first, index)
        rows.append({"index": index, "x": cx, "y": cy})
    return rows


def _click_delay_sec(config: dict) -> float:
    return inventory_click_delay_sec(config, default_ms=650)


def _resolve_point(get_point: GetPoint, key: str, fallback: str | None = None) -> CalibrationPoint:
    point = get_point(key)
    if point is None and fallback:
        point = get_point(fallback)
    return point


def _resolve_region(
    get_region: GetRegion, key: str, fallback: str | None = None
) -> tuple[int, int, int, int] | None:
    region = get_region(key)
    if region is None and fallback:
        region = get_region(fallback)
    return region


def _inventory_ready(get_point: GetPoint) -> list[str]:
    missing: list[str] = []
    for key, fallback in _INVENTORY_POINT_SPECS:
        if _resolve_point(get_point, key, fallback) is None:
            missing.append(key if not fallback else f"{key}/{fallback}")
    return missing


def _ui_ready(get_point: GetPoint, get_region: GetRegion, config: dict) -> list[str]:
    missing: list[str] = []
    for key, fallback in _UI_POINT_SPECS:
        if _resolve_point(get_point, key, fallback) is None:
            missing.append(key if not fallback else f"{key}/{fallback}")
    for key in _UI_REGION_KEYS:
        if _resolve_region(get_region, key) is None:
            missing.append(key)
    layout = read_drive_layout(config)
    if layout.button_count < 1:
        missing.append("biome_selector_button_count")
    return missing


def biome_selector_ready(
    get_point: GetPoint,
    *,
    get_region: GetRegion | None = None,
    config: dict | None = None,
) -> tuple[bool, list[str]]:
    missing = _inventory_ready(get_point)
    if get_region is not None and config is not None:
        missing.extend(_ui_ready(get_point, get_region, config))
    runtime = winocr_status()
    if runtime.get("state") != "installed" and not blossom_ocr.ocr_available():
        missing.append("winocr")
    return (not missing, missing)


def calibration_status(
    get_point: GetPoint,
    get_region: GetRegion,
    config: dict,
) -> dict:
    inv_missing = _inventory_ready(get_point)
    ui_missing = _ui_ready(get_point, get_region, config)
    layout = read_drive_layout(config)
    frame = _resolve_region(get_region, "biome_selector_frame_pos")
    return {
        "inventory_ready": not inv_missing,
        "ui_ready": not ui_missing,
        "ocr_ready": blossom_ocr.ocr_available(),
        "inventory_missing": inv_missing,
        "ui_missing": ui_missing,
        "layout": {
            "button_width": layout.button_width,
            "button_height": layout.button_height,
            "button_count": layout.button_count,
            "button_spacing": layout.button_spacing,
        },
        "frame": list(frame) if frame else None,
        "slots": layout_slot_preview(config, get_point),
        "drives": normalize_drive_toggles(config.get("biome_selector_drives")),
    }


def _autoit_send(token: str) -> bool:
    try:
        import autoit

        autoit.send(token)
        return True
    except Exception as error:
        print(f"[main macro] biome selector: autoit send {token!r} failed: {error}")
        return False


def _type_search_query(text: str) -> None:
    _autoit_send("^{a}")
    _autoit_send("{BACKSPACE}")
    _autoit_send(text)


def _normalize_label(text: str) -> str:
    line = (text or "").lower()
    line = re.sub(r"[^a-z0-9]+", " ", line)
    return " ".join(line.split())


def _fuzzy_drive_match(ocr_text: str, drive_name: str) -> bool:
    a = _normalize_label(ocr_text)
    b = _normalize_label(drive_name)
    if not a or not b:
        return False
    if b in a or a in b:
        return True
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if not b_tokens:
        return False
    overlap = len(a_tokens & b_tokens) / len(b_tokens)
    return overlap >= 0.6


def _enabled_drives(config: dict) -> list[str]:
    toggles = normalize_drive_toggles(config.get("biome_selector_drives"))
    return [name for name, on in toggles.items() if on]


def _run_inventory_use(
    *,
    config: dict,
    get_point: GetPoint,
    focus_roblox: Callable[[], bool],
    cancel_event,
) -> str | None:
    """Returns None on success, or an error/cancel string."""
    click_delay = _click_delay_sec(config)
    steps: list[tuple[str, str | None, int, str]] = [
        ("inventory_menu", None, 1, "open inventory"),
        ("search_bar", "potion_search_bar", 2, "search bar"),
    ]
    for key, fallback, clicks, label in steps:
        point = _resolve_point(get_point, key, fallback)
        if point is None:
            return f"Error: missing calibration {key}"
        if not github_original_click_at(*point, click=clicks, pre_sleep_sec=click_delay, cancel=cancel_event):
            return "Cancelled"
        print(f"[main macro] biome selector: {label} at {point}")
        if not _sleep_sec(0.2 + click_delay, cancel_event):
            return "Cancelled"

    _type_search_query(BIOME_SELECTOR_SEARCH_TEXT)
    if not _sleep_sec(0.25 + click_delay, cancel_event):
        return "Cancelled"
    _autoit_send("{ENTER}")
    if not _sleep_sec(0.35 + click_delay, cancel_event):
        return "Cancelled"

    first_slot = _resolve_point(get_point, "first_item_inventory_slot_pos")
    if first_slot is None:
        return "Error: missing first_item_inventory_slot_pos"
    if not github_original_click_at(*first_slot, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
        return "Cancelled"
    if not _sleep_sec(0.3 + click_delay, cancel_event):
        return "Cancelled"

    use_button = _resolve_point(get_point, "use_button")
    if use_button is None:
        return "Error: missing use_button"
    if not github_original_click_at(*use_button, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
        return "Cancelled"
    if not _sleep_sec(0.22 + click_delay, cancel_event):
        return "Cancelled"

    close_button = _resolve_point(get_point, "inventory_close_button") or _resolve_point(
        get_point, "inventory_menu"
    )
    if close_button is not None:
        github_original_click_at(*close_button, click=1, pre_sleep_sec=click_delay, cancel=cancel_event)
        _sleep_sec(0.22 + click_delay, cancel_event)
    return None


def _click_confirm(
    *,
    config: dict,
    get_point: GetPoint,
    cancel_event,
) -> bool:
    click_delay = _click_delay_sec(config)
    confirm = _resolve_point(get_point, "biome_selector_confirm_pos")
    if confirm is None:
        print("[main macro] biome selector: missing confirm calibration")
        return False

    if not github_original_click_at(*confirm, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
        return False
    return _sleep_sec(CONFIRM_SETTLE_SEC, cancel_event)


def _run_drive_panel(
    *,
    config: dict,
    get_point: GetPoint,
    get_region: GetRegion,
    cancel_event,
) -> str:
    if not blossom_ocr.ocr_available():
        return "Error: Windows OCR required for Biome Selector drives"

    enabled = _enabled_drives(config)
    if not enabled:
        return "Skipped: no drives enabled in Biome Selector settings"

    first = _resolve_point(get_point, "biome_selector_first_drive_pos")
    if first is None:
        return "Error: missing biome_selector_first_drive_pos"

    layout = read_drive_layout(config)
    if not _sleep_sec(UI_SETTLE_SEC, cancel_event):
        return "Cancelled"

    clicked: list[str] = []
    for index in range(layout.button_count):
        if cancel_event.is_set():
            return "Cancelled"

        region = layout.row_ocr_region(first, index)
        frame = _resolve_region(get_region, "biome_selector_frame_pos")
        if frame is not None:
            fx, fy, fw, fh = frame
            rx, ry, rw, rh = region
            if ry < fy or ry + rh > fy + fh:
                continue

        raw = blossom_ocr.ocr_region(region, psm=ROW_OCR_PSM)
        label = (raw or "").strip()
        print(f"[main macro] biome selector: row {index} OCR -> {label!r}")

        matched_drive = None
        for drive in enabled:
            if _fuzzy_drive_match(label, drive):
                matched_drive = drive
                break
        if not matched_drive:
            continue

        cx, cy = layout.row_center(first, index)
        click_delay = _click_delay_sec(config)
        if not github_original_click_at(cx, cy, click=1, pre_sleep_sec=click_delay, cancel=cancel_event):
            return "Cancelled"
        print(f"[main macro] biome selector: clicked enabled drive {matched_drive!r} at ({cx}, {cy})")
        if not _sleep_sec(0.35 + click_delay, cancel_event):
            return "Cancelled"

        if not _click_confirm(
            config=config,
            get_point=get_point,
            cancel_event=cancel_event,
        ):
            return "Cancelled"
        clicked.append(matched_drive)
        if not _sleep_sec(0.45, cancel_event):
            return "Cancelled"

    if not clicked:
        return "Error: OCR found no enabled drives in the calibrated list"
    return f"OK: selected {', '.join(clicked)}"


def run_biome_selector(
    *,
    config: dict,
    get_point: GetPoint,
    get_region: GetRegion,
    focus_roblox: Callable[[], bool],
    cancel_event,
    reason: str,
) -> str:
    ready, missing = biome_selector_ready(get_point, get_region=get_region, config=config)
    if not ready:
        return "Skipped: biome selector not ready — " + ", ".join(missing)
    if cancel_event.is_set():
        return "Cancelled"

    print(f"[main macro] biome selector ({reason})")
    if not focus_roblox():
        return "Error: Roblox not focused"

    if not _sleep_sec(PRE_USE_SETTLE_SEC, cancel_event):
        return "Cancelled"

    inv_result = _run_inventory_use(
        config=config,
        get_point=get_point,
        focus_roblox=focus_roblox,
        cancel_event=cancel_event,
    )
    if inv_result:
        return inv_result

    return _run_drive_panel(
        config=config,
        get_point=get_point,
        get_region=get_region,
        cancel_event=cancel_event,
    )
