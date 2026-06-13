"""Global camera + character align before replaying any movement path."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Sequence

from blossom_dirs import APP_CONFIG_PATH, CHAR_ALIGN_FILENAME
from macro_engine import (
    MacroReplayer,
    _cancelled,
    _sleep_sec,
    align_camera_look_down,
    focus_roblox_window,
    load_json,
    normalize_events,
    release_stuck_inputs,
    reset_character_in_game,
)

CHAR_ALIGN_STEM = "char_align"
PRE_PATH_WAIT_AFTER_CAMERA_SEC = 0.0
# Settle time after char_align.json finishes, before the main path plays. Gives
# the character a beat to stop drifting from the align nudge.
POST_CHAR_ALIGN_WAIT_SEC = 2.0
COLLECTIONS_CONFIG_KEY = "collections_button"
EXIT_COLLECTIONS_CONFIG_KEY = "exit_collections_button"

# Eden paths are excluded from the char_align pre-step (they have their own
# entry/alignment and char_align throws the route off).
_EDEN_PATH_STEMS = frozenset({"eden", "edenpath", "eden_path"})


def _calibration_point_from_config(config: dict, key: str) -> tuple[int, int] | None:
    value = config.get(key)
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        x = int(round(float(value[0])))
        y = int(round(float(value[1])))
    except (TypeError, ValueError):
        return None
    if x <= 0 and y <= 0:
        return None
    return x, y


def collections_align_points_from_config() -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    if not APP_CONFIG_PATH.is_file():
        return None, None
    try:
        config = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    return (
        _calibration_point_from_config(config, COLLECTIONS_CONFIG_KEY),
        _calibration_point_from_config(config, EXIT_COLLECTIONS_CONFIG_KEY),
    )


def is_char_align_path(path: Path | None) -> bool:
    if path is None:
        return False
    return path.stem.lower() == CHAR_ALIGN_STEM


def is_eden_path(path: Path | None) -> bool:
    if path is None:
        return False
    return path.stem.lower() in _EDEN_PATH_STEMS


def _keys_only_payload(payload: dict) -> dict:
    """Strip mouse events so char_align never moves the cursor during replay."""
    events = [
        e
        for e in (payload.get("events") or [])
        if isinstance(e, dict) and str(e.get("type", "")).startswith("key_")
    ]
    return {
        **payload,
        "events": normalize_events(events),
        "keys_only": True,
    }


def resolve_char_align_path(search_dirs: Sequence[Path]) -> Path | None:
    for folder in search_dirs:
        candidate = folder / CHAR_ALIGN_FILENAME
        if candidate.is_file():
            return candidate
    return None


def path_playback_multiplier_from_config(*, default: float = 1.0) -> float:
    if not APP_CONFIG_PATH.is_file():
        return default
    try:
        config = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    for key in (
        "path_playback_multiplier",
        "obby_playback_multiplier",
        "egg_playback_multiplier",
        "fishing_playback_multiplier",
    ):
        raw = config.get(key)
        if raw is None:
            continue
        try:
            value = float(raw)
            if value > 0:
                return max(0.25, min(value, 4.0))
        except (TypeError, ValueError):
            continue
    return default


def camera_align_down_px_from_config(*, default: int = 80) -> int:
    if not APP_CONFIG_PATH.is_file():
        return default
    try:
        config = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
        return int(config.get("camera_align_down_px", default))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return default


def run_pre_path_alignment(
    replayer: MacroReplayer,
    *,
    search_dirs: Sequence[Path],
    camera_down_px: int | None = None,
    wait_after_camera_sec: float = PRE_PATH_WAIT_AFTER_CAMERA_SEC,
    skip_char_align_replay: bool = False,
    cancel: threading.Event | None = None,
) -> str | None:
    """
    Camera align, wait 3s, then replay char_align.json (unless already playing that file).
    Returns an error/cancelled status string, or None on success.
    """
    pixels = camera_down_px if camera_down_px is not None else camera_align_down_px_from_config()
    if _cancelled(cancel):
        return "Cancelled"

    if not focus_roblox_window():
        print("[pre-path align] warning: could not focus Roblox")
    if not _sleep_sec(0.15, cancel):
        return "Cancelled"

    collections, exit_collections = collections_align_points_from_config()
    camera_result = align_camera_look_down(
        down_px=pixels,
        collections=collections,
        exit_collections=exit_collections,
        cancel=cancel,
    )
    if camera_result == "Cancelled":
        return "Cancelled"
    if str(camera_result).startswith("Error"):
        return str(camera_result)

    if not reset_character_in_game(reason="after camera align", cancel=cancel):
        return "Cancelled"

    wait_sec = max(0.0, float(wait_after_camera_sec))
    if wait_sec > 0:
        print(f"[pre-path align] extra settle {wait_sec:g}s")
        if not _sleep_sec(wait_sec, cancel):
            return "Cancelled"

    multiplier = path_playback_multiplier_from_config()

    if skip_char_align_replay:
        print("[pre-path align] skipping char_align.json (main path is char_align)")
        return None

    align_path = resolve_char_align_path(search_dirs)
    if align_path is None:
        print("[pre-path align] char_align.json not found — skipping character align")
        return None

    print(f"[pre-path align] replaying {align_path.name} (multiplier={multiplier:g}, keys only)")
    char_payload = _keys_only_payload(load_json(align_path))
    char_result = replayer.replay(
        char_payload,
        focus_roblox=False,
        playback_multiplier=multiplier,
        reset_before=False,
    )
    if str(char_result).startswith("Error") or char_result == "Cancelled":
        return str(char_result)
    if not release_stuck_inputs(reason="after char_align", cancel=cancel):
        return "Cancelled"
    print("[pre-path align] char_align finished")

    post_wait = max(0.0, float(POST_CHAR_ALIGN_WAIT_SEC))
    if post_wait > 0:
        print(f"[pre-path align] settle {post_wait:g}s after char_align")
        if not _sleep_sec(post_wait, cancel):
            return "Cancelled"
    return None


def replay_movement_path(
    replayer: MacroReplayer,
    payload: dict,
    *,
    path_file: Path | None = None,
    search_dirs: Sequence[Path],
    camera_down_px: int | None = None,
    wait_after_camera_sec: float = PRE_PATH_WAIT_AFTER_CAMERA_SEC,
    focus_roblox: bool = True,
) -> str:
    """Camera align + wait + char_align, then the requested path.

    Eden paths skip the char_align pre-step (and its settle) since char_align
    knocks the Eden route off its own entry alignment.
    """
    skip_char_align = is_char_align_path(path_file) or is_eden_path(path_file)
    pre_error = run_pre_path_alignment(
        replayer,
        search_dirs=search_dirs,
        camera_down_px=camera_down_px,
        wait_after_camera_sec=wait_after_camera_sec,
        skip_char_align_replay=skip_char_align,
        cancel=replayer._external_cancel,
    )
    if pre_error:
        return pre_error
    if replayer._should_cancel():
        return "Cancelled"

    multiplier = path_playback_multiplier_from_config()
    return replayer.replay(
        payload,
        focus_roblox=focus_roblox,
        playback_multiplier=multiplier,
        reset_before=True,
    )
