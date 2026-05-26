"""Launch the edited local UI from assets/index.html in a desktop window."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import webbrowser
from copy import deepcopy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread

try:
    import webview
except ImportError:
    print("Missing dependency: pywebview")
    print("Install it with: py -m pip install pywebview")
    sys.exit(1)

from macro_engine import (
    MacroRecorder,
    MacroReplayer,
    github_original_click_at,
    load_json as load_macro_json,
    normalize_events,
    potion_filename,
    save_json as save_macro_json,
)
from potion_recorder import RECORDER_HEIGHT, RECORDER_WIDTH, PotionRecorderController

ROOT = Path(__file__).resolve().parent
INDEX_HTML = ROOT / "assets" / "index.html"
LOCAL_CONFIG_PATH = ROOT / "config.json"
BIOMES_PATH = ROOT / "assets" / "biomes_data.json"
APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "CoteabMacro"
APP_CONFIG_PATH = APP_DATA_DIR / "config.json"
POTION_DIR = APP_DATA_DIR / "crafting_files_do_not_open"
OBBY_PATHS_DIR = APP_DATA_DIR / "paths"
OBBY_PATHS_DIRS = (OBBY_PATHS_DIR, ROOT / "paths")
DEBUG_LOG_PATH = ROOT / "debug-f8c06d.log"
DEBUG_SESSION_ID = "f8c06d"
POTION_CRAFT_SLOWDOWN = 1.0
POTION_CRAFT_STEP_GAP_SEC = 0.0

_SERVER_BASE: str | None = None
CALIBRATION_KEY_RE = re.compile(r"^[A-Za-z0-9_:-]{1,80}$")


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


def start_asset_server(root: Path) -> str:
    """Serve repo files over HTTP so WebView2 can use ?query params."""

    class AssetHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), AssetHandler)
    host, port = server.server_address
    Thread(target=server.serve_forever, daemon=True).start()
    return f"http://{host}:{port}"


def ui_url(*, window: str | None = None, mode: str | None = None, page: str | None = None) -> str:
    if not _SERVER_BASE:
        raise RuntimeError("Asset server has not started")
    if page:
        return f"{_SERVER_BASE}/assets/{page}"
    url = f"{_SERVER_BASE}/assets/index.html"
    params: list[str] = []
    if window:
        params.append(f"window={window}")
    if mode:
        params.append(f"mode={mode}")
    if params:
        url += "?" + "&".join(params)
    return url

MODULE_FLAGS: list[tuple[str, str]] = [
    ("Biome Randomizer (BR)", "biome_randomizer"),
    ("Strange Controller (SC)", "strange_controller"),
    ("OCR Failsafe", "enable_ocr_failsafe"),
    ("Auto Reconnect", "auto_reconnect"),
    ("Auto Claim Daily Quests", "auto_claim_daily_quests"),
    ("Fishing Mode", "fishing_mode"),
    ("Auto Potion Craft", "enable_potion_crafting"),
    ("Potion Switching", "enable_potion_switching"),
    ("Auto Merchant Teleporter", "auto_merchant_teleporter"),
    ("Auto Merchant in Limbo", "auto_merchant_in_limbo"),
    ("Periodical Aura Screenshot", "periodical_aura_screenshot"),
    ("Periodical Inventory Screenshot", "periodical_inventory_screenshot"),
    ("Auto Complete Basic Obby", "enable_auto_obby"),
    ("Teleport Portable Crack", "teleport_portable_crack"),
    ("Auto Eden Contract", "auto_eden_contract"),
    ("Enable Buff in Glitched", "auto_buff_glitched"),
    ("Teleport Back to Limbo", "teleport_back_to_limbo"),
    ("Remote Access", "remote_access_enabled"),
]


def load_json(path: Path, default):
    if not path.exists():
        return deepcopy(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return deepcopy(default)


def resolve_config_path() -> Path:
    if APP_CONFIG_PATH.exists():
        return APP_CONFIG_PATH
    return LOCAL_CONFIG_PATH


def config_enabled(config: dict, key: str) -> bool:
    value = config.get(key)
    if isinstance(value, dict):
        if key == "auto_pop_biomes":
            return any(isinstance(item, dict) and item.get("enabled") for item in value.values())
        return any(bool(item.get("enabled")) for item in value.values() if isinstance(item, dict)) or bool(value)
    return bool(value)


class LocalUiApi:
    """Backend bridge so the bundled React UI matches the packaged app."""

    def __init__(self) -> None:
        self._config_path = resolve_config_path()
        self._config = self._load_config()
        self._recorder = MacroRecorder()
        self._replayer = MacroReplayer()
        self._macro_running = False
        self._macro_stop = Event()
        self._macro_thread: Thread | None = None
        self._calibration_hotkey = None
        self._calibration_capture_seq = 0
        self._calibration_capture_state: dict = {}
        self._potion_controller = PotionRecorderController(
            on_start_recording=self._begin_potion_click_recording,
            on_stop_save=self._finish_potion_click_recording,
            on_cancel_recording=self._cancel_potion_click_recording,
            on_main_start=self._hotkey_main_start,
            on_main_stop=self._hotkey_main_stop,
        )
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        POTION_DIR.mkdir(parents=True, exist_ok=True)
        OBBY_PATHS_DIR.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> dict:
        primary = load_json(self._config_path, {})
        if self._config_path == APP_CONFIG_PATH:
            return primary
        fallback = load_json(LOCAL_CONFIG_PATH, {})
        return {**fallback, **primary} if primary else fallback

    @property
    def _window(self) -> webview.Window:
        return webview.windows[0]

    def get_config(self):
        return deepcopy(self._config)

    def save_config(self, config):
        self._config = dict(config or {})
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            json.dumps(self._config, indent=2),
            encoding="utf-8",
        )
        return True

    def _valid_calibration_key(self, key) -> str | None:
        cleaned = str(key or "").strip()
        if not CALIBRATION_KEY_RE.fullmatch(cleaned):
            return None
        return cleaned

    def _emit_calibration_result(self, key: str, value: list[int], mode: str) -> None:
        payload = json.dumps({"key": key, "value": value, "mode": mode})
        try:
            self._window.evaluate_js(
                f"if (window.onCalibrationResult) window.onCalibrationResult({payload});"
            )
            # region agent log
            _debug_log(
                "run_local_ui.py:_emit_calibration_result",
                "calibration result emitted to ui",
                {"key": key, "value": value, "mode": mode},
                "Q3",
            )
            # endregion
        except Exception as error:
            # region agent log
            _debug_log(
                "run_local_ui.py:_emit_calibration_result",
                "calibration result emit failed",
                {"key": key, "value": value, "mode": mode, "error": str(error)},
                "Q3",
            )
            # endregion

    def create_calibration_window(self, key, mode="point"):
        cleaned = self._valid_calibration_key(key)
        if not cleaned:
            return {"ok": False, "error": "Unsupported calibration key"}
        capture_mode = "region" if str(mode).lower() == "region" else "point"

        # region agent log
        _debug_log(
            "run_local_ui.py:create_calibration_window",
            "original calibration api called",
            {"key": cleaned, "mode": capture_mode, "previous": self._config.get(cleaned)},
            "Q1,Q2,Q3",
        )
        # endregion
        try:
            import keyboard
            import pyautogui
        except Exception as error:
            return {"ok": False, "error": str(error)}

        if self._calibration_hotkey is not None:
            try:
                keyboard.remove_hotkey(self._calibration_hotkey)
            except Exception:
                pass
            self._calibration_hotkey = None

        def capture() -> None:
            try:
                x, y = pyautogui.position()
                value = [int(x), int(y)]
                if capture_mode == "region":
                    value = [int(x), int(y), 1, 1]
                self._config[cleaned] = value
                self.save_config(self._config)
                self._calibration_capture_seq += 1
                self._calibration_capture_state = {
                    "seq": self._calibration_capture_seq,
                    "key": cleaned,
                    "value": value,
                    "mode": capture_mode,
                    "timestamp": int(time.time() * 1000),
                }
                print(f"[calibration] {cleaned} = {value} via original UI F8")
                # region agent log
                _debug_log(
                    "run_local_ui.py:create_calibration_window.capture",
                    "original calibration api captured F8",
                    {"key": cleaned, "value": value, "mode": capture_mode},
                    "Q2,Q3",
                )
                # endregion
                self._emit_calibration_result(cleaned, value, capture_mode)
            finally:
                try:
                    if self._calibration_hotkey is not None:
                        keyboard.remove_hotkey(self._calibration_hotkey)
                except Exception:
                    pass
                self._calibration_hotkey = None

        self._calibration_hotkey = keyboard.add_hotkey("f8", capture, suppress=False)
        return {
            "ok": True,
            "status": f"Hover {cleaned} in Roblox and press F8",
            "key": cleaned,
            "mode": capture_mode,
            "seq": self._calibration_capture_seq,
        }

    def get_macro_version(self):
        return "2.1.8-local"

    def get_biome_data(self):
        return self.get_full_biome_data()

    def get_full_biome_data(self):
        data = deepcopy(load_json(BIOMES_PATH, {}))
        overrides = self._config.get("custom_biome_overrides") or {}
        for name, override in overrides.items():
            if isinstance(override, dict):
                data[name] = {**data.get(name, {}), **override}
        return data

    def get_active_modules(self):
        modules = {
            name: {
                "enabled": config_enabled(self._config, key),
                "active": self._macro_running and config_enabled(self._config, key),
            }
            for name, key in MODULE_FLAGS
        }
        if config_enabled(self._config, "auto_pop_biomes"):
            modules["Auto Pop Biomes"] = {"enabled": True, "active": self._macro_running}

        incompatibilities: list[str] = []
        if self._config.get("fishing_mode"):
            incompatibilities.append(
                "Fishing mode is active — movements, potion crafting, periodic screenshots, "
                "aura screenshots, daily quest claiming, and other non-essential mouse actions are paused."
            )
        if self._config.get("teleport_portable_crack") and (
            self._config.get("fishing_mode")
            or self._config.get("enable_potion_crafting")
            or self._config.get("enable_auto_obby")
        ):
            incompatibilities.append(
                "Portable Crack teleport only works when fishing mode, potion crafting, auto obby, "
                "and auto egg pathing are OFF."
            )

        return {"modules": modules, "incompatibilities": incompatibilities}

    def get_update_available(self):
        return None

    def check_for_updates(self):
        return {"available": False}

    def check_winocr_status(self):
        try:
            import winocr  # type: ignore

            version = getattr(winocr, "__version__", "unknown")
            return {"installed": True, "version": version}
        except ImportError:
            return {
                "installed": False,
                "version": "unknown",
                "message": "WinOCR not installed in this Python environment",
            }

    def list_potion_files(self):
        files: set[str] = set()
        if POTION_DIR.is_dir():
            files.update(path.name for path in POTION_DIR.glob("*.json"))
        return sorted(files)

    def check_obby_path_exists(self):
        for folder in OBBY_PATHS_DIRS:
            if folder.is_dir() and any(folder.glob("*.json")):
                return True
        return False

    def _hotkey_main_start(self) -> None:
        if self._potion_controller.is_open:
            return
        print("[main macro] F1 pressed")
        # region agent log
        _debug_log(
            "run_local_ui.py:_hotkey_main_start",
            "main F1 hotkey reached backend",
            {
                "macro_running": self._macro_running,
                "potion_open": self._potion_controller.is_open,
                "selected_potion_file": self._config.get("selected_potion_file"),
            },
            "H1",
        )
        # endregion
        self.set_biome_detection(True)

    def _hotkey_main_stop(self) -> None:
        if self._potion_controller.is_open:
            return
        print("[main macro] F2 pressed")
        self.set_biome_detection(False)

    def _begin_potion_click_recording(self) -> None:
        self._stop_local_macro()
        self._replayer.cancel()
        self._recorder.start(clicks_only=True)

    def _cancel_potion_click_recording(self) -> None:
        if self._recorder.is_recording:
            self._recorder.stop()

    def _finish_potion_click_recording(self, name: str) -> str | None:
        if self._recorder.is_recording:
            self._recorder.stop()

        try:
            filename = potion_filename(name)
        except ValueError as error:
            return str(error)

        events = list(self._recorder._events)
        mouse_downs = [event for event in events if event.get("type") == "mouse_down"]
        if not mouse_downs:
            return "No clicks recorded — press Record, then click in Roblox"

        payload = {"events": normalize_events(events), "clicks_only": True}
        target = POTION_DIR / filename
        save_macro_json(target, payload)
        print(f"[potion recorder] saved {target} ({len(mouse_downs)} clicks)")
        self._recorder._events = []
        self._potion_controller.set_click_count(0)
        return None

    def _selected_potion_file(self) -> str | None:
        candidates = [
            self._config.get("selected_potion_file"),
            self._config.get("potion_last_file"),
            self._config.get("potion_file_1"),
            self._config.get("potion_file_2"),
            self._config.get("potion_file_3"),
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return potion_filename(candidate.strip())
        return None

    def _selected_potion_name(self) -> str | None:
        filename = self._selected_potion_file()
        if not filename:
            return None
        return Path(filename).stem.strip()

    def _calibration_point(self, key: str, *, fallback: str | None = None) -> tuple[int, int] | None:
        value = self._config.get(key)
        if value is None and fallback:
            value = self._config.get(fallback)
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

    def _potion_interval_seconds(self) -> int:
        raw = self._config.get("potion_craft_interval") or self._config.get("potion_switch_interval") or 180
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            value = 180
        return max(10, value)

    def _run_selected_potion_once(self, *, reason: str, loop_add_craft: bool = False) -> str:
        potion_name = self._selected_potion_name()
        if not potion_name:
            return "Error: no selected potion"
        return self._run_calibrated_potion(potion_name, reason=reason, loop_add_craft=loop_add_craft)

    def _run_calibrated_potion(self, potion_name: str, *, reason: str, loop_add_craft: bool = False) -> str:
        if self._potion_controller.is_open or self._recorder.is_recording:
            return "Skipped: recorder is open or recording"

        potion_name = Path(potion_name or "").stem.strip()
        if not potion_name:
            return "Error: no potion name"

        items_tab = self._calibration_point("potion_items_tab", fallback="items_tab")
        search_bar = self._calibration_point("potion_search_bar", fallback="search_bar")
        first_slot = self._calibration_point("potion_first_potion_slot_pos", fallback="first_item_inventory_slot_pos")
        recipe_button = self._calibration_point("potion_recipe_button")
        auto_add_button = self._calibration_point("potion_auto_add_button", fallback="potion_auto_button")
        craft_button = self._calibration_point("potion_craft_button", fallback="potion_auto_button")
        missing = [
            name
            for name, point in {
                "potion_items_tab/items_tab": items_tab,
                "potion_search_bar/search_bar": search_bar,
                "potion_first_potion_slot_pos/first_item_inventory_slot_pos": first_slot,
                "potion_recipe_button": recipe_button,
                "potion_auto_add_button": auto_add_button,
                "potion_craft_button": craft_button,
            }.items()
            if point is None
        ]
        if missing:
            return "Error: missing potion calibration: " + ", ".join(missing)

        # region agent log
        _debug_log(
            "run_local_ui.py:_run_selected_potion_once",
            "main macro using calibrated potion craft flow",
            {
                "reason": reason,
                "potion_name": potion_name,
                "items_tab": items_tab,
                "search_bar": search_bar,
                "first_slot": first_slot,
                "setup_source": {
                    "items_tab": "potion_items_tab",
                    "search_bar": "potion_search_bar",
                    "first_slot": "potion_first_potion_slot_pos",
                },
                "recipe_button": recipe_button,
                "auto_add_button": auto_add_button,
                "craft_button": craft_button,
                "missing": missing,
            },
            "H6,H7,H8",
        )
        # endregion
        print(f"[main macro] {reason}: crafting {potion_name} with calibrated buttons")
        focused = self._potion_controller.focus_roblox()
        print(f"[main macro] Roblox focus before craft: {focused}")
        if not focused:
            return "Error: Roblox not focused"

        def pause_for_potion_step() -> bool:
            return not self._macro_stop.is_set() if loop_add_craft else True

        def potion_click(label: str, point: tuple[int, int], *, cycle: int | None = None, click: int = 1) -> bool:
            # region agent log
            _debug_log(
                "run_local_ui.py:_run_calibrated_potion.potion_click",
                "potion click step",
                {
                    "label": label,
                    "point": point,
                    "cycle": cycle,
                    "loop_add_craft": loop_add_craft,
                    "slowdown": POTION_CRAFT_SLOWDOWN,
                    "extra_gap_sec": POTION_CRAFT_STEP_GAP_SEC,
                    "click_method": "github_original_click_at",
                    "click_count": click,
                },
                "T3,T4,T6,G1,G2",
            )
            # endregion
            github_original_click_at(*point, click=click)
            return pause_for_potion_step()

        try:
            import pyautogui
            import autoit

            pyautogui.PAUSE = 0.04 * POTION_CRAFT_SLOWDOWN
            # region agent log
            _debug_log(
                "run_local_ui.py:_run_calibrated_potion.search",
                "about to click search and type potion name",
                {
                    "potion_name": potion_name,
                    "foreground": self._potion_controller._foreground_title(),
                    "search_bar": search_bar,
                    "items_tab": items_tab,
                    "setup_source": {
                        "items_tab": "potion_items_tab",
                        "search_bar": "potion_search_bar",
                    },
                },
                "T1,T2,T3",
            )
            # endregion
            if not potion_click("items_tab", items_tab):
                return f"Stopped while setting up {potion_name}"
            if not potion_click("search_bar", search_bar, click=2):
                return f"Stopped while setting up {potion_name}"
            autoit.send("^{a}")
            autoit.send("{BACKSPACE}")
            autoit.send(potion_name)
            if not pause_for_potion_step():
                return f"Stopped while searching {potion_name}"
            # region agent log
            _debug_log(
                "run_local_ui.py:_run_calibrated_potion.search",
                "search text sent",
                {
                    "potion_name": potion_name,
                    "foreground": self._potion_controller._foreground_title(),
                },
                "T1,T2",
            )
            # endregion
            # region agent log
            _debug_log(
                "run_local_ui.py:_run_calibrated_potion.actions",
                "about to click result recipe add craft",
                {
                    "first_slot": first_slot,
                    "recipe_button": recipe_button,
                    "auto_add_button": auto_add_button,
                    "craft_button": craft_button,
                },
                "T3,T4",
            )
            # endregion
            if not potion_click("first_slot", first_slot):
                return f"Stopped while selecting {potion_name}"
            if not potion_click("recipe_button", recipe_button):
                return f"Stopped while opening recipe for {potion_name}"

            cycle = 0
            while True:
                cycle += 1
                # region agent log
                _debug_log(
                    "run_local_ui.py:_run_calibrated_potion.add_craft_loop",
                    "running add everything and craft cycle",
                    {
                        "potion_name": potion_name,
                        "cycle": cycle,
                        "loop_add_craft": loop_add_craft,
                        "stop_requested": self._macro_stop.is_set(),
                    },
                    "T3,T6",
                )
                # endregion
                if not potion_click("auto_add_button", auto_add_button, cycle=cycle):
                    return f"Stopped while auto-adding {potion_name}"
                if not potion_click("craft_button", craft_button, cycle=cycle):
                    return f"Stopped while crafting {potion_name}"
                if not loop_add_craft:
                    break
        except Exception as error:
            result = f"Error: calibrated craft failed: {error}"
            print(f"[main macro] craft result: {result}")
            return result

        result = f"Crafted {potion_name}" if not loop_add_craft else f"Stopped crafting {potion_name}"
        print(f"[main macro] craft result: {result}")
        return result

    def _macro_loop(self) -> None:
        print("[main macro] worker started")
        try:
            if self._config.get("enable_potion_crafting"):
                self._run_selected_potion_once(reason="startup", loop_add_craft=True)
            else:
                print("[main macro] potion crafting disabled; no local crafting action to run")

            while not self._macro_stop.wait(1.0):
                if not self._config.get("enable_potion_crafting"):
                    continue

                interval = self._potion_interval_seconds()
                if self._macro_stop.wait(interval):
                    break
                self._run_selected_potion_once(reason=f"interval {interval}s", loop_add_craft=True)
        finally:
            self._macro_running = False
            print("[main macro] worker stopped")

    def _start_local_macro(self) -> None:
        if self._macro_running:
            print("[main macro] already running")
            return

        self._macro_stop.clear()
        self._macro_running = True
        self._macro_thread = Thread(target=self._macro_loop, daemon=True)
        self._macro_thread.start()
        print("[main macro] started")

    def _stop_local_macro(self) -> None:
        if not self._macro_running and not self._replayer.is_running:
            print("[main macro] already stopped")
            return

        print("[main macro] stopping")
        self._macro_stop.set()
        self._replayer.cancel()
        self._macro_running = False

    def init_hotkeys(self) -> None:
        self._potion_controller.register_main_hotkeys()

    def get_potion_recorder_state(self):
        state = self._potion_controller.get_state()
        if not state.get("open"):
            return state
        count = self._recorder.click_count
        if self._recorder.is_recording or count:
            state["click_count"] = count
            self._potion_controller.set_click_count(count)
        return state

    def set_potion_recorder_name(self, name):
        self._potion_controller.set_name(name or "")
        return True

    def close_potion_recorder_overlay(self):
        try:
            if self._recorder.is_recording:
                self._recorder.stop()
            window = self._potion_controller._overlay_window
            self._potion_controller.shutdown()
            self._potion_controller._overlay_window = None
            if window is not None:
                Thread(target=self._destroy_recorder_window, args=(window,), daemon=True).start()
            return True
        except Exception as error:
            print(f"[potion recorder] close failed: {error}")
            return False

    def _destroy_recorder_window(self, window) -> None:
        try:
            import time

            time.sleep(0.2)
            window.destroy()
        except Exception as error:
            print(f"[potion recorder] window destroy failed: {error}")

    def _on_recorder_window_closed(self, _window=None):
        try:
            if self._recorder.is_recording:
                self._recorder.stop()
            self._potion_controller.shutdown()
            self._potion_controller._overlay_window = None
        except Exception as error:
            print(f"[potion recorder] closed cleanup failed: {error}")

    def minimize_potion_recorder_window(self):
        window = self._potion_controller._overlay_window
        if window is not None:
            try:
                window.minimize()
            except Exception as error:
                print(f"[potion recorder] failed to minimize recorder window: {error}")
                return False
        return True

    def open_recorder_window_potion(self):
        self._stop_local_macro()
        self._replayer.cancel()
        if self._potion_controller.is_open:
            overlay = self._potion_controller._overlay_window
            if overlay is not None:
                try:
                    overlay.show()
                    return True
                except Exception:
                    self._potion_controller.close()

        x, y = self._potion_controller.overlay_position()
        try:
            window = webview.create_window(
                "Potion Recorder",
                url=ui_url(page="potion_recorder_overlay.html"),
                width=RECORDER_WIDTH,
                height=RECORDER_HEIGHT,
                x=x,
                y=y,
                resizable=False,
                min_size=(RECORDER_WIDTH, RECORDER_HEIGHT),
                frameless=True,
                easy_drag=False,
                on_top=False,
                text_select=True,
                transparent=False,
                background_color="#13111f",
                js_api=self,
            )
        except Exception as error:
            print(f"[potion recorder] failed to open recorder window: {error}")
            return False
        window.events.closed += self._on_recorder_window_closed
        self._potion_controller.attach_overlay_window(window)
        self._potion_controller.open()
        return True

    def start_macro_recording(self):
        try:
            if self._potion_controller.is_open:
                error = self._potion_controller.start_recording()
                return {"ok": error is None, "error": error}
            self._potion_controller.focus_roblox()
            self._recorder.start(clicks_only=False)
            return {"ok": True, "error": None}
        except Exception as error:
            print(f"[potion recorder] record failed: {error}")
            if self._potion_controller.is_open:
                self._potion_controller._set_status(f"Record failed: {error}")
            return {"ok": False, "error": str(error)}

    def stop_macro_recording_potion(self, name):
        try:
            cleaned = (name or "").strip()
            if not cleaned:
                if self._potion_controller.is_open:
                    self._potion_controller._set_status("Enter a potion name first")
                return {"ok": False, "error": "Enter a potion name first"}

            if self._potion_controller.is_open:
                self._potion_controller.set_name(cleaned)
                error = self._potion_controller.stop_and_save()
            else:
                error = self._finish_potion_click_recording(cleaned)

            if error:
                print(f"[potion recorder] {error}")
                return {"ok": False, "error": error}

            filename = potion_filename(cleaned)
            return {"ok": True, "error": None, "filename": filename}
        except Exception as error:
            print(f"[potion recorder] save failed: {error}")
            if self._potion_controller.is_open:
                self._potion_controller._set_status(f"Save failed: {error}")
            return {"ok": False, "error": str(error)}

    def stop_macro_recording(self):
        self._recorder.stop()
        payload = self._recorder.build_payload(include_screen=True)
        save_macro_json(OBBY_PATHS_DIR / "obby.json", payload)
        return True

    def replay_potion_recording(self, name):
        if self._recorder.is_recording:
            return "Error: stop recording before replaying"

        try:
            filename = potion_filename(name)
        except ValueError as error:
            return f"Error: {error}"

        path = POTION_DIR / filename
        if not path.exists():
            return f"Error: {filename} not found"

        try:
            payload = load_macro_json(path)
        except (OSError, json.JSONDecodeError) as error:
            return f"Error: {error}"

        if self._replayer.is_running:
            return "Error: replay already running"

        def run_replay() -> None:
            print(f"[potion recorder] replay starting {filename}")
            self._potion_controller.focus_roblox()
            result = self._replayer.replay(payload)
            print(f"[potion recorder] replay {filename}: {result}")

        Thread(target=run_replay, daemon=True).start()
        return "Replay Started"

    def craft_selected_potion(self):
        if self._recorder.is_recording or self._potion_controller.is_open:
            return {"ok": False, "error": "Close/stop the recorder before crafting"}
        if self._replayer.is_running:
            return {"ok": False, "error": "Replay already running"}

        def run() -> None:
            result = self._run_selected_potion_once(reason="manual")
            print(f"[main macro] manual craft selected result: {result}")

        thread = Thread(target=run, daemon=True)
        thread.start()
        return {"ok": True, "error": None, "status": "Craft started"}

    def craft_potion_by_name(self, name):
        cleaned = Path(str(name or "")).stem.strip()
        if not cleaned:
            return {"ok": False, "error": "Potion name is required"}
        if self._recorder.is_recording or self._potion_controller.is_open:
            return {"ok": False, "error": "Close/stop the recorder before crafting"}
        if self._replayer.is_running:
            return {"ok": False, "error": "Replay already running"}

        def run() -> None:
            result = self._run_calibrated_potion(cleaned, reason="manual-name")
            print(f"[main macro] manual craft {cleaned}: {result}")

        Thread(target=run, daemon=True).start()
        return {"ok": True, "error": None, "status": f"Crafting {cleaned}"}

    def set_calibration_point(self, key):
        allowed = {
            "potion_items_tab",
            "potion_search_bar",
            "potion_first_potion_slot_pos",
            "potion_recipe_button",
            "potion_auto_add_button",
            "potion_craft_button",
        }
        if key not in allowed:
            return {"ok": False, "error": "Unsupported calibration key"}
        try:
            import pyautogui

            x, y = pyautogui.position()
        except Exception as error:
            return {"ok": False, "error": str(error)}
        self._config[key] = [int(x), int(y)]
        self.save_config(self._config)
        print(f"[calibration] {key} = {[int(x), int(y)]}")
        return {"ok": True, "key": key, "value": [int(x), int(y)]}

    def begin_calibration_point(self, key):
        allowed = {
            "potion_items_tab",
            "potion_search_bar",
            "potion_first_potion_slot_pos",
            "potion_recipe_button",
            "potion_auto_add_button",
            "potion_craft_button",
        }
        if key not in allowed:
            return {"ok": False, "error": "Unsupported calibration key"}

        # region agent log
        _debug_log(
            "run_local_ui.py:begin_calibration_point",
            "calibration arm requested",
            {"key": key, "previous": self._config.get(key)},
            "C1,C3",
        )
        # endregion
        try:
            import keyboard
            import pyautogui
        except Exception as error:
            return {"ok": False, "error": str(error)}

        if self._calibration_hotkey is not None:
            try:
                keyboard.remove_hotkey(self._calibration_hotkey)
            except Exception:
                pass
            self._calibration_hotkey = None

        def capture() -> None:
            try:
                x, y = pyautogui.position()
                self._config[key] = [int(x), int(y)]
                self.save_config(self._config)
                self._calibration_capture_seq += 1
                self._calibration_capture_state = {
                    "seq": self._calibration_capture_seq,
                    "key": key,
                    "value": [int(x), int(y)],
                    "timestamp": int(time.time() * 1000),
                }
                print(f"[calibration] {key} = {[int(x), int(y)]} via F8")
                # region agent log
                _debug_log(
                    "run_local_ui.py:begin_calibration_point.capture",
                    "calibration F8 captured position",
                    {"key": key, "value": [int(x), int(y)]},
                    "C3",
                )
                # endregion
            finally:
                try:
                    if self._calibration_hotkey is not None:
                        keyboard.remove_hotkey(self._calibration_hotkey)
                except Exception:
                    pass
                self._calibration_hotkey = None

        self._calibration_hotkey = keyboard.add_hotkey("f8", capture, suppress=False)
        return {
            "ok": True,
            "status": f"Hover {key} in Roblox and press F8",
            "seq": self._calibration_capture_seq,
        }

    def get_calibration_status(self):
        return {
            "ok": True,
            "seq": self._calibration_capture_seq,
            "capture": dict(self._calibration_capture_state),
        }

    def replay_recording(self):
        path = OBBY_PATHS_DIR / "obby.json"
        if not path.exists():
            return "Error: obby.json not found — record an obby path first"

        try:
            payload = load_macro_json(path)
        except (OSError, json.JSONDecodeError) as error:
            return f"Error: {error}"

        self._potion_controller.focus_roblox()
        return self._replayer.replay(payload)

    def align_camera(self):
        return "Aligned!"

    def import_config(self):
        try:
            result = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("JSON files (*.json)", "All files (*.*)"),
            )
        except Exception as error:
            return {"success": False, "error": str(error)}

        if not result:
            return {"success": False, "error": "No file selected"}

        source = Path(result[0] if isinstance(result, (list, tuple)) else result)
        try:
            imported = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return {"success": False, "error": str(error)}

        if not isinstance(imported, dict):
            return {"success": False, "error": "Invalid config file"}

        self.save_config(imported)
        return {"success": True}

    def send_webhook_status(self, message, color=5814783):
        print(f"[webhook preview] {message} (color={color})")
        return True

    def set_always_on_top(self, enabled):
        self._window.on_top = bool(enabled)
        return True

    def set_biome_detection(self, enabled):
        enabled = bool(enabled)
        self._config["enable_biome_detection"] = enabled
        # region agent log
        _debug_log(
            "run_local_ui.py:set_biome_detection",
            "main macro toggle requested",
            {
                "enabled": enabled,
                "macro_running": self._macro_running,
                "enable_potion_crafting": self._config.get("enable_potion_crafting"),
                "selected_potion_file": self._config.get("selected_potion_file"),
                "potion_file_1": self._config.get("potion_file_1"),
                "replayer_running": self._replayer.is_running,
            },
            "H1,H2",
        )
        # endregion
        if enabled:
            print("[main macro] START requested")
            self._potion_controller.focus_roblox()
            self._start_local_macro()
        else:
            print("[main macro] STOP requested")
            self._stop_local_macro()
        return True

    def open_url(self, url):
        webbrowser.open(url)
        return True

    def minimize_window(self):
        self._window.minimize()

    def minimize(self):
        self.minimize_window()

    def window_minimize(self):
        self.minimize_window()

    def close_window(self):
        self._stop_local_macro()
        self._window.destroy()

    def close(self):
        self.close_window()

    def quit_app(self):
        self.close_window()

    def window_close(self):
        self.close_window()

    def toggle_maximize(self):
        if getattr(self._window, "maximized", False):
            self._window.restore()
        else:
            self._window.maximize()

    def maximize_window(self):
        self._window.maximize()

    def restore_window(self):
        self._window.restore()

    def window_toggle_maximize(self):
        self.toggle_maximize()

    def preview_noop(self, *args, **kwargs):
        print(f"[local preview] {kwargs or args or 'noop'}")
        return True

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self.preview_noop


def main() -> int:
    global _SERVER_BASE

    if not INDEX_HTML.exists():
        print(f"UI file not found: {INDEX_HTML}")
        return 1

    _SERVER_BASE = start_asset_server(ROOT)
    print(f"Serving UI from {_SERVER_BASE}")

    config_path = resolve_config_path()
    print(f"Using config: {config_path}")
    if config_path == APP_CONFIG_PATH:
        print("Loaded your real Coteab Macro settings from AppData.")
    else:
        print("AppData config not found — using repo config.json fallback.")

    api = LocalUiApi()
    window = webview.create_window(
        "Coteab Macro (Local UI Preview)",
        url=ui_url(),
        width=980,
        height=640,
        min_size=(860, 540),
        frameless=True,
        easy_drag=True,
        js_api=api,
    )

    def on_ready():
        api.init_hotkeys()

    webview.start(debug=False, func=on_ready)
    api._stop_local_macro()
    api._potion_controller.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
