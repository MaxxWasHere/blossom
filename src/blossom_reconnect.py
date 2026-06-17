"""Private-server reconnect for Blossom (cross-PC, calibration-based).

Replaces the monolithic Coteab mixin_actions reconnect flow with a focused
state machine: terminate Roblox, launch PS deep links, click the calibrated
Start button, verify in-game via Roblox logs.
"""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlparse

import psutil

from blossom_biomes import get_latest_log_file
from macro_engine import click_at_settled, focus_roblox_window

ROBLOX_PROCESS_NAMES = frozenset(
    {
        "RobloxPlayerBeta.exe",
        "Windows10Universal.exe",
        "RobloxPlayerLauncher.exe",
        "RobloxCrashHandler.exe",
    }
)

_DISCONNECT_LINE = "[FLog::Network] Client:Disconnect"
_EQUIPPED_RE = re.compile(
    r'"state"\s*:\s*"Equipped\s+(.+?)"\s*,\s*"smallImage"', re.IGNORECASE
)

DEFAULT_PLACE_ID = "15532962292"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_START_WAIT_SEC = 600.0
DEFAULT_LAUNCH_WAIT_SEC = 180.0
DEFAULT_CLICK_INTERVAL_SEC = 4.0
DEFAULT_BACKOFF_BASE_SEC = 8.0


def _current_username() -> str:
    try:
        return str(psutil.Process().username() or "").strip().lower()
    except Exception:
        return ""


def roblox_processes_running() -> bool:
    user = _current_username()
    try:
        for proc in psutil.process_iter(["name", "username"]):
            name = str(proc.info.get("name") or "")
            if name not in ROBLOX_PROCESS_NAMES:
                continue
            proc_user = str(proc.info.get("username") or "").strip().lower()
            if user and proc_user and proc_user != user:
                continue
            return True
    except (psutil.Error, OSError):
        pass
    return False


def terminate_roblox_processes() -> int:
    """Kill Roblox client processes for the current Windows user. Returns count killed."""
    user = _current_username()
    killed = 0
    try:
        for proc in psutil.process_iter(["pid", "name", "username"]):
            name = str(proc.info.get("name") or "")
            if name not in ROBLOX_PROCESS_NAMES:
                continue
            proc_user = str(proc.info.get("username") or "").strip().lower()
            if user and proc_user and proc_user != user:
                continue
            try:
                proc.kill()
                proc.wait(timeout=3)
                killed += 1
                print(f"[reconnect] terminated {name} (pid {proc.info.get('pid')})")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass
    except (psutil.Error, OSError) as error:
        print(f"[reconnect] terminate failed: {error}")
    return killed


def build_reconnect_deep_links(link: str) -> list[str]:
    """Build ordered roblox:// launch candidates from a PS share or private link."""
    raw_link = str(link or "").strip()
    if not raw_link:
        return []

    try:
        parsed = urlparse(raw_link)
        query = parse_qs(parsed.query)
        query_ci = {str(k).strip().lower(): v for k, v in query.items()}
        path = parsed.path or ""
        is_roblox_protocol = parsed.scheme.lower() == "roblox"
        path_l = path.lower()
        raw_l = raw_link.lower()

        raw_place_match = re.search(r"placeID=(\d+)", raw_link, flags=re.IGNORECASE)
        raw_place_id = raw_place_match.group(1) if raw_place_match else ""
        place_match = re.search(r"/games/(\d+)", path, flags=re.IGNORECASE)
        place_id = place_match.group(1) if place_match else (raw_place_id or DEFAULT_PLACE_ID)

        link_code = ""
        source_type = ""
        if query_ci.get("privateserverlinkcode"):
            link_code = str(query_ci["privateserverlinkcode"][0]).strip()
            source_type = "private"
        elif query_ci.get("linkcode"):
            link_code = str(query_ci["linkcode"][0]).strip()
            source_type = "private"
        elif query_ci.get("code"):
            link_type = str(query_ci.get("type", [""])[0]).strip().lower()
            if link_type in ("", "server"):
                link_code = str(query_ci["code"][0]).strip()
                source_type = "share"

        if not link_code:
            for pattern in (
                r"privateServerLinkCode=([^&\s]+)",
                r"linkCode=([^&\s]+)",
                r"code=([^&\s]+)",
            ):
                match = re.search(pattern, raw_link, flags=re.IGNORECASE)
                if match:
                    link_code = str(match.group(1)).strip()
                    if "privateserverlinkcode" in pattern.lower() or "linkcode" in pattern.lower():
                        source_type = "private"
                    elif "navigation/share_links" in raw_l or path_l.startswith("/share"):
                        source_type = "share"
                    break

        if not link_code and ("navigation/share_links" in raw_l or path_l.startswith("/share")):
            source_type = "share"

        candidates: list[str] = []
        if is_roblox_protocol:
            candidates.append(raw_link)
        if not link_code:
            return candidates

        encoded = quote(link_code, safe="")
        share_link = f"roblox://navigation/share_links?code={encoded}&type=Server"
        private_link = f"roblox://placeID={place_id}&linkCode={encoded}"
        if source_type == "private":
            candidates.extend([private_link, share_link])
        else:
            candidates.extend([share_link, private_link])

        deduped: list[str] = []
        for item in candidates:
            if item not in deduped:
                deduped.append(item)
        return deduped
    except Exception as error:
        print(f"[reconnect] deep link parse failed: {error}")
        return []


def _coerce_point(raw: Any, fallback: tuple[int, int] = (0, 0)) -> tuple[int, int]:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return fallback
    try:
        return int(raw[0]), int(raw[1])
    except (TypeError, ValueError):
        return fallback


def is_in_game_from_log(old_log_file: str | None = None) -> bool:
    """True when Roblox logs show equipped aura (in-game RPC)."""
    log_file = get_latest_log_file()
    if not log_file or not os.path.exists(log_file):
        return False
    if old_log_file and log_file == old_log_file:
        return False
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read()
    except OSError:
        return False
    return bool(_EQUIPPED_RE.search(content))


class DisconnectLogWatcher:
    """Tail Roblox logs for Client:Disconnect lines."""

    def __init__(self) -> None:
        self._log_file: str | None = None
        self._position = 0
        self._last_disconnect_at = 0.0
        self._handled = False
        self._cooldown_sec = 30.0

    def reset_handled(self) -> None:
        self._handled = False

    def poll(self) -> bool:
        """Return True once per disconnect event (with cooldown)."""
        if self._handled:
            return False
        if time.time() - self._last_disconnect_at < self._cooldown_sec:
            return False

        log_file = get_latest_log_file()
        if not log_file or not os.path.exists(log_file):
            return False

        if log_file != self._log_file:
            self._log_file = log_file
            try:
                self._position = os.path.getsize(log_file)
            except OSError:
                self._position = 0
            return False

        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as handle:
                handle.seek(self._position)
                chunk = handle.read()
                self._position = handle.tell()
        except OSError:
            return False

        if _DISCONNECT_LINE in chunk:
            self._last_disconnect_at = time.time()
            self._handled = True
            print("[reconnect] disconnect detected in Roblox log")
            return True
        return False


class ReconnectManager:
    """Thread-safe PS reconnect orchestrator."""

    def __init__(
        self,
        *,
        status_cb: Callable[[str], None] | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self._lock = threading.Lock()
        self._reconnecting = False
        self._last_error = ""
        self._status_cb = status_cb
        self._max_attempts = max(1, int(max_attempts))
        self._worker: threading.Thread | None = None

    @property
    def reconnecting(self) -> bool:
        with self._lock:
            return self._reconnecting

    @property
    def last_error(self) -> str:
        with self._lock:
            return self._last_error

    def _set_status(self, message: str) -> None:
        print(f"[reconnect] {message}")
        if self._status_cb is not None:
            try:
                self._status_cb(message)
            except Exception:
                pass

    def request_reconnect(
        self,
        config: dict[str, Any],
        *,
        reason: str = "reconnect requested",
        on_complete: Callable[[bool], None] | None = None,
    ) -> bool:
        """Start reconnect in a background thread if not already running."""
        with self._lock:
            if self._reconnecting:
                return False
            self._reconnecting = True
            self._last_error = ""

        def _worker() -> None:
            ok = False
            try:
                ok = self._run_sync(config, reason=reason)
            finally:
                with self._lock:
                    self._reconnecting = False
                if on_complete is not None:
                    try:
                        on_complete(ok)
                    except Exception:
                        pass

        self._worker = threading.Thread(target=_worker, name="BlossomReconnect", daemon=True)
        self._worker.start()
        return True

    def _run_sync(self, config: dict[str, Any], *, reason: str) -> bool:
        if not bool(config.get("auto_reconnect", False)):
            self._set_status("auto_reconnect disabled — terminating Roblox only")
            terminate_roblox_processes()
            self._last_error = "auto_reconnect disabled"
            return False

        ps_link = str(config.get("private_server_link") or "").strip()
        deep_links = build_reconnect_deep_links(ps_link)
        if not deep_links:
            self._set_status("no valid private_server_link — cannot reconnect")
            terminate_roblox_processes()
            self._last_error = "missing private_server_link"
            return False

        start_btn = _coerce_point(config.get("reconnect_start_button"), (954, 876))
        if start_btn[0] <= 0 and start_btn[1] <= 0:
            self._set_status("reconnect_start_button not calibrated")
            terminate_roblox_processes()
            self._last_error = "missing reconnect_start_button"
            return False

        self._set_status(f"{reason} — starting reconnect")
        old_log_file = get_latest_log_file()

        for attempt in range(1, self._max_attempts + 1):
            self._set_status(f"attempt {attempt}/{self._max_attempts}: closing Roblox")
            terminate_roblox_processes()
            time.sleep(2.0)

            launched = False
            launch_candidates = list(deep_links)
            if ps_link.lower().startswith(("http://", "https://")) and ps_link not in launch_candidates:
                launch_candidates.append(ps_link)

            for deep_link in launch_candidates:
                try:
                    os.startfile(deep_link)
                    self._set_status(f"launched {deep_link[:64]}…")
                    launched = True
                    break
                except OSError as error:
                    print(f"[reconnect] launch failed: {error}")

            if not launched:
                self._last_error = "could not launch any deep link"
                backoff = DEFAULT_BACKOFF_BASE_SEC * attempt
                time.sleep(backoff)
                continue

            wait_start = time.monotonic()
            while time.monotonic() - wait_start < DEFAULT_LAUNCH_WAIT_SEC:
                if roblox_processes_running():
                    break
                time.sleep(2.0)

            if not roblox_processes_running():
                self._last_error = "Roblox did not open"
                time.sleep(DEFAULT_BACKOFF_BASE_SEC * attempt)
                continue

            self._set_status("Roblox open — clicking Start / reconnect")
            if self._click_until_in_game(start_btn, old_log_file=old_log_file):
                self._set_status("reconnected — in game")
                return True

            self._last_error = "stuck in main menu"
            time.sleep(DEFAULT_BACKOFF_BASE_SEC * attempt)

        self._set_status("reconnect failed after max attempts")
        terminate_roblox_processes()
        return False

    def _click_until_in_game(
        self,
        start_btn: tuple[int, int],
        *,
        old_log_file: str | None,
    ) -> bool:
        deadline = time.monotonic() + DEFAULT_START_WAIT_SEC
        while time.monotonic() < deadline:
            focus_roblox_window()
            time.sleep(0.3)
            x, y = start_btn
            if x > 0 or y > 0:
                click_at_settled(x, y)
            if is_in_game_from_log(old_log_file):
                return True
            if not roblox_processes_running():
                return False
            time.sleep(DEFAULT_CLICK_INTERVAL_SEC)
        return False
