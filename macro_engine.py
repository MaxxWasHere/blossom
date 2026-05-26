"""Record and replay mouse/keyboard macros for potion crafting and obby paths."""

from __future__ import annotations

import json
import sys
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Callable

import autoit

DEBUG_LOG_PATH = Path(__file__).resolve().parent / "debug-f8c06d.log"
DEBUG_SESSION_ID = "f8c06d"


def _debug_log(location: str, message: str, data: dict, hypothesis_id: str) -> None:
    try:
        payload = {
            "sessionId": DEBUG_SESSION_ID,
            "runId": "initial",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass

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
    # region agent log
    _debug_log(
        "macro_engine.py:click_at",
        "dispatching calibrated click",
        {"x": int(x), "y": int(y), "button": button},
        "T3,T4",
    )
    # endregion
    tween_move(x, y)
    print(f"[macro input] click {button} at {int(x)},{int(y)}")
    mouse_button(button, down=True)
    time.sleep(CLICK_HOLD_SEC)
    mouse_button(button, down=False)
    time.sleep(PRE_CLICK_SETTLE_SEC)


def github_original_click_at(x: int, y: int, *, click: int = 1) -> None:
    # region agent log
    _debug_log(
        "macro_engine.py:github_original_click_at",
        "dispatching github original autoit click",
        {"x": int(x), "y": int(y), "click": int(click), "speed": 3, "pre_sleep_sec": 0.335},
        "G1,G2",
    )
    # endregion
    print(f"[macro input] github original click left at {int(x)},{int(y)} x{int(click)}")
    time.sleep(0.335)
    autoit.mouse_click("left", int(x), int(y), int(click), speed=3)


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


def key_action(key: str, down: bool) -> None:
    if user32 is None:
        return
    vk = _vk_for_key(key)
    if not vk:
        return
    flags = 0 if down else KEYEVENTF_KEYUP
    inp = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUT_UNION(ki=KEYBDINPUT(vk, 0, flags, 0, None)),
    )
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


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
                    # region agent log
                    _debug_log(
                        "macro_engine.py:MacroRecorder._append",
                        "mouse click captured by recorder hook",
                        {
                            "clicks": clicks,
                            "x": event.get("x"),
                            "y": event.get("y"),
                            "button": event.get("button"),
                            "clicks_only": self._clicks_only,
                        },
                        "H3",
                    )
                    # endregion
                    if clicks <= 5 or clicks % 10 == 0:
                        print(
                            f"[macro recorder] captured click #{clicks} at "
                            f"{event.get('x')},{event.get('y')}"
                        )

    def start(self, *, clicks_only: bool = False) -> None:
        import keyboard
        import mouse

        self.stop()
        self._events = []
        self._clicks_only = clicks_only
        self._start = time.perf_counter()
        self._recording = True
        print(f"[macro recorder] started clicks_only={clicks_only}")

        def on_mouse(event) -> None:
            if not self._recording:
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
            if not name:
                return
            etype = "key_down" if event.event_type == keyboard.KEY_DOWN else "key_up"
            self._append({"type": etype, "key": name, "t": self._timestamp()})

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
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def cancel(self) -> None:
        self._cancel.set()

    def _replay_click_sequence(self, events: list[dict]) -> str:
        clicks = [event for event in events if event.get("type") == "mouse_down"]
        if not clicks:
            return "Error: recording has no clicks"

        print(f"[macro replay] potion click replay starting clicks={len(clicks)}")
        prev_t = 0.0
        for index, event in enumerate(clicks, start=1):
            if self._cancel.is_set():
                return "Cancelled"

            t = float(event.get("t") or 0)
            gap = max(0.0, min(t - prev_t, POTION_MAX_CLICK_GAP_SEC))
            if gap > 0:
                time.sleep(gap)
            prev_t = t

            x = int(event.get("x") or 0)
            y = int(event.get("y") or 0)
            button = str(event.get("button") or "left")
            if x <= 0 and y <= 0:
                print(f"[macro replay] skipped click #{index}: invalid position {x},{y}")
                continue

            print(f"[macro replay] click #{index}/{len(clicks)} at {x},{y}")
            # region agent log
            _debug_log(
                "macro_engine.py:MacroReplayer._replay_click_sequence",
                "replay click about to send input",
                {
                    "index": index,
                    "total": len(clicks),
                    "x": x,
                    "y": y,
                    "button": button,
                    "gap": gap,
                },
                "H4",
            )
            # endregion
            click_at(x, y, button)

        return "Replay Finished"

    def replay(self, payload: dict) -> str:
        events = normalize_events(list(payload.get("events") or []))
        if not events:
            return "Error: recording is empty"

        self._cancel.clear()
        self._running = True
        try:
            event_types = {event.get("type") for event in events}
            if payload.get("clicks_only") or event_types <= {"mouse_down", "mouse_up"}:
                return self._replay_click_sequence(events)

            prev_t = 0.0
            for event in events:
                if self._cancel.is_set():
                    return "Cancelled"

                t = float(event.get("t") or 0)
                gap = max(0.0, min(t - prev_t, MAX_EVENT_GAP_SEC))
                if gap > 0:
                    time.sleep(gap)
                prev_t = t

                etype = event.get("type")
                if etype == "mouse_move":
                    continue

                if etype == "mouse_down":
                    tween_move(int(event.get("x") or 0), int(event.get("y") or 0))
                    mouse_button(str(event.get("button") or "left"), down=True)
                    time.sleep(CLICK_HOLD_SEC)
                elif etype == "mouse_up":
                    tween_move(int(event.get("x") or 0), int(event.get("y") or 0))
                    mouse_button(str(event.get("button") or "left"), down=False)
                elif etype == "key_down":
                    key_action(str(event.get("key") or ""), down=True)
                elif etype == "key_up":
                    key_action(str(event.get("key") or ""), down=False)

            return "Replay Finished"
        finally:
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
