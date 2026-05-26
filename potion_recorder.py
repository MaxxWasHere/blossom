"""Floating potion recorder overlay with F1/F2 hotkeys."""

from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

if sys.platform == "win32":
    import ctypes

    user32 = ctypes.windll.user32
    SW_RESTORE = 9
else:
    user32 = None


OVERLAY_WIDTH = 430
OVERLAY_HEIGHT = 272
RECORDER_WIDTH = 500
RECORDER_HEIGHT = 300
OVERLAY_MARGIN = 48
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


@dataclass
class PotionRecorderState:
    open: bool = False
    recording: bool = False
    click_count: int = 0
    elapsed: int = 0
    status: str = "Ready"
    name: str = ""


class PotionRecorderController:
    RECORDER_START_KEY = "f1"
    RECORDER_STOP_KEY = "f2"
    MAIN_START_KEY = "f1"
    MAIN_STOP_KEY = "f2"

    def __init__(
        self,
        *,
        on_start_recording: Callable[[], None],
        on_stop_save: Callable[[str], str | None],
        on_cancel_recording: Callable[[], None],
        on_main_start: Callable[[], None],
        on_main_stop: Callable[[], None],
    ) -> None:
        self._on_start_recording = on_start_recording
        self._on_stop_save = on_stop_save
        self._on_cancel_recording = on_cancel_recording
        self._on_main_start = on_main_start
        self._on_main_stop = on_main_stop
        self._lock = threading.Lock()
        self._state = PotionRecorderState()
        self._overlay_window = None
        self._main_hotkeys: list = []
        self._recorder_hotkeys: list = []
        self._timer_stop = threading.Event()
        self._timer_thread: threading.Thread | None = None
        self._recording_started_at = 0.0
        self._closing = False

    @property
    def is_open(self) -> bool:
        return self._state.open

    def get_state(self) -> dict:
        with self._lock:
            return {
                "open": self._state.open,
                "recording": self._state.recording,
                "click_count": self._state.click_count,
                "elapsed": self._state.elapsed,
                "status": self._state.status,
                "name": self._state.name,
                "overlay_visible": True,
            }

    def set_name(self, name: str) -> None:
        with self._lock:
            self._state.name = (name or "").strip()

    def set_click_count(self, count: int) -> None:
        with self._lock:
            self._state.click_count = count

    def _set_status(self, status: str) -> None:
        with self._lock:
            self._state.status = status

    def _set_recording(self, recording: bool) -> None:
        with self._lock:
            self._state.recording = recording
            if recording:
                self._state.elapsed = 0

    def attach_overlay_window(self, window) -> None:
        self._overlay_window = window

    def open(self) -> None:
        import keyboard

        self._closing = False
        with self._lock:
            self._state.open = True
            self._state.status = "Ready - F1 records, F2 stops and saves"
        self._suspend_main_hotkeys()
        self._recorder_hotkeys = [
            keyboard.add_hotkey(self.RECORDER_START_KEY, self._hotkey_start, suppress=False),
            keyboard.add_hotkey(self.RECORDER_STOP_KEY, self._hotkey_stop, suppress=False),
        ]
        print("[potion recorder] hotkeys active: F1=start, F2=stop/save")

    def shutdown(self) -> None:
        import keyboard

        if self._closing:
            return
        self._closing = True

        self._stop_timer()
        for hook in self._recorder_hotkeys:
            try:
                keyboard.remove_hotkey(hook)
            except KeyError:
                pass
        self._recorder_hotkeys = []
        self._restore_main_hotkeys()

        with self._lock:
            self._state.open = False
            self._state.recording = False

    def close(self, *, destroy_window: bool = True) -> None:
        overlay = self._overlay_window
        self.shutdown()
        self._overlay_window = None

        if destroy_window and overlay is not None:
            try:
                overlay.destroy()
            except Exception:
                pass

        with self._lock:
            self._state = PotionRecorderState()

        self._closing = False

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

    def _is_roblox_title(self, title: str) -> bool:
        lower = (title or "").strip().lower()
        return bool(lower) and "roblox" in lower and "macro" not in lower and "coteab" not in lower

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
            self._set_status("Recording — focus Roblox manually")
            print("[roblox focus] pygetwindow missing")
            return False

        matches: list = []
        try:
            for window in gw.getAllWindows():
                title = (window.title or "").strip()
                if self._is_roblox_title(title):
                    matches.append(window)
        except Exception:
            self._set_status("Could not scan windows — focus Roblox manually")
            print("[roblox focus] could not scan windows")
            return False

        if not matches:
            self._set_status("Roblox not found — focus it manually")
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
            self._set_status("Switched to Roblox")
            print("[roblox focus] focused via Win32")
            return True

        try:
            target.activate()
            time.sleep(0.18)
            if self._is_roblox_title(self._foreground_title()):
                self._set_status("Switched to Roblox")
                print("[roblox focus] focused via pygetwindow")
                return True
        except Exception as exc:
            print(f"[roblox focus] pygetwindow activate failed: {exc}")

        self._set_status("Could not focus Roblox — alt-tab manually")
        print(f"[roblox focus] failed, foreground={self._foreground_title()!r}")
        return False

    def is_roblox_or_overlay_focused(self) -> bool:
        if user32 is None:
            return True

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False

        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return False

        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        title_text = title.value.strip()
        lower = title_text.lower()
        if "potion recorder" in lower:
            return True
        return self._is_roblox_title(title_text)

    def start_recording(self) -> str | None:
        with self._lock:
            if self._state.recording:
                return None
        try:
            focused = self.focus_roblox()
            # region agent log
            _debug_log(
                "potion_recorder.py:start_recording",
                "potion recorder start path reached",
                {
                    "focused_roblox": focused,
                    "state_open": self._state.open,
                    "state_recording": self._state.recording,
                    "name": self._state.name,
                },
                "H3",
            )
            # endregion
            self._on_start_recording()
        except Exception as error:
            self._set_status(f"Record failed: {error}")
            return str(error)

        self._set_recording(True)
        self._recording_started_at = time.perf_counter()
        self._set_status("Recording - click in Roblox, then F2 or Stop & Save")
        print("[potion recorder] recording started")
        self._start_timer()
        return None

    def stop_and_save(self) -> str | None:
        with self._lock:
            name = (self._state.name or "").strip()
            was_recording = self._state.recording
            self._state.recording = False

        self._stop_timer()
        # region agent log
        _debug_log(
            "potion_recorder.py:stop_and_save",
            "potion recorder stop/save path reached",
            {
                "name": name,
                "was_recording": was_recording,
                "state_open": self._state.open,
            },
            "H5",
        )
        # endregion
        if was_recording:
            print(f"[potion recorder] stop/save requested for {name or '<missing name>'}")

        if not name:
            try:
                self._on_cancel_recording()
            except Exception as exc:
                print(f"[potion recorder] cancel after missing name failed: {exc}")
            self._set_status("Enter a potion name first")
            return "Enter a potion name first"

        try:
            error = self._on_stop_save(name)
        except Exception as exc:
            self._set_status(f"Save failed: {exc}")
            return str(exc)

        if error:
            self._set_status(error)
            return error

        saved_as = name if name.lower().endswith(".json") else f"{name}.json"
        self._set_status(f"Saved {saved_as}")
        with self._lock:
            self._state.click_count = 0
            self._state.elapsed = 0
        return None

    def _start_timer(self) -> None:
        self._stop_timer()
        self._timer_stop.clear()

        def run() -> None:
            while not self._timer_stop.wait(0.25):
                with self._lock:
                    if not self._state.recording:
                        continue
                    self._state.elapsed = int(time.perf_counter() - self._recording_started_at)

        self._timer_thread = threading.Thread(target=run, daemon=True)
        self._timer_thread.start()

    def _stop_timer(self) -> None:
        self._timer_stop.set()

    def _hotkey_start(self) -> None:
        if not self.is_open:
            return
        print("[potion recorder] F1 pressed")
        # region agent log
        _debug_log(
            "potion_recorder.py:_hotkey_start",
            "potion F1 hotkey reached backend",
            {
                "state_open": self._state.open,
                "state_recording": self._state.recording,
                "name": self._state.name,
            },
            "H3",
        )
        # endregion
        self.start_recording()

    def _hotkey_stop(self) -> None:
        if not self.is_open:
            return
        print("[potion recorder] F2 pressed")
        self.stop_and_save()

    def _suspend_main_hotkeys(self) -> None:
        import keyboard

        for hook in self._main_hotkeys:
            try:
                keyboard.remove_hotkey(hook)
            except KeyError:
                pass
        self._main_hotkeys = []

    def _restore_main_hotkeys(self) -> None:
        import keyboard

        self._suspend_main_hotkeys()
        self._main_hotkeys = [
            keyboard.add_hotkey(self.MAIN_START_KEY, self._on_main_start, suppress=False),
            keyboard.add_hotkey(self.MAIN_STOP_KEY, self._on_main_stop, suppress=False),
        ]

    def register_main_hotkeys(self) -> None:
        self._restore_main_hotkeys()
        # region agent log
        _debug_log(
            "potion_recorder.py:register_main_hotkeys",
            "main F1/F2 hotkeys registered",
            {"main_hotkey_count": len(self._main_hotkeys)},
            "H1",
        )
        # endregion

    def overlay_position(self) -> tuple[int, int]:
        if user32 is None:
            return 100, 100
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        x = max(OVERLAY_MARGIN, (screen_w - RECORDER_WIDTH) // 2)
        y = max(OVERLAY_MARGIN, (screen_h - RECORDER_HEIGHT) // 2)
        return x, y
