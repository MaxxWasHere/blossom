"""Auto Eden detection (faithful port of the original Noteab macro).

The original macro (xVapure/Noteab-Macro, ``biome_tracker/mixin_actions.py``)
implements "auto eden" as a background OCR loop that watches the in-game chat for
the server announcement ``"devourer of the void, eden has appeared"`` and, when it
sees it (ignoring players who spoof the line), pings Discord with a screenshot.

This module reproduces that behaviour on Blossom's input/OCR layer:

* OCR runs against the calibrated chat regions (``chat_box_ocr_pos`` etc.).
* The same fuzzy target + 0.8 threshold + player-tag spoof guard is used.
* The same 40 minute cooldown prevents duplicate pings.

The loop is fully exception-guarded so it can never crash the macro, and it is
gated behind the existing ``auto_eden_contract`` toggle (off by default).
"""

from __future__ import annotations

import difflib
import threading
import time
from typing import Any, Callable

import blossom_ocr
from macro_engine import _sleep_sec, github_original_click_at

ConfigProvider = Callable[[], dict]
ConfigEnabled = Callable[[dict, str], bool]
CanRunCb = Callable[[], bool]
FocusRobloxCb = Callable[[], Any]
SendAlertCb = Callable[[str | None], Any]

# Enable toggle: the existing Blossom flag for this feature.
AUTO_EDEN_CONFIG_KEY = "auto_eden_contract"

# Original macro constants (kept verbatim so behaviour matches).
EDEN_FUZZY_TARGET = "devourer of the void, eden has appeared"
EDEN_FUZZY_THRESHOLD = 0.8
EDEN_OCR_COOLDOWN_SEC = 2400  # 40 minutes
DEFAULT_CHECK_INTERVAL_MIN = 5.0
MIN_CHECK_INTERVAL_SEC = 60.0
TAG_LOOKBACK = 100

# Player rank tags: if the matched text is preceded by one of these, it's a real
# player typing the line (trolling), not the server announcement.
PLAYER_TAGS: tuple[str, ...] = (
    "[fan]", "[vip]", "[vip+]", "[donator]", "[contributor]",
    "[cm]", "[dev]", "[moderator]", "[admin]", "[owner]",
    "[og]", "[tester]", "[youtuber]", "[rolls]",
)

# Module-level cooldown so repeated detections within 40 min don't re-ping even
# across loop restarts within the same process.
_last_eden_found_time = 0.0
_cooldown_lock = threading.Lock()


def auto_eden_enabled(config: dict, *, config_enabled: ConfigEnabled) -> bool:
    """True when Auto Eden detection is toggled on (and not idling)."""
    if config_enabled(config, "enable_idle_mode"):
        return False
    return config_enabled(config, AUTO_EDEN_CONFIG_KEY)


def auto_eden_interval_seconds(config: dict) -> float:
    """Minimum seconds between OCR checks (original default 5 min, floor 60s)."""
    try:
        minutes = float(config.get("eden_check_interval", DEFAULT_CHECK_INTERVAL_MIN))
    except (TypeError, ValueError):
        minutes = DEFAULT_CHECK_INTERVAL_MIN
    return max(MIN_CHECK_INTERVAL_SEC, minutes * 60.0)


def _region(config: dict, key: str) -> tuple[int, int, int, int] | None:
    raw = config.get(key)
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    try:
        x, y, w, h = (int(round(float(v))) for v in raw[:4])
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return (x, y, w, h)


def _point(config: dict, key: str, default: tuple[int, int] | None = None) -> tuple[int, int] | None:
    raw = config.get(key)
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return default
    try:
        x, y = int(round(float(raw[0]))), int(round(float(raw[1])))
    except (TypeError, ValueError):
        return default
    if x <= 0 and y <= 0:
        return default
    return (x, y)


def auto_eden_ready(config: dict) -> tuple[bool, list[str]]:
    """Confirm the calibrations the OCR check needs are present."""
    missing: list[str] = []
    if _region(config, "chat_box_ocr_pos") is None:
        missing.append("chat_box_ocr_pos")
    if _point(config, "chat_hover_pos") is None:
        missing.append("chat_hover_pos")
    if _point(config, "chat_close_button") is None:
        missing.append("chat_close_button")
    return (not missing, missing)


def _is_player_message(text: str, match_pos: int) -> bool:
    start = max(0, match_pos - TAG_LOOKBACK)
    prefix = text[start:match_pos]
    return any(tag in prefix for tag in PLAYER_TAGS)


def _text_contains_eden(text: str) -> bool:
    """Port of the original exact + fuzzy sliding-window Eden detection."""
    if not text:
        return False
    exact_pos = text.find(EDEN_FUZZY_TARGET)
    if exact_pos != -1:
        if not _is_player_message(text, exact_pos):
            return True
        print("[AutoEden] exact 'Eden' line detected but it's a player trolling — ignoring")
        return False

    win_len = len(EDEN_FUZZY_TARGET)
    if win_len > len(text):
        return False
    for i in range(len(text) - win_len + 1):
        window = text[i:i + win_len]
        ratio = difflib.SequenceMatcher(None, EDEN_FUZZY_TARGET, window).ratio()
        if ratio >= EDEN_FUZZY_THRESHOLD:
            if not _is_player_message(text, i):
                return True
            print("[AutoEden] fuzzy 'Eden' line detected but it's a player trolling — ignoring")
            return False
    return False


def _ensure_chat_open(config: dict, log_prefix: str) -> bool:
    """Hover the chat and confirm a chat tab is visible, opening it if needed."""
    try:
        import autoit
        import pyautogui
    except Exception:  # noqa: BLE001 - input layer missing
        return False

    chat_hover = _point(config, "chat_hover_pos")
    chat_close = _point(config, "chat_close_button")
    chat_tab_region = _region(config, "chat_tab_ocr_pos")
    if chat_hover is None:
        return False

    try:
        size = pyautogui.size()
        autoit.mouse_move(size.width // 2, size.height // 2, speed=3)
        time.sleep(0.5)
        autoit.mouse_move(chat_hover[0], chat_hover[1], speed=3)
        time.sleep(0.5)
    except Exception as error:  # noqa: BLE001
        print(f"{log_prefix} chat hover failed: {error}")
        return False

    def _tab_visible(candidates: tuple[str, ...]) -> bool:
        if chat_tab_region is None:
            return True  # no tab calibration -> assume open, OCR the box directly
        for attempt in range(2):
            tab_text = blossom_ocr.ocr_region(chat_tab_region, psm=7).lower()
            if blossom_ocr.fuzzy_match_any(tab_text, candidates, threshold=0.8):
                return True
            if attempt == 0:
                time.sleep(0.35)
        return False

    if _tab_visible(("here", "general", "server message")):
        return True

    # Toggle chat open and re-check.
    if chat_close is not None:
        try:
            autoit.mouse_click("left", chat_close[0], chat_close[1], 1, speed=3)
            time.sleep(0.7)
            autoit.mouse_move(chat_hover[0], chat_hover[1], speed=3)
            time.sleep(0.5)
        except Exception:  # noqa: BLE001
            pass
    return _tab_visible(("general", "server message"))


def run_auto_eden_check(
    config: dict,
    *,
    focus_roblox_cb: FocusRobloxCb | None = None,
    send_eden_alert_cb: SendAlertCb | None = None,
    log_prefix: str = "[AutoEden]",
) -> str:
    """One OCR detection cycle. Returns a short status string.

    Mirrors the original ``_scheduled_eden_ocr_check``: focus Roblox, open chat,
    OCR the chat box, fuzzy-detect the Eden announcement (ignoring spoofers),
    honour the 40 minute cooldown, then fire the alert callback.
    """
    global _last_eden_found_time

    chat_box_region = _region(config, "chat_box_ocr_pos")
    if chat_box_region is None:
        return "Skipped: chat_box_ocr_pos not calibrated"
    if not blossom_ocr.tesseract_available():
        return "Skipped: OCR unavailable"

    if focus_roblox_cb is not None:
        try:
            focus_roblox_cb()
            _sleep_sec(0.15)
        except Exception:  # noqa: BLE001
            pass

    try:
        if not _ensure_chat_open(config, log_prefix):
            return "Skipped: could not confirm chat is open"

        text = blossom_ocr.ocr_region(chat_box_region, psm=6).lower()
        if not text:
            return "No chat text"

        if not _text_contains_eden(text):
            return "No Eden"

        now = time.monotonic()
        with _cooldown_lock:
            if (now - _last_eden_found_time) < EDEN_OCR_COOLDOWN_SEC:
                return "Eden detected (cooldown active)"
            _last_eden_found_time = now

        print(f"{log_prefix} Eden spawn detected!")

        screenshot_path = _capture_chat_screenshot(chat_box_region, log_prefix)
        if send_eden_alert_cb is not None:
            try:
                send_eden_alert_cb(screenshot_path)
            except Exception as error:  # noqa: BLE001
                print(f"{log_prefix} alert callback failed: {error}")
        return "OK: Eden detected"
    finally:
        # Always try to close chat again so it doesn't sit open over the game.
        chat_close = _point(config, "chat_close_button")
        if chat_close is not None:
            try:
                github_original_click_at(chat_close[0], chat_close[1], click=1)
            except Exception:  # noqa: BLE001
                pass


def _capture_chat_screenshot(region: tuple[int, int, int, int], log_prefix: str) -> str | None:
    try:
        import pyautogui

        from blossom_dirs import ensure_app_data_dirs  # local import; optional
    except Exception:  # noqa: BLE001
        return None
    try:
        from pathlib import Path

        ensure_app_data_dirs()
        from blossom_dirs import APP_DATA_DIR

        shots = Path(APP_DATA_DIR) / "images"
        shots.mkdir(parents=True, exist_ok=True)
        path = shots / f"eden_ocr_{int(time.time())}.png"
        img = pyautogui.screenshot(region=region)
        img.save(str(path))
        return str(path)
    except Exception as error:  # noqa: BLE001
        print(f"{log_prefix} chat screenshot failed: {error}")
        return None


def run_auto_eden_loop(
    *,
    stop_event: threading.Event,
    can_run_cb: CanRunCb,
    config_provider: ConfigProvider,
    config_enabled: ConfigEnabled,
    focus_roblox_cb: FocusRobloxCb | None = None,
    send_eden_alert_cb: SendAlertCb | None = None,
    log_prefix: str = "[AutoEden]",
    print_start_stop: bool = True,
) -> None:
    """Background worker loop (port of ``eden_ocr_check_loop``).

    Polls on the configured interval, runs an OCR check when nothing higher
    priority is busy, and pings Discord on detection. Fully exception-guarded.
    """
    if print_start_stop:
        print(f"{log_prefix} worker started")
    last_check = 0.0
    try:
        while not stop_event.is_set():
            try:
                config = config_provider()
                if not auto_eden_enabled(config, config_enabled=config_enabled):
                    stop_event.wait(2.0)
                    continue
                if not can_run_cb():
                    stop_event.wait(2.0)
                    continue

                interval = auto_eden_interval_seconds(config)
                now = time.monotonic()
                if last_check and (now - last_check) < interval:
                    stop_event.wait(2.0)
                    continue
                last_check = now

                result = run_auto_eden_check(
                    config,
                    focus_roblox_cb=focus_roblox_cb,
                    send_eden_alert_cb=send_eden_alert_cb,
                    log_prefix=log_prefix,
                )
                if result and not result.startswith(("No ", "Skipped")):
                    print(f"{log_prefix} {result}")
            except Exception as error:  # noqa: BLE001 - never let the loop die
                print(f"{log_prefix} loop error: {error}")
            stop_event.wait(1.0)
    finally:
        if print_start_stop:
            print(f"{log_prefix} worker stopped")
