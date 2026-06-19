"""Ordered macro schedule — run fishing, potion craft, merchant, or idle for timed steps."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

SCHEDULE_ACTIVITIES = ("fishing", "potion", "merchant", "idle")

SCHEDULE_CONTROLLED_KEYS = (
    "fishing_mode",
    "enable_potion_crafting",
    "enable_potion_switching",
    "merchant_teleporter",
    "auto_merchant_teleporter",
)

_LEGACY_SEASONAL_KEYS = (
    "collect_easter",
    "egg_ocr_detect_special",
    "egg_playback_multiplier",
    "enable_auto_egg_pathing",
    "auto_egg_pathing",
)

DEFAULT_PROFILE_ID = "default"

_DEFAULT_PROFILE_STEPS: list[dict[str, Any]] = [
    {"activity": "fishing", "hours": 2, "minutes": 0},
    {"activity": "potion", "hours": 3, "minutes": 0},
]


def strip_legacy_seasonal_keys(config: dict) -> dict:
    """Remove retired Easter / egg-path keys from a config dict."""
    patch: dict = {}
    for key in _LEGACY_SEASONAL_KEYS:
        if key in config:
            patch[key] = None
    return patch


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _coerce_duration_part(value: Any, *, default: int = 0, maximum: int = 99) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return max(0, min(parsed, maximum))


def new_schedule_profile_id() -> str:
    return uuid.uuid4().hex[:12]


def normalize_schedule_step(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    activity = str(raw.get("activity") or raw.get("mode") or "").strip().lower()
    if activity not in SCHEDULE_ACTIVITIES:
        return None
    hours = _coerce_duration_part(raw.get("hours"), default=0, maximum=48)
    minutes = _coerce_duration_part(raw.get("minutes"), default=0, maximum=59)
    if hours == 0 and minutes == 0:
        minutes = 30
    return {"activity": activity, "hours": hours, "minutes": minutes}


def default_schedule_profile(*, profile_id: str | None = None, name: str = "Default") -> dict[str, Any]:
    return {
        "id": profile_id or DEFAULT_PROFILE_ID,
        "name": name,
        "steps": deepcopy(_DEFAULT_PROFILE_STEPS),
        "loop": True,
    }


def normalize_schedule_profile(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    profile_id = str(raw.get("id") or "").strip() or new_schedule_profile_id()
    name = str(raw.get("name") or "Untitled").strip() or "Untitled"
    steps: list[dict[str, Any]] = []
    if isinstance(raw.get("steps"), list):
        for entry in raw["steps"]:
            step = normalize_schedule_step(entry)
            if step is not None:
                steps.append(step)
    if not steps:
        steps = deepcopy(_DEFAULT_PROFILE_STEPS)
    return {
        "id": profile_id,
        "name": name,
        "steps": steps,
        "loop": _coerce_bool(raw.get("loop", True)),
    }


def migrate_schedule_profiles(config: dict) -> tuple[dict[str, Any], bool]:
    """Ensure config has macro_schedule_profiles; migrate legacy macro_schedule_steps once."""
    if isinstance(config.get("macro_schedule_profiles"), list) and config["macro_schedule_profiles"]:
        return config, False

    steps: list[dict[str, Any]] = []
    raw_steps = config.get("macro_schedule_steps")
    if isinstance(raw_steps, list):
        for entry in raw_steps:
            step = normalize_schedule_step(entry)
            if step is not None:
                steps.append(step)

    loop = _coerce_bool(config.get("macro_schedule_loop", True))
    profile = default_schedule_profile()
    if steps:
        profile["steps"] = steps
    profile["loop"] = loop

    active_id = str(config.get("macro_schedule_active_profile_id") or DEFAULT_PROFILE_ID).strip()
    if not active_id:
        active_id = DEFAULT_PROFILE_ID
    profile["id"] = DEFAULT_PROFILE_ID

    migrated = deepcopy(config)
    migrated["macro_schedule_profiles"] = [profile]
    migrated["macro_schedule_active_profile_id"] = active_id
    migrated["macro_schedule_steps"] = profile["steps"]
    migrated["macro_schedule_loop"] = profile["loop"]
    return migrated, True


def _normalize_profiles_list(raw_profiles: Any) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    if isinstance(raw_profiles, list):
        for entry in raw_profiles:
            profile = normalize_schedule_profile(entry)
            if profile is not None:
                profiles.append(profile)
    if not profiles:
        profiles.append(default_schedule_profile())
    return profiles


def get_active_schedule_profile(config: dict) -> dict[str, Any]:
    """Return the normalized profile used when the macro schedule runs."""
    cfg, _ = migrate_schedule_profiles(config)
    profiles = _normalize_profiles_list(cfg.get("macro_schedule_profiles"))
    active_id = str(cfg.get("macro_schedule_active_profile_id") or DEFAULT_PROFILE_ID).strip()
    for profile in profiles:
        if profile["id"] == active_id:
            return profile
    return profiles[0]


def sync_legacy_schedule_keys(config: dict) -> dict[str, Any]:
    """Keep macro_schedule_steps / macro_schedule_loop aligned with the active profile."""
    merged = deepcopy(config)
    active = get_active_schedule_profile(merged)
    merged["macro_schedule_steps"] = active["steps"]
    merged["macro_schedule_loop"] = active["loop"]
    merged["macro_schedule_active_profile_id"] = active["id"]
    return merged


def normalize_macro_schedule_profiles(config: dict) -> dict[str, Any]:
    cfg, _ = migrate_schedule_profiles(config)
    profiles = _normalize_profiles_list(cfg.get("macro_schedule_profiles"))
    active_id = str(cfg.get("macro_schedule_active_profile_id") or profiles[0]["id"]).strip()
    if not any(p["id"] == active_id for p in profiles):
        active_id = profiles[0]["id"]
    return {
        "enabled": _coerce_bool(cfg.get("macro_schedule_enabled")),
        "active_profile_id": active_id,
        "profiles": profiles,
    }


def normalize_macro_schedule(config: dict) -> dict[str, Any]:
    cfg, _ = migrate_schedule_profiles(config)
    active = get_active_schedule_profile(cfg)
    bundle = normalize_macro_schedule_profiles(cfg)
    return {
        "enabled": bundle["enabled"],
        "loop": active["loop"],
        "steps": active["steps"],
        "active_profile_id": active["id"],
        "profiles": bundle["profiles"],
    }


def schedule_step_duration_sec(step: dict[str, Any]) -> float:
    hours = _coerce_duration_part(step.get("hours"), default=0)
    minutes = _coerce_duration_part(step.get("minutes"), default=30)
    return float(max(60, hours * 3600 + minutes * 60))


def schedule_activity_patch(activity: str) -> dict[str, bool]:
    """Config toggles forced for a schedule step (other keys unchanged)."""
    activity = str(activity or "").strip().lower()
    off = {key: False for key in SCHEDULE_CONTROLLED_KEYS}
    if activity == "fishing":
        return {**off, "fishing_mode": True}
    if activity == "potion":
        return {**off, "enable_potion_crafting": True}
    if activity == "merchant":
        return {**off, "merchant_teleporter": True}
    if activity == "idle":
        return off
    return off


def schedule_status(
    *,
    config: dict,
    step_index: int,
    step_started_at: float,
    now: float,
    active: bool,
) -> dict[str, Any]:
    schedule = normalize_macro_schedule(config)
    steps = schedule["steps"]
    if not active or not schedule["enabled"] or not steps:
        return {
            "active": False,
            "enabled": schedule["enabled"],
            "loop": schedule["loop"],
            "steps": steps,
            "step_index": 0,
            "step_count": len(steps),
            "step_activity": "",
            "step_remaining_seconds": 0.0,
            "active_profile_id": schedule.get("active_profile_id", ""),
        }
    index = max(0, min(int(step_index), len(steps) - 1))
    step = steps[index]
    elapsed = max(0.0, now - step_started_at)
    remaining = max(0.0, schedule_step_duration_sec(step) - elapsed)
    return {
        "active": True,
        "enabled": True,
        "loop": schedule["loop"],
        "steps": steps,
        "step_index": index,
        "step_count": len(steps),
        "step_activity": step["activity"],
        "step_remaining_seconds": round(remaining, 1),
        "active_profile_id": schedule.get("active_profile_id", ""),
    }


def merge_schedule_profiles_payload(config: dict, payload: dict) -> dict:
    """Return a config dict with schedule profile fields merged from the UI payload."""
    merged, _ = migrate_schedule_profiles(config)
    if not isinstance(payload, dict):
        return sync_legacy_schedule_keys(merged)

    if "enabled" in payload:
        merged["macro_schedule_enabled"] = bool(payload.get("enabled"))

    if "active_profile_id" in payload:
        merged["macro_schedule_active_profile_id"] = str(payload.get("active_profile_id") or "").strip()

    if "profiles" in payload and isinstance(payload.get("profiles"), list):
        profiles: list[dict[str, Any]] = []
        for entry in payload["profiles"]:
            profile = normalize_schedule_profile(entry)
            if profile is not None:
                profiles.append(profile)
        if profiles:
            merged["macro_schedule_profiles"] = profiles

    return sync_legacy_schedule_keys(merged)


def merge_schedule_payload(config: dict, payload: dict) -> dict:
    """Return a config dict with schedule fields merged from the UI payload."""
    merged = deepcopy(config)
    if not isinstance(payload, dict):
        return merged
    merged, _ = migrate_schedule_profiles(merged)

    if "enabled" in payload:
        merged["macro_schedule_enabled"] = bool(payload.get("enabled"))

    if "active_profile_id" in payload:
        merged["macro_schedule_active_profile_id"] = str(payload.get("active_profile_id") or "").strip()

    if "profiles" in payload and isinstance(payload.get("profiles"), list):
        profiles: list[dict[str, Any]] = []
        for entry in payload["profiles"]:
            profile = normalize_schedule_profile(entry)
            if profile is not None:
                profiles.append(profile)
        if profiles:
            merged["macro_schedule_profiles"] = profiles

    active = get_active_schedule_profile(merged)
    profile_updated = False

    if "loop" in payload:
        active = {**active, "loop": bool(payload.get("loop"))}
        profile_updated = True

    if "steps" in payload and isinstance(payload.get("steps"), list):
        steps: list[dict[str, Any]] = []
        for entry in payload["steps"]:
            step = normalize_schedule_step(entry)
            if step is not None:
                steps.append(step)
        active = {**active, "steps": steps}
        profile_updated = True

    if profile_updated:
        profiles = _normalize_profiles_list(merged.get("macro_schedule_profiles"))
        replaced = False
        for index, profile in enumerate(profiles):
            if profile["id"] == active["id"]:
                profiles[index] = normalize_schedule_profile(active) or profile
                replaced = True
                break
        if not replaced:
            profiles.append(normalize_schedule_profile(active) or default_schedule_profile())
        merged["macro_schedule_profiles"] = profiles

    return sync_legacy_schedule_keys(merged)
