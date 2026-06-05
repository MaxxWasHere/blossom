"""Global macro hotkeys (configurable) and Roblox window focus."""

from __future__ import annotations

import sys
import threading
import time
from typing import Callable

if sys.platform == "win32":
    import ctypes

    user32 = ctypes.windll.user32
    SW_RESTORE = 9
else:
    user32 = None

DEFAULT_MACRO_START_KEY = "f1"
DEFAULT_MACRO_STOP_KEY = "f2"
HOTKEY_UNBOUND = ""
UNBOUND_ALIASES = frozenset({"", "none", "off", "unbound", "disabled", "no", "nobind", "no bind"})

# Browser KeyboardEvent.key names -> keyboard library hotkey names
_KEY_ALIASES = {
    "arrowup": "up",
    "arrowdown": "down",
    "arrowleft": "left",
    "arrowright": "right",
    " ": "space",
    "spacebar": "space",
    "escape": "esc",
    "return": "enter",
    "del": "delete",
    "pageup": "page up",
    "pagedown": "page down",
    "meta": "windows",
    "os": "windows",
    "control": "ctrl",
    "command": "windows",
}


def is_unbound_hotkey(value: object) -> bool:
    return str(value or "").strip().lower() in UNBOUND_ALIASES


def _canonical_key_part(part: str) -> str:
    token = (part or "").strip().lower()
    if not token:
        raise ValueError("Invalid hotkey")
    return _KEY_ALIASES.get(token, token)


def normalize_hotkey(value: str) -> str:
    cleaned = (value or "").strip().lower()
    if not cleaned or is_unbound_hotkey(cleaned):
        raise ValueError("Invalid hotkey")
    parts = [_canonical_key_part(part) for part in cleaned.split("+") if part.strip()]
    if not parts:
        raise ValueError("Invalid hotkey")
    combined = "+".join(parts)
    if sys.platform == "win32":
        import keyboard

        keyboard.parse_hotkey(combined)
    return combined


def resolve_hotkey_setting(config: dict, key: str, default: str) -> str | None:
    """None = explicitly unbound; default used only when the config key is missing."""
    if key not in config:
        return default
    raw = config.get(key)
    if is_unbound_hotkey(raw):
        return None
    cleaned = str(raw or "").strip().lower()
    return cleaned if cleaned else None


class MacroHotkeyManager:
    def __init__(
        self,
        *,
        get_hotkeys: Callable[[], tuple[str, str]],
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
    ) -> None:
        self._get_hotkeys = get_hotkeys
        self._on_start = on_start
        self._on_stop = on_stop
        self._lock = threading.Lock()
        self._hooks: list = []
        self._bound_keys: list[str] = []

    def register(self) -> None:
        import keyboard

        self.unregister()
        start_key, stop_key = self._get_hotkeys()
        hooks: list = []
        bound_keys: list[str] = []
        with self._lock:
            for label, key, handler in (
                ("start", start_key, self._on_start),
                ("stop", stop_key, self._on_stop),
            ):
                if not key:
                    continue
                try:
                    hooks.append(keyboard.add_hotkey(key, handler, suppress=False))
                    bound_keys.append(key)
                except Exception as exc:
                    print(f"[macro hotkeys] could not bind {label}={key!r}: {exc}")
            self._hooks = hooks
            self._bound_keys = bound_keys
        print(
            f"[macro hotkeys] active: start={start_key or 'unbound'}, stop={stop_key or 'unbound'}"
        )

    def reload(self) -> None:
        self.register()

    def unregister(self) -> None:
        import keyboard

        with self._lock:
            hooks = list(self._hooks)
            keys = list(self._bound_keys)
            self._hooks = []
            self._bound_keys = []

        for hook in hooks:
            try:
                keyboard.remove_hotkey(hook)
            except Exception:
                pass
        for key in keys:
            try:
                keyboard.remove_hotkey(key)
            except Exception:
                pass

    def _is_roblox_title(self, title: str) -> bool:
        lower = (title or "").strip().lower()
        return bool(lower) and "roblox" in lower and "macro" not in lower and "coteab" not in lower and "blossom" not in lower

    def _foreground_title(self) -> str:
        if user32 is None:
            return ""

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""

        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""

        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        return title.value.strip()

    def _force_foreground(self, hwnd: int) -> bool:
        if user32 is None or not hwnd:
            return False

        foreground_thread = 0
        target_thread = 0
        current_thread = 0
        try:
            foreground = user32.GetForegroundWindow()
            current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            target_thread = user32.GetWindowThreadProcessId(hwnd, None)
            foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0

            if foreground_thread:
                user32.AttachThreadInput(current_thread, foreground_thread, True)
            if target_thread:
                user32.AttachThreadInput(current_thread, target_thread, True)

            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
            user32.SetFocus(hwnd)
            time.sleep(0.18)
            return self._is_roblox_title(self._foreground_title())
        except Exception as exc:
            print(f"[roblox focus] force foreground failed: {exc}")
            return False
        finally:
            try:
                if foreground_thread:
                    user32.AttachThreadInput(current_thread, foreground_thread, False)
                if target_thread:
                    user32.AttachThreadInput(current_thread, target_thread, False)
            except Exception:
                pass

    def focus_roblox(self) -> bool:
        if self._is_roblox_title(self._foreground_title()):
            print("[roblox focus] already focused")
            return True

        try:
            import pygetwindow as gw
        except ImportError:
            print("[roblox focus] pygetwindow missing")
            return False

        matches: list = []
        try:
            for window in gw.getAllWindows():
                title = (window.title or "").strip()
                if self._is_roblox_title(title):
                    matches.append(window)
        except Exception:
            print("[roblox focus] could not scan windows")
            return False

        if not matches:
            print("[roblox focus] Roblox window not found")
            return False

        target = matches[0]
        title = (target.title or "Roblox").strip()
        print(f"[roblox focus] focusing {title!r}")
        try:
            if target.isMinimized:
                target.restore()
        except Exception:
            pass

        hwnd = int(getattr(target, "_hWnd", 0) or 0)
        if self._force_foreground(hwnd):
            print("[roblox focus] focused via Win32")
            return True

        try:
            target.activate()
            time.sleep(0.18)
            if self._is_roblox_title(self._foreground_title()):
                print("[roblox focus] focused via pygetwindow")
                return True
        except Exception as exc:
            print(f"[roblox focus] pygetwindow activate failed: {exc}")

        print(f"[roblox focus] failed, foreground={self._foreground_title()!r}")
        return False
