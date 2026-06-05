#!/usr/bin/env python3
"""
Record movement/obby paths in the exact JSON format Blossom uses.

Usage:
  py tools/blossom_path_recorder.py record --name my_route
  py tools/blossom_path_recorder.py replay Blossom/paths/my_route.json
  py tools/blossom_path_recorder.py validate paths/my_route.json

Interactive record session (default: keys only, no mouse):
  F4  = start recording
  F10 = stop and save
  F5  = replay saved path (after save, or pass --name)
  Q   = quit
  Esc = cancel current recording

Output goes to %LOCALAPPDATA%\\Blossom\\paths\\ by default, or --out DIR.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from macro_engine import (  # noqa: E402
    MacroRecorder,
    MacroReplayer,
    filter_recorder_hotkeys,
    focus_roblox_window,
    normalize_events,
    save_json,
)

from blossom_dirs import OBBY_PATHS_DIR
from blossom_prepath import replay_movement_path

PATH_SEARCH_DIRS = (OBBY_PATHS_DIR, ROOT / "paths", ROOT / "Blossom" / "paths")

DEFAULT_OUT = OBBY_PATHS_DIR
SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

HOTKEY_START = "f4"
HOTKEY_STOP = "f10"
HOTKEY_REPLAY = "f5"
HOTKEY_QUIT = "q"

RECORDER_SUPPRESS_KEYS = {
    HOTKEY_START,
    HOTKEY_STOP,
    HOTKEY_REPLAY,
    HOTKEY_QUIT,
    "esc",
    "escape",
    "f9",
}


def resolve_output_dir(explicit: str | None) -> Path:
    if explicit:
        out = Path(explicit).expanduser().resolve()
    else:
        out = DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    return out


def safe_filename(name: str) -> str:
    stem = Path(name.strip()).stem
    if not stem or not SAFE_NAME.match(stem):
        raise ValueError(
            "Name must be 1-64 chars: letters, numbers, underscore, hyphen only "
            "(e.g. eden_route, egg_route4)"
        )
    return f"{stem}.json"


def build_payload(
    events: list[dict],
    *,
    keys_only: bool = True,
    label: str = "",
) -> dict:
    filtered = filter_recorder_hotkeys(list(events))
    if keys_only:
        filtered = [e for e in filtered if str(e.get("type", "")).startswith("key_")]
    payload: dict = {
        "events": normalize_events(filtered),
        "created": time.time(),
        "label": label or "",
        "keys_only": bool(keys_only),
    }
    try:
        import ctypes

        w = int(ctypes.windll.user32.GetSystemMetrics(0))
        h = int(ctypes.windll.user32.GetSystemMetrics(1))
        payload["screen"] = {"w": w, "h": h}
    except Exception:
        pass
    return payload


def validate_payload(payload: dict) -> list[str]:
    issues: list[str] = []
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        issues.append("Missing or empty 'events' array.")
        return issues

    allowed = {"mouse_move", "mouse_down", "mouse_up", "key_down", "key_up"}
    for index, event in enumerate(events[:20]):
        if not isinstance(event, dict):
            issues.append(f"Event #{index} is not an object.")
            continue
        if event.get("type") not in allowed:
            issues.append(f"Event #{index} has unknown type: {event.get('type')!r}")

    types = {e.get("type") for e in events if isinstance(e, dict)}
    if payload.get("keys_only") and types & {"mouse_move", "mouse_down", "mouse_up"}:
        issues.append("keys_only is set but file still has mouse events.")

    if not any(t in types for t in ("key_down", "mouse_down")):
        issues.append("No key_down or mouse_down events — path may do nothing on replay.")

    return issues


def run_replay(path: Path, *, delay_sec: float = 3.0) -> int:
    if not path.is_file():
        print(f"Not found: {path}")
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    issues = validate_payload(payload)
    if issues:
        print("Validation warnings (replaying anyway):")
        for item in issues:
            print(f"  - {item}")
    print("Click the Roblox window now.")
    print(f"Replay starts in {int(delay_sec)} seconds...")
    time.sleep(max(0.0, delay_sec))
    if focus_roblox_window():
        print("Roblox focused.")
    else:
        print("Could not auto-focus Roblox — click the game window before replay runs.")
    replayer = MacroReplayer()
    result = replay_movement_path(
        replayer,
        payload,
        path_file=path.resolve(),
        search_dirs=PATH_SEARCH_DIRS,
        focus_roblox=False,
    )
    print(result)
    filtered = filter_recorder_hotkeys(payload.get("events") or [])
    key_count = sum(
        1
        for e in filtered
        if isinstance(e, dict) and str(e.get("type", "")).startswith("key_")
    )
    print(f"({key_count} movement keys after filtering recorder hotkeys)")
    return 0 if not str(result).startswith("Error") else 1


def print_session_help(dest: Path, *, keys_only: bool) -> None:
    mode = "keys only (WASD — mouse ignored)" if keys_only else "keys + mouse clicks"
    print()
    print("Blossom path recorder")
    print(f"  Mode: {mode}")
    print(f"  Save to: {dest}")
    print(f"  {HOTKEY_START.upper()}  = start recording")
    print(f"  {HOTKEY_STOP.upper()} = stop and save")
    print(f"  {HOTKEY_REPLAY.upper()}  = replay saved path")
    print("  Esc  = cancel recording")
    print("  Q    = quit")
    print()


def cmd_record(args: argparse.Namespace) -> int:
    try:
        import keyboard
    except ImportError:
        print("Install dependencies: py -m pip install keyboard mouse")
        return 1

    keys_only = not getattr(args, "include_mouse", False)
    out_dir = resolve_output_dir(args.out)
    filename = safe_filename(args.name)
    dest = out_dir / filename

    print_session_help(dest, keys_only=keys_only)

    recorder = MacroRecorder()
    state = {
        "phase": "idle",
        "stop": False,
        "quit": False,
        "last_saved": None,
    }

    def on_start():
        if state["phase"] != "idle" or state["quit"]:
            return
        state["phase"] = "recording"
        recorder.start(keys_only=keys_only, suppress_keys=RECORDER_SUPPRESS_KEYS)
        print(f"Recording… ({HOTKEY_STOP.upper()} = save, Esc = cancel)")

    def on_stop():
        if state["phase"] != "recording":
            return
        state["stop"] = True

    def on_cancel():
        if state["phase"] != "recording":
            return
        recorder.stop()
        state["phase"] = "idle"
        print("Recording cancelled.")

    def on_replay():
        if state["phase"] == "recording":
            print("Stop recording first (F10).")
            return
        target = state.get("last_saved") or dest
        if not Path(target).is_file():
            print(f"No saved path yet: {target}")
            return
        keyboard.unhook_all_hotkeys()
        try:
            run_replay(Path(target), delay_sec=args.replay_delay)
        finally:
            register_hotkeys()

    def on_quit():
        if state["phase"] == "recording":
            recorder.stop()
        state["quit"] = True

    def register_hotkeys():
        keyboard.add_hotkey(HOTKEY_START, on_start)
        keyboard.add_hotkey(HOTKEY_STOP, on_stop)
        keyboard.add_hotkey(HOTKEY_REPLAY, on_replay)
        keyboard.add_hotkey(HOTKEY_QUIT, on_quit)
        keyboard.add_hotkey("esc", on_cancel)

    register_hotkeys()

    try:
        while not state["quit"]:
            if state["stop"]:
                state["stop"] = False
                if state["phase"] != "recording":
                    print(f"Not recording — press {HOTKEY_START.upper()} first.")
                    continue

                events = recorder.stop()
                state["phase"] = "idle"
                if not events:
                    print("No events captured.")
                    continue

                payload = build_payload(
                    events,
                    keys_only=keys_only,
                    label=args.label or args.name,
                )
                issues = validate_payload(payload)
                save_json(dest, payload)
                state["last_saved"] = dest

                manifest_path = dest.with_suffix(".manifest.json")
                manifest = {
                    "id": Path(filename).stem,
                    "filename": filename,
                    "label": args.label or args.name,
                    "task": args.task or "",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "event_count": len(payload["events"]),
                    "screen": payload.get("screen"),
                    "keys_only": payload.get("keys_only"),
                    "validation_issues": issues,
                }
                manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

                print(f"Saved {len(payload['events'])} key events -> {dest}")
                print(f"Press {HOTKEY_REPLAY.upper()} to test replay, {HOTKEY_START.upper()} to record again, Q to quit.")
                if issues:
                    print("Warnings:")
                    for item in issues:
                        print(f"  - {item}")
                continue

            time.sleep(0.1)
    finally:
        keyboard.unhook_all_hotkeys()
        try:
            import keyboard as kb

            kb.release("w")
            kb.release("a")
            kb.release("s")
            kb.release("d")
            kb.release("space")
        except Exception:
            pass

    print("Bye.")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.file).resolve()
    if not path.is_file():
        print(f"Not found: {path}")
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    issues = validate_payload(payload)
    events = payload.get("events") or []
    types: dict[str, int] = {}
    for e in events:
        if isinstance(e, dict):
            t = str(e.get("type", "?"))
            types[t] = types.get(t, 0) + 1
    print(f"File: {path}")
    print(f"Events: {len(events)}")
    print(f"Types: {types}")
    print(f"Screen: {payload.get('screen')}")
    if issues:
        print("Issues:")
        for item in issues:
            print(f"  - {item}")
        return 1
    print("OK — compatible with Blossom replay format.")
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    return run_replay(Path(args.file).resolve(), delay_sec=args.delay)


def cmd_export(args: argparse.Namespace) -> int:
    out_dir = resolve_output_dir(args.out)
    filename = safe_filename(args.name)
    src = Path(args.file).resolve() if args.file else out_dir / filename
    if not src.is_file():
        print(f"Path file not found: {src}")
        return 1
    payload = json.loads(src.read_text(encoding="utf-8"))
    manifest_path = src.with_suffix(".manifest.json")
    manifest = {
        "id": Path(filename).stem,
        "filename": src.name,
        "label": args.label or args.name,
        "task": args.task or "",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "event_count": len(payload.get("events") or []),
        "screen": payload.get("screen"),
        "keys_only": payload.get("keys_only"),
        "validation_issues": validate_payload(payload),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {manifest_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Record Blossom-compatible path JSON files.")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser(
        "record",
        help=f"Record session ({HOTKEY_START.upper()} start, {HOTKEY_STOP.upper()} save, {HOTKEY_REPLAY.upper()} replay)",
    )
    rec.add_argument("--name", required=True, help="File name without .json (e.g. my_obby)")
    rec.add_argument("--label", default="", help="Human-readable label")
    rec.add_argument("--task", default="", help="What this path is for (Eden, egg, obby, etc.)")
    rec.add_argument("--out", default=None, help="Output directory (default: Blossom/paths)")
    rec.add_argument(
        "--include-mouse",
        action="store_true",
        help="Also record mouse clicks (default: keys only, no mouse)",
    )
    rec.add_argument(
        "--replay-delay",
        type=float,
        default=3.0,
        help="Seconds before F5 replay starts (default: 3)",
    )
    rec.set_defaults(func=cmd_record)

    val = sub.add_parser("validate", help="Check a path file")
    val.add_argument("file", help="Path to .json")
    val.set_defaults(func=cmd_validate)

    rep = sub.add_parser("replay", help="Replay a path file in Roblox")
    rep.add_argument("file", help="Path to .json")
    rep.add_argument("--delay", type=float, default=3.0, help="Countdown before replay")
    rep.set_defaults(func=cmd_replay)

    exp = sub.add_parser("export", help="Write/update .manifest.json for sharing")
    exp.add_argument("--name", required=True, help="Path id / stem")
    exp.add_argument("--file", default=None, help="Source .json (default: paths/<name>.json)")
    exp.add_argument("--label", default="")
    exp.add_argument("--task", default="", help="e.g. eden_contract, auto_obby, egg_route")
    exp.add_argument("--out", default=None)
    exp.set_defaults(func=cmd_export)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
