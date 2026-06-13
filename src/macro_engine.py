"""Record and replay mouse/keyboard macros for potion crafting and obby paths."""

from __future__ import annotations

import json
import re
import sys
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Callable

import autoit




if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    KEYEVENTF_KEYUP = 0x0002
    VK_MAP = {
        "space": 0x20,
        "enter": 0x0D,
        "tab": 0x09,
        "escape": 0x1B,
        "esc": 0x1B,
        "shift": 0x10,
        "ctrl": 0x11,
        "control": 0x11,
        "alt": 0x12,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
    }
    for _fi in range(1, 13):
        VK_MAP[f"f{_fi}"] = 0x70 + (_fi - 1)

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

else:
    user32 = None

CLICK_HOLD_SEC = 0.09
PRE_CLICK_SETTLE_SEC = 0.03
TWEEN_MOVE_SEC = 0.055
TWEEN_MOVE_STEPS = 7
POTION_MAX_CLICK_GAP_SEC = 0.35
MAX_EVENT_GAP_SEC = 8.0
MOVEMENT_REPLAY_MAX_GAP_SEC = 90.0
REPLAY_KEY_SETTLE_SEC = 0.012
REPLAY_INPUT_RESET_SEC = 0.08
CHAR_RESET_WAIT_SEC = 1.35
CHAR_RESET_KEY_GAP_SEC = 0.04
CANCEL_SLEEP_CHUNK_SEC = 0.05
RELEASE_KEYS = (
    "w",
    "a",
    "s",
    "d",
    "q",
    "e",
    "space",
    "shift",
    "ctrl",
    "alt",
    "left",
    "right",
    "up",
    "down",
)
CAMERA_ALIGN_DOWN_PX = 80
CAMERA_ALIGN_RMB_HOLD_SEC = 0.2
CAMERA_ALIGN_UI_GAP_SEC = 0.19
CAMERA_ALIGN_DRAG_SEC = 0.28
CAMERA_ALIGN_DRAG_STEPS = 16
CAMERA_ALIGN_RETURN_SEC = 0.24
CAMERA_ALIGN_RETURN_STEPS = 14

# Inventory / UI click pacing (15% faster). Not applied to potion crafting or fishing.
UI_CLICK_SPEED_MULTIPLIER = 0.85


def inventory_click_delay_sec(config: dict, *, default_ms: float = 350) -> float:
    """Config inventory_click_delay in seconds, scaled for faster UI clicks."""
    raw = config.get("inventory_click_delay", default_ms)
    try:
        ms = float(raw)
    except (TypeError, ValueError):
        ms = default_ms
    return max(0.05, (ms / 1000.0) * UI_CLICK_SPEED_MULTIPLIER)


def _cursor_pos() -> tuple[int, int]:
    if user32 is None:
        return 0, 0

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def _ease_out_quad(t: float) -> float:
    t = max(0.0, min(1.0, float(t)))
    return 1.0 - (1.0 - t) * (1.0 - t)


def _smooth_move_axis(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    *,
    duration: float,
    steps: int,
    cancel: threading.Event | None = None,
) -> bool:
    if user32 is None:
        return True
    step_count = max(1, int(steps))
    sleep_for = max(0.001, float(duration) / step_count)
    for step in range(1, step_count + 1):
        if _cancelled(cancel):
            return False
        t = _ease_out_quad(step / step_count)
        x = int(round(start_x + (end_x - start_x) * t))
        y = int(round(start_y + (end_y - start_y) * t))
        user32.SetCursorPos(x, y)
        if not _sleep_sec(sleep_for, cancel):
            return False
    return True


def _rmb_hold_registered(*, cancel: threading.Event | None = None) -> bool:
    """Hold RMB at the current cursor so Roblox sees look-drag."""
    mouse_button("right", down=True)
    return _sleep_sec(CAMERA_ALIGN_RMB_HOLD_SEC, cancel)


def align_camera_look_down(
    *,
    down_px: int = CAMERA_ALIGN_DOWN_PX,
    collections: tuple[int, int] | None = None,
    exit_collections: tuple[int, int] | None = None,
    cancel: threading.Event | None = None,
) -> str:
    """
    Collections menu → exit → hold RMB, drag down, release RMB, smooth return.
    """
    if user32 is None:
        return "Error: Windows input API unavailable"

    if _cancelled(cancel):
        return "Cancelled"

    if collections and (collections[0] > 0 or collections[1] > 0):
        print(f"[camera align] click collections at {collections[0]},{collections[1]}")
        if not click_at_settled(collections[0], collections[1], pre_sleep_sec=0.1, cancel=cancel):
            return "Cancelled"
        if not _sleep_sec(CAMERA_ALIGN_UI_GAP_SEC, cancel):
            return "Cancelled"
    else:
        print("[camera align] collections_button not calibrated — skipping")

    if exit_collections and (exit_collections[0] > 0 or exit_collections[1] > 0):
        print(f"[camera align] click exit collections at {exit_collections[0]},{exit_collections[1]}")
        if not click_at_settled(exit_collections[0], exit_collections[1], pre_sleep_sec=0.1, cancel=cancel):
            return "Cancelled"
        if not _sleep_sec(CAMERA_ALIGN_UI_GAP_SEC, cancel):
            return "Cancelled"
    else:
        print("[camera align] exit_collections_button not calibrated — skipping")

    pixels = max(1, min(int(down_px), 400))
    start_x, start_y = _cursor_pos()
    _, screen_h = _screen_size()
    target_y = min(start_y + pixels, screen_h - 1)

    print(f"[camera align] RMB hold + drag down {pixels}px from {start_x},{start_y}")
    if not _rmb_hold_registered(cancel=cancel):
        mouse_button("right", down=False)
        return "Cancelled"
    if not _smooth_move_axis(
        start_x,
        start_y,
        start_x,
        target_y,
        duration=CAMERA_ALIGN_DRAG_SEC,
        steps=CAMERA_ALIGN_DRAG_STEPS,
        cancel=cancel,
    ):
        mouse_button("right", down=False)
        return "Cancelled"
    mouse_button("right", down=False)
    if not _sleep_sec(PRE_CLICK_SETTLE_SEC, cancel):
        return "Cancelled"
    print(f"[camera align] smooth return to {start_x},{start_y}")
    if not _smooth_move_axis(
        start_x,
        target_y,
        start_x,
        start_y,
        duration=CAMERA_ALIGN_RETURN_SEC,
        steps=CAMERA_ALIGN_RETURN_STEPS,
        cancel=cancel,
    ):
        return "Cancelled"
    release_stuck_inputs(reason="camera align", cancel=cancel)
    return "Aligned!"


def _cancelled(cancel: threading.Event | None) -> bool:
    return cancel is not None and cancel.is_set()


def _sleep_sec(seconds: float, cancel: threading.Event | None = None) -> bool:
    """Sleep in small chunks so STOP can interrupt. Returns False if cancelled."""
    remaining = max(0.0, float(seconds))
    while remaining > 0:
        if _cancelled(cancel):
            return False
        step = min(remaining, CANCEL_SLEEP_CHUNK_SEC)
        time.sleep(step)
        remaining -= step
    return not _cancelled(cancel)


def _sleep_until(deadline: float, cancel: threading.Event | None = None) -> bool:
    while True:
        if _cancelled(cancel):
            return False
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return True
        time.sleep(min(remaining, CANCEL_SLEEP_CHUNK_SEC))
    return not _cancelled(cancel)


def release_stuck_inputs(*, reason: str = "", cancel: threading.Event | None = None) -> bool:
    """Release keys and mouse without the in-game reset combo."""
    label = f" ({reason})" if reason else ""
    print(f"[macro reset] releasing keys and mouse{label}")
    for key in RELEASE_KEYS:
        if _cancelled(cancel):
            return False
        replay_key_action(key, False)
    for button in ("left", "right", "middle"):
        if _cancelled(cancel):
            return False
        mouse_button(button, down=False)
    return _sleep_sec(REPLAY_INPUT_RESET_SEC, cancel)


def reset_input_state(*, reason: str = "", cancel: threading.Event | None = None) -> bool:
    return release_stuck_inputs(reason=reason, cancel=cancel)


def reset_character_in_game(*, reason: str = "character reset", cancel: threading.Event | None = None) -> bool:
    """Roblox character reset: Esc, R, Enter, then a short settle."""
    print(f"[macro reset] {reason}: Esc → R → Enter")
    if not release_stuck_inputs(cancel=cancel):
        return False

    for key in ("esc", "r", "enter"):
        if _cancelled(cancel):
            return False
        replay_key_action(key, True)
        if not _sleep_sec(CHAR_RESET_KEY_GAP_SEC, cancel):
            return False
        replay_key_action(key, False)
        if not _sleep_sec(CHAR_RESET_KEY_GAP_SEC, cancel):
            return False

    print(f"[macro reset] waiting {CHAR_RESET_WAIT_SEC:g}s after reset combo")
    if not _sleep_sec(CHAR_RESET_WAIT_SEC, cancel):
        return False
    return release_stuck_inputs(cancel=cancel)


def _screen_size() -> tuple[int, int]:
    if user32 is None:
        return 1920, 1080
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def _vk_for_key(key: str) -> int:
    key = (key or "").strip().lower()
    if not key:
        return 0
    if key in VK_MAP:
        return VK_MAP[key]
    match = re.match(r"^f(\d{1,2})$", key)
    if match:
        num = int(match.group(1))
        if 1 <= num <= 24:
            return 0x70 + (num - 1)
    if len(key) == 1:
        return user32.VkKeyScanW(ctypes.c_wchar(key)) & 0xFF
    return 0


def _button_flags(button: str, down: bool) -> int:
    button = (button or "left").lower()
    if button == "right":
        return MOUSEEVENTF_RIGHTDOWN if down else MOUSEEVENTF_RIGHTUP
    if button == "middle":
        return MOUSEEVENTF_MIDDLEDOWN if down else MOUSEEVENTF_MIDDLEUP
    return MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP


def instant_move(x: int, y: int) -> None:
    if user32 is None:
        return
    user32.SetCursorPos(int(x), int(y))
    time.sleep(PRE_CLICK_SETTLE_SEC)


def tween_move(x: int, y: int, *, duration: float = TWEEN_MOVE_SEC) -> None:
    if user32 is None:
        return

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    current = POINT()
    user32.GetCursorPos(ctypes.byref(current))

    start_x = int(current.x)
    start_y = int(current.y)
    target_x = int(x)
    target_y = int(y)

    steps = max(1, TWEEN_MOVE_STEPS)
    sleep_for = max(0.001, duration / steps)
    for step in range(1, steps + 1):
        t = step / steps
        # Ease out slightly so Roblox sees movement without making replay feel slow.
        eased = 1 - (1 - t) * (1 - t)
        nx = round(start_x + (target_x - start_x) * eased)
        ny = round(start_y + (target_y - start_y) * eased)
        user32.SetCursorPos(nx, ny)
        time.sleep(sleep_for)

    user32.SetCursorPos(target_x, target_y)
    time.sleep(PRE_CLICK_SETTLE_SEC)


def click_at(x: int, y: int, button: str = "left") -> None:
    tween_move(x, y)
    print(f"[macro input] click {button} at {int(x)},{int(y)}")
    mouse_button(button, down=True)
    time.sleep(CLICK_HOLD_SEC)
    mouse_button(button, down=False)
    time.sleep(PRE_CLICK_SETTLE_SEC)


def click_hold_at(
    x: int,
    y: int,
    seconds: float,
    *,
    button: str = "left",
    cancel: threading.Event | None = None,
) -> bool:
    """Move to (x, y), hold the mouse button down for `seconds`, then release.

    Used for the merchant dialogue press-and-hold (original held mouse-down ~3s).
    Returns False if cancelled mid-hold (button is always released).
    """
    if _cancelled(cancel):
        return False
    instant_move(int(x), int(y))
    print(f"[macro input] hold {button} at {int(x)},{int(y)} for {float(seconds):.1f}s")
    mouse_button(button, down=True)
    try:
        ok = _sleep_sec(max(0.0, float(seconds)), cancel)
    finally:
        mouse_button(button, down=False)
        time.sleep(PRE_CLICK_SETTLE_SEC)
    return ok


def github_original_click_at(
    x: int,
    y: int,
    *,
    click: int = 1,
    pre_sleep_sec: float = 0.335,
    cancel: threading.Event | None = None,
) -> bool:
    """Returns False if cancelled before the click completes."""
    if _cancelled(cancel):
        return False
    delay = max(0.0, float(pre_sleep_sec))
    print(f"[macro input] github original click left at {int(x)},{int(y)} x{int(click)}")
    if delay and not _sleep_sec(delay, cancel):
        return False
    if _cancelled(cancel):
        return False
    autoit.mouse_click("left", int(x), int(y), int(click), speed=3)
    return True


def click_at_settled(
    x: int,
    y: int,
    *,
    click: int = 1,
    pre_sleep_sec: float = 0.1,
    cancel: threading.Event | None = None,
) -> bool:
    """Jump to (x, y), settle, then click in place — no click while moving there."""
    if _cancelled(cancel):
        return False
    instant_move(int(x), int(y))
    delay = max(PRE_CLICK_SETTLE_SEC, float(pre_sleep_sec))
    if not _sleep_sec(delay, cancel):
        return False
    for i in range(max(1, int(click))):
        if _cancelled(cancel):
            return False
        mouse_button("left", down=True)
        if not _sleep_sec(CLICK_HOLD_SEC, cancel):
            return False
        mouse_button("left", down=False)
        if i + 1 < click and not _sleep_sec(0.04, cancel):
            return False
    return True


def mouse_button(button: str, down: bool) -> None:
    if user32 is None:
        return
    flags = _button_flags(button, down)
    try:
        # Roblox tends to accept this older event path more consistently than
        # zero-delta SendInput mouse packets from automation.
        user32.mouse_event(flags, 0, 0, 0, 0)
        return
    except Exception:
        pass

    inp = INPUT(type=INPUT_MOUSE, union=INPUT_UNION(mi=MOUSEINPUT(0, 0, 0, flags, 0, None)))
    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if sent != 1:
        print(f"[macro input] SendInput failed for {button} {'down' if down else 'up'}")


def focus_roblox_window() -> bool:
    """Bring Roblox to the foreground before replaying inputs."""
    try:
        from macro_hotkeys import MacroHotkeyManager

        mgr = MacroHotkeyManager(lambda: (None, None), lambda: None, lambda: None)
        return mgr.focus_roblox()
    except Exception as error:
        print(f"[roblox focus] failed: {error}")
        return False


def replay_key_action(key: str, down: bool) -> bool:
    """Send a key for path replay (SendInput + scan code first, then keyboard lib)."""
    name = (key or "").strip().lower()
    if not name:
        return False

    if user32 is not None:
        vk = _vk_for_key(name)
        if vk:
            scan = int(user32.MapVirtualKeyW(vk, 0)) & 0xFF
            flags = KEYEVENTF_KEYUP if not down else 0
            inp = INPUT(
                type=INPUT_KEYBOARD,
                union=INPUT_UNION(ki=KEYBDINPUT(vk, scan, flags, 0, None)),
            )
            if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1:
                time.sleep(REPLAY_KEY_SETTLE_SEC)
                return True

    try:
        import keyboard

        if down:
            keyboard.press(name)
        else:
            keyboard.release(name)
        time.sleep(REPLAY_KEY_SETTLE_SEC)
        return True
    except Exception as error:
        print(f"[macro replay] key {name!r} {'down' if down else 'up'} failed: {error}")
        return False


def key_action(key: str, down: bool) -> None:
    replay_key_action(key, down)


def filter_recorder_hotkeys(
    events: list[dict],
    *,
    extra: set[str] | None = None,
) -> list[dict]:
    blocked = {
        "f4",
        "f5",
        "f9",
        "f10",
        "q",
        "esc",
        "escape",
    }
    if extra:
        blocked |= {str(k).lower() for k in extra}
    out: list[dict] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if str(event.get("type", "")).startswith("key_"):
            key = str(event.get("key") or "").lower()
            if key in blocked:
                continue
        out.append(event)
    return out


def collapse_key_events(events: list[dict]) -> list[dict]:
    """Turn repeated key_down while held into one down/up pair; keep real hold duration."""
    out: list[dict] = []
    held: dict[str, dict] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        etype = event.get("type")
        key = str(event.get("key") or "").lower()
        if not key or not str(etype).startswith("key_"):
            out.append(event)
            continue
        if etype == "key_down":
            if key in held:
                continue
            held[key] = dict(event)
            out.append(held[key])
        elif etype == "key_up":
            if key not in held:
                continue
            up_event = dict(event)
            if float(up_event.get("t") or 0) < float(held[key].get("t") or 0):
                up_event["t"] = held[key].get("t")
            held.pop(key)
            out.append(up_event)
    for key, down_event in held.items():
        out.append(
            {
                "type": "key_up",
                "key": key,
                "t": float(down_event.get("t") or 0) + 0.05,
                "x": 0,
                "y": 0,
            }
        )
    out.sort(key=lambda item: float(item.get("t") or 0))
    return out


def normalize_events(events: list[dict]) -> list[dict]:
    last_x = last_y = 0
    out: list[dict] = []
    for raw in events:
        event = dict(raw)
        x = int(event.get("x") or 0)
        y = int(event.get("y") or 0)
        if x == 0 and y == 0 and (last_x or last_y):
            x, y = last_x, last_y
        elif x or y:
            last_x, last_y = x, y
        event["x"] = x
        event["y"] = y
        out.append(event)
    return out


class MacroRecorder:
    def __init__(self) -> None:
        self._events: list[dict] = []
        self._start = 0.0
        self._recording = False
        self._clicks_only = False
        self._keys_only = False
        self._suppress_keys: set[str] = set()
        self._lock = threading.Lock()
        self._mouse_hook = None
        self._key_hook = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def click_count(self) -> int:
        with self._lock:
            return sum(1 for event in self._events if event.get("type") == "mouse_down")

    def _timestamp(self) -> float:
        return time.perf_counter() - self._start

    def _append(self, event: dict) -> None:
        with self._lock:
            if self._recording:
                self._events.append(event)
                if event.get("type") == "mouse_down":
                    clicks = sum(1 for item in self._events if item.get("type") == "mouse_down")
                    if clicks <= 5 or clicks % 10 == 0:
                        print(
                            f"[macro recorder] captured click #{clicks} at "
                            f"{event.get('x')},{event.get('y')}"
                        )

    def start(
        self,
        *,
        clicks_only: bool = False,
        keys_only: bool = False,
        suppress_keys: set[str] | None = None,
    ) -> None:
        import keyboard
        import mouse

        self.stop()
        self._events = []
        self._clicks_only = clicks_only
        self._keys_only = keys_only
        self._suppress_keys = {str(k).lower() for k in (suppress_keys or set())}
        self._start = time.perf_counter()
        self._recording = True
        print(
            f"[macro recorder] started clicks_only={clicks_only} keys_only={keys_only}"
        )

        def on_mouse(event) -> None:
            if not self._recording or self._keys_only:
                return
            if isinstance(event, mouse.ButtonEvent):
                x, y = mouse.get_position()
                btn = str(event.button or "left").replace("Button.", "")
                etype = "mouse_down" if event.event_type == mouse.DOWN else "mouse_up"
                self._append(
                    {
                        "type": etype,
                        "x": int(x),
                        "y": int(y),
                        "button": btn,
                        "key": "",
                        "delta": 0,
                        "t": self._timestamp(),
                    }
                )
            elif not self._clicks_only and isinstance(event, mouse.MoveEvent):
                self._append(
                    {
                        "type": "mouse_move",
                        "x": int(event.x),
                        "y": int(event.y),
                        "button": "",
                        "key": "",
                        "delta": 0,
                        "t": self._timestamp(),
                    }
                )

        def on_key(event) -> None:
            if not self._recording or self._clicks_only:
                return
            name = (event.name or "").lower()
            if not name or name in self._suppress_keys:
                return
            etype = "key_down" if event.event_type == keyboard.KEY_DOWN else "key_up"
            self._append({"type": etype, "key": name, "t": self._timestamp()})

        if not keys_only:
            self._mouse_hook = mouse.hook(on_mouse)
        if not clicks_only:
            self._key_hook = keyboard.hook(on_key)

    def stop(self) -> list[dict]:
        import keyboard
        import mouse

        self._recording = False
        if self._key_hook is not None:
            keyboard.unhook(self._key_hook)
            self._key_hook = None
        if self._mouse_hook is not None:
            mouse.unhook(self._mouse_hook)
            self._mouse_hook = None
        with self._lock:
            clicks = sum(1 for event in self._events if event.get("type") == "mouse_down")
            print(f"[macro recorder] stopped events={len(self._events)} clicks={clicks}")
            return deepcopy(self._events)

    def build_payload(self, *, include_screen: bool = False) -> dict:
        w, h = _screen_size()
        payload: dict = {"events": normalize_events(self._events)}
        if include_screen:
            payload["created"] = time.time()
            payload["screen"] = {"w": w, "h": h}
        return payload


class MacroReplayer:
    def __init__(self) -> None:
        self._cancel = threading.Event()
        self._external_cancel: threading.Event | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def set_cancel_event(self, event: threading.Event | None) -> None:
        self._external_cancel = event

    def _should_cancel(self) -> bool:
        if self._cancel.is_set():
            return True
        return _cancelled(self._external_cancel)

    def cancel(self) -> None:
        self._cancel.set()

    def _replay_click_sequence(self, events: list[dict]) -> str:
        clicks = [event for event in events if event.get("type") == "mouse_down"]
        if not clicks:
            return "Error: recording has no clicks"

        print(f"[macro replay] potion click replay starting clicks={len(clicks)}")
        prev_t = 0.0
        cancel = self._external_cancel
        for index, event in enumerate(clicks, start=1):
            if self._should_cancel():
                return "Cancelled"

            t = float(event.get("t") or 0)
            gap = max(0.0, min(t - prev_t, POTION_MAX_CLICK_GAP_SEC))
            if gap > 0 and not _sleep_sec(gap, self._external_cancel):
                return "Cancelled"
            prev_t = t

            x = int(event.get("x") or 0)
            y = int(event.get("y") or 0)
            button = str(event.get("button") or "left")
            if x <= 0 and y <= 0:
                print(f"[macro replay] skipped click #{index}: invalid position {x},{y}")
                continue

            print(f"[macro replay] click #{index}/{len(clicks)} at {x},{y}")
            click_at(x, y, button)

        return "Replay Finished"

    def replay(
        self,
        payload: dict,
        *,
        focus_roblox: bool = True,
        playback_multiplier: float = 1.0,
        reset_before: bool = True,
    ) -> str:
        raw = filter_recorder_hotkeys(list(payload.get("events") or []))
        events = collapse_key_events(normalize_events(raw))
        if not events:
            return "Error: recording is empty"

        multiplier = max(0.25, min(float(playback_multiplier or 1.0), 4.0))

        self._cancel.clear()
        self._running = True
        held: set[str] = set()
        cancel = self._external_cancel
        try:
            if self._should_cancel():
                return "Cancelled"

            if focus_roblox:
                if not focus_roblox_window():
                    print("[macro replay] warning: could not focus Roblox — click the game window")
                if not _sleep_sec(0.2, cancel):
                    return "Cancelled"

            if reset_before:
                if not release_stuck_inputs(reason="before replay", cancel=cancel):
                    return "Cancelled"

            event_types = {event.get("type") for event in events}
            if payload.get("clicks_only") or event_types <= {"mouse_down", "mouse_up"}:
                return self._replay_click_sequence(events)

            start = time.perf_counter()
            sent = 0
            for event in events:
                if self._should_cancel():
                    for key in list(held):
                        replay_key_action(key, False)
                    return "Cancelled"

                t = float(event.get("t") or 0)
                target = start + (t / multiplier)
                if not _sleep_until(target, cancel):
                    for key in list(held):
                        replay_key_action(key, False)
                    return "Cancelled"

                etype = event.get("type")
                if etype == "mouse_move":
                    continue

                if etype == "mouse_down":
                    tween_move(int(event.get("x") or 0), int(event.get("y") or 0))
                    mouse_button(str(event.get("button") or "left"), down=True)
                    if not _sleep_sec(CLICK_HOLD_SEC, cancel):
                        return "Cancelled"
                elif etype == "mouse_up":
                    tween_move(int(event.get("x") or 0), int(event.get("y") or 0))
                    mouse_button(str(event.get("button") or "left"), down=False)
                elif etype == "key_down":
                    key = str(event.get("key") or "").lower()
                    if key and key not in held:
                        if replay_key_action(key, True):
                            held.add(key)
                            sent += 1
                elif etype == "key_up":
                    key = str(event.get("key") or "").lower()
                    if key in held:
                        replay_key_action(key, False)
                        held.discard(key)
                        sent += 1

            if self._should_cancel():
                return "Cancelled"

            release_stuck_inputs(reason="after replay", cancel=cancel)

            if sent == 0:
                return "Error: no keys were sent (check recording or focus Roblox)"
            return "Replay Finished"
        finally:
            for key in list(held):
                replay_key_action(key, False)
            if self._should_cancel():
                release_stuck_inputs(cancel=cancel)
            self._running = False
            self._cancel.clear()


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4 if len(str(payload)) < 50000 else None), encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def potion_filename(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("Potion name is required")
    return cleaned if cleaned.lower().endswith(".json") else f"{cleaned}.json"
