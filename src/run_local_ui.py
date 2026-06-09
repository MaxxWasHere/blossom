"""Launch the edited local UI from assets/index.html in a desktop window."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from contextlib import contextmanager
from copy import deepcopy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from threading import Event, Lock, Thread

try:
    import webview
except ImportError:
    print("Missing dependency: pywebview")
    print("Install it with: py -m pip install pywebview")
    sys.exit(1)

from macro_engine import (
    MacroRecorder,
    MacroReplayer,
    _sleep_sec,
    align_camera_look_down,
    github_original_click_at,
    load_json as load_macro_json,
    potion_filename,
    release_stuck_inputs,
    save_json as save_macro_json,
)
from button_region_check import parse_calibration_region
from calibration_capture import capture_region_drag
from potion_craft_rules import (
    GREEN_GUARD_CALIBRATION_KEYS,
    green_guard_allows_click,
    submit_potion_search_text,
)
from discord_webhooks import (
    DEFAULT_RARE_MENTION_MODE,
    REMOVED_BIOMES,
    migrate_biome_webhook_config,
    normalize_webhook_urls,
    send_aura_webhook,
    send_biome_webhook,
    send_currency_webhook,
    send_discord_webhook,
    send_eden_webhook,
    send_status_webhook,
)
from blossom_updater import (
    APP_VERSION,
    GITHUB_OWNER,
    GITHUB_REPO,
    apply_exe_update,
    build_channel,
    check_newer_than_local,
    check_update_status,
    display_version,
    fetch_latest_release,
    is_frozen_build,
    version_info,
)
from macro_hotkeys import (
    DEFAULT_MACRO_START_KEY,
    DEFAULT_MACRO_STOP_KEY,
    MacroHotkeyManager,
    is_unbound_hotkey,
    normalize_hotkey,
    resolve_hotkey_setting,
)
from blossom_auras import should_ping_aura
from blossom_dirs import (
    APP_CONFIG_PATH,
    APP_DATA_DIR,
    OBBY_PATHS_DIR,
    POTION_DIR,
    dev_repo_root,
    ensure_app_data_dirs,
    migrate_all_user_data,
)
from blossom_runtime_deps import abi_key, cv2_status, ensure_opencv
from blossom_custom_ui import (
    ensure_sample_custom_ui_file,
    list_custom_ui_themes,
    read_custom_ui_css,
)
from blossom_prepath import (
    camera_align_down_px_from_config,
    replay_movement_path,
    run_pre_path_alignment,
)
from blossom_merchant import (
    merchant_cooldown_remaining,
    merchant_in_limbo_enabled,
    merchant_teleporter_enabled,
    merchant_teleporter_ready,
    mt_interval_seconds,
    run_merchant_limbo_interact,
    run_merchant_teleporter,
)
from blossom_quests import (
    daily_quests_enabled,
    daily_quests_ready,
    quest_interval_seconds,
    run_daily_quest_claim,
)
from blossom_biome_selector import (
    apply_calibration_side_effects,
    biome_selector_enabled,
    biome_selector_interval_seconds,
    biome_selector_ready,
    calibration_status,
    normalize_drive_toggles,
    run_biome_selector,
)
from blossom_eden import (
    auto_eden_enabled,
    auto_eden_ready,
    run_auto_eden_loop,
)
from blossom_brsc import (
    BR_ITEM_NAME,
    SC_ITEM_NAME,
    biome_randomizer_enabled,
    br_interval_seconds,
    brsc_ready,
    run_use_item,
    sc_interval_seconds,
    strange_controller_enabled,
)
from blossom_buffs import (
    auto_buff_glitched_enabled,
    buffs_ready,
    run_auto_pop_buffs,
)
from blossom_biomes import GLITCHED_BIOME, BiomeWatcher
import blossom_license
from blossom_fishing import close_roblox_chat_from_config, run_fishing_loop
from blossom_macro_session import MacroSessionGate
from blossom_ui_scheduler import (
    MacroUiTask,
    ScheduledUiTask,
    pick_task,
    schedule,
    startup_order,
)

def _bundle_root() -> Path:
    """Bundled UI/assets (PyInstaller extract dir when frozen)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", dev_repo_root()))
    return dev_repo_root()


def _install_root() -> Path:
    """Folder where BlossomMacro.exe / the project lives — persistent data goes here."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return dev_repo_root()


ROOT = _bundle_root()
INSTALL_ROOT = _install_root()
INDEX_HTML = ROOT / "assets" / "index.html"
APP_ICON_PATH = ROOT / "assets" / "icon.ico"
if not APP_ICON_PATH.is_file():
    APP_ICON_PATH = ROOT / "icon.ico"
LOCAL_CONFIG_PATH = INSTALL_ROOT / "config.json"
BIOMES_PATH = ROOT / "assets" / "biomes_data.json"
AURAS_PATH = ROOT / "assets" / "auras.json"
OBBY_PATHS_DIRS = (OBBY_PATHS_DIR, INSTALL_ROOT / "paths", ROOT / "paths")
POTION_CRAFT_SLOWDOWN = 1.0
POTION_CRAFT_STEP_GAP_SEC = 0.0
POTION_CLICK_PRE_SLEEP_SEC = 0.14
POTION_LOOP_SLOWDOWN = 1.2
# Brief pause between potions when rotating (not another switch interval).
POTION_SWITCH_GAP_SEC = 0.0
QUEST_AFTER_MERCHANT_SETTLE_SEC = 0.4
UI_BETWEEN_TASKS_SETTLE_SEC = 0.75
# How long start/stop waits for the previous macro worker thread to finish a
# tick and exit before giving up. The loop ticks every 0.15s, so this is ample
# even when a UI action just started; keeps restart from leaking a live thread.
MACRO_THREAD_JOIN_TIMEOUT_SEC = 5.0

# Update check tuning. The check only runs at launch and then on a long timer,
# so these add no steady-state cost.
UPDATE_CHECK_ATTEMPTS = 3
UPDATE_CHECK_BACKOFF_SEC = (2.0, 8.0)  # waits between attempts 1->2, 2->3
UPDATE_RECHECK_SECONDS = 6 * 60 * 60  # re-check every 6 hours while app stays open

_SERVER_BASE: str | None = None
CALIBRATION_KEY_RE = re.compile(r"^[A-Za-z0-9_:-]{1,80}$")




def apply_windows_window_icon(window, icon_path: Path) -> None:
    """Set taskbar / title-bar icon on Windows (Blossom sakura icon)."""
    if sys.platform != "win32" or not icon_path.is_file():
        return
    try:
        import ctypes

        WM_SETICON = 0x80
        ICON_SMALL = 0
        ICON_BIG = 1
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x10
        LR_DEFAULTSIZE = 0x40

        user32 = ctypes.windll.user32
        hwnd = None
        native = getattr(window, "native", None)
        if native is not None:
            handle = getattr(native, "Handle", None) or getattr(native, "handle", None)
            if handle is not None:
                hwnd = int(handle)
        if not hwnd:
            hwnd = user32.FindWindowW(None, str(window.title))
        if not hwnd:
            return

        path = str(icon_path.resolve())
        hicon = user32.LoadImageW(
            None,
            path,
            IMAGE_ICON,
            0,
            0,
            LR_LOADFROMFILE | LR_DEFAULTSIZE,
        )
        if not hicon:
            return
        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
    except Exception:
        pass


WIN32_MIN_WINDOW = (860, 540)
DEFAULT_WINDOW_WIDTH = 980
DEFAULT_WINDOW_HEIGHT = 640
MAX_WINDOW_WIDTH = 2560
MAX_WINDOW_HEIGHT = 1600


def _clamp_window_size(width, height) -> tuple[int, int]:
    min_w, min_h = WIN32_MIN_WINDOW
    try:
        w = int(round(float(width)))
        h = int(round(float(height)))
    except (TypeError, ValueError):
        w, h = DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT
    w = max(min_w, min(MAX_WINDOW_WIDTH, w))
    h = max(min_h, min(MAX_WINDOW_HEIGHT, h))
    return w, h


def _resolve_initial_window_size(config: dict) -> tuple[int, int]:
    w = config.get("ui_window_width")
    h = config.get("ui_window_height")
    if w is not None and h is not None:
        return _clamp_window_size(w, h)
    return DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT


def _window_hwnd(window) -> int | None:
    """Resolve native HWND for a pywebview window (Windows)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        user32 = ctypes.windll.user32
        handle = int(getattr(window, "handle", 0) or 0)
        if handle:
            return handle
        native = getattr(window, "native", None)
        if native is not None:
            raw = getattr(native, "Handle", None) or getattr(native, "handle", None)
            if raw is not None:
                return int(raw)
        hwnd = user32.FindWindowW(None, str(window.title))
        return int(hwnd) if hwnd else None
    except Exception:
        return None


def apply_windows_frameless_chrome(window) -> None:
    """Frameless Win32 polish: native resize, shadow, Win11 rounded HWND corners."""
    if sys.platform != "win32":
        return
    hwnd = _window_hwnd(window)
    if not hwnd:
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi

        GWL_STYLE = -16
        WS_THICKFRAME = 0x00040000
        WS_MINIMIZEBOX = 0x00020000
        WS_MAXIMIZEBOX = 0x00010000
        WS_CAPTION = 0x00C00000

        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        style |= WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_CAPTION
        user32.SetWindowLongW(hwnd, GWL_STYLE, style)

        SWP_FRAMECHANGED = 0x0020
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER,
        )

        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        pref = ctypes.c_int(DWMWCP_ROUND)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(pref),
            ctypes.sizeof(pref),
        )

        class _Margins(ctypes.Structure):
            _fields_ = [
                ("cxLeftWidth", ctypes.c_int),
                ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int),
                ("cyBottomHeight", ctypes.c_int),
            ]

        margins = _Margins(1, 1, 1, 1)
        dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
    except Exception:
        pass


_WIN32_RESIZE_EDGES = frozenset(
    {
        "left",
        "right",
        "top",
        "bottom",
        "top-left",
        "top-right",
        "bottom-left",
        "bottom-right",
    }
)


def _manual_resize_window(hwnd: int, edge: str, min_size: tuple[int, int]) -> None:
    """Drag-resize for frameless pywebview (FormBorderStyle None ignores NC messages)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    VK_LBUTTON = 0x01
    min_w, min_h = min_size

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    if user32.IsZoomed(hwnd):
        return

    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    start_l, start_t, start_r, start_b = rect.left, rect.top, rect.right, rect.bottom

    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    start_x, start_y = pt.x, pt.y

    # Wait until the button is down (JS may call us just after pointerdown).
    for _ in range(30):
        if user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000:
            break
        time.sleep(0.01)
    else:
        return

    def clamp_rect(l: int, t: int, r: int, b: int) -> tuple[int, int, int, int]:
        w = r - l
        h = b - t
        if w < min_w:
            if "left" in edge:
                l = r - min_w
            else:
                r = l + min_w
        if h < min_h:
            if "top" in edge:
                t = b - min_h
            else:
                b = t + min_h
        return l, t, r, b

    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010

    while user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000:
        user32.GetCursorPos(ctypes.byref(pt))
        dx = pt.x - start_x
        dy = pt.y - start_y
        l, t, r, b = start_l, start_t, start_r, start_b

        if "left" in edge:
            l = start_l + dx
        if "right" in edge:
            r = start_r + dx
        if "top" in edge:
            t = start_t + dy
        if "bottom" in edge:
            b = start_b + dy

        l, t, r, b = clamp_rect(l, t, r, b)
        user32.SetWindowPos(
            hwnd,
            0,
            l,
            t,
            r - l,
            b - t,
            SWP_NOZORDER | SWP_NOACTIVATE,
        )
        time.sleep(0.008)


def _set_always_on_top_win32(hwnd: int, enabled: bool) -> bool:
    import ctypes

    user32 = ctypes.windll.user32
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_SHOWWINDOW = 0x0040
    insert_after = HWND_TOPMOST if enabled else HWND_NOTOPMOST
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
    return bool(user32.SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, flags))


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
    ("Biome Selector (Broken / WIP)", "biome_selector"),
    ("OCR Failsafe", "enable_ocr_failsafe"),
    ("Auto Reconnect", "auto_reconnect"),
    ("Auto Claim Daily Quests", "auto_claim_daily_quests"),
    ("Fishing Mode", "fishing_mode"),
    ("Auto Potion Craft", "enable_potion_crafting"),
    ("Potion Switching", "enable_potion_switching"),
    ("Auto Merchant Teleporter", "merchant_teleporter"),
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
    if LOCAL_CONFIG_PATH.exists():
        shutil.copy2(LOCAL_CONFIG_PATH, APP_CONFIG_PATH)
        return APP_CONFIG_PATH
    return APP_CONFIG_PATH


def config_enabled(config: dict, key: str) -> bool:
    value = config.get(key)
    if isinstance(value, dict):
        if key == "auto_pop_biomes":
            return any(isinstance(item, dict) and item.get("enabled") for item in value.values())
        return any(bool(item.get("enabled")) for item in value.values() if isinstance(item, dict)) or bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def biome_notify_enabled(notifier: dict, biome_key: str) -> bool:
    """True when biome_notifier enables Discord alerts for this biome."""
    val = notifier.get(biome_key)
    if val is None:
        val = notifier.get(str(biome_key).upper())
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    text = str(val).strip().lower()
    if text in ("none", "off", "false", "0", ""):
        return False
    if text in ("message", "on", "true", "1", "yes"):
        return True
    return bool(val)


class LocalUiApi:
    """Backend bridge so the bundled React UI matches the packaged app."""

    def __init__(self) -> None:
        self._config_path = resolve_config_path()
        self._config = self._load_config()
        # mtime of the config file at the last successful load; lets the hot
        # macro loop skip re-reading/parsing JSON when nothing has changed.
        self._config_mtime = self._config_file_mtime()
        self._sync_potion_switching_with_craft(persist=True)
        self._macro_stop = Event()
        self._recorder = MacroRecorder()
        self._replayer = MacroReplayer()
        self._replayer.set_cancel_event(self._macro_stop)
        self._macro_running = False
        self._macro_started_at: float | None = None
        self._macro_thread: Thread | None = None
        # Serializes macro start/stop so a quick stop->start can't run the
        # teardown/join and the fresh-start setup at the same time.
        self._macro_lifecycle_lock = Lock()
        self._buff_pop_requested = Event()
        self._biome_watcher: BiomeWatcher | None = None
        # App-lifetime stop so the biome/aura watcher always listens, even when
        # the macro is idle. Only set on app close.
        self._listener_stop = Event()
        # App-lifetime stop for the periodic license re-validation thread.
        self._license_stop = Event()
        self._license_thread: Thread | None = None
        self._calibration_hotkey = None
        self._calibration_capture_seq = 0
        self._calibration_capture_state: dict = {}
        self._calibration_capture_active = False
        self._hotkeys = MacroHotkeyManager(
            get_hotkeys=self._macro_hotkey_pair,
            on_start=self._hotkey_main_start,
            on_stop=self._hotkey_main_stop,
        )
        self._update_cache: dict[str, str] | None = None
        self._update_check_running = False
        # "ok" | "checking" | "offline"; last outcome of the update check so a
        # manual check or the UI can show a quiet, non-intrusive status.
        self._update_last_status = "ok"
        self._update_recheck_stop = Event()
        self._update_recheck_thread: Thread | None = None
        self._potion_rotation_index = 0
        self._always_on_top_applied: bool | None = None
        self._always_on_top_lock = Lock()
        self._resize_lock = Lock()
        self._window_size_save_timer: threading.Timer | None = None
        self._window_size_save_lock = Lock()
        self._macro_session_gate = MacroSessionGate(settle_sec=UI_BETWEEN_TASKS_SETTLE_SEC)
        self._fishing_stop_event = Event()
        self._fishing_thread: Thread | None = None
        self._fishing_lock = Lock()
        self._fishing_busy = False
        self._eden_stop_event = Event()
        self._eden_thread: Thread | None = None
        self._eden_lock = Lock()
        self._fishing_runtime_state: dict = {
            "fish_caught_count": 0,
            "fish_caught_since_merchant": 0,
            "fish_caught_since_merchant_ocr": 0,
            "fish_caught_since_br_sc": 0,
        }
        # Serializes the explicit in-app OpenCV ("fishing vision") installer so a
        # second click can't kick off a concurrent download/extract.
        self._opencv_install_lock = Lock()
        self._opencv_installing = False
        self._opencv_install_thread: Thread | None = None
        ensure_app_data_dirs()
        ensure_sample_custom_ui_file()
        migrate_all_user_data(INSTALL_ROOT)
        if self._potion_crafting_enabled():
            self._remove_currency_screenshot_file()

    def _load_config(self) -> dict:
        primary = load_json(self._config_path, {})
        if self._config_path == APP_CONFIG_PATH:
            config = primary
        else:
            fallback = load_json(LOCAL_CONFIG_PATH, {})
            config = {**fallback, **primary} if primary else fallback
        migrate_biome_webhook_config(config)
        return config

    def _config_file_mtime(self) -> float | None:
        try:
            return self._config_path.stat().st_mtime
        except OSError:
            return None

    def _reload_config_from_disk(self) -> None:
        """Pick up UI toggles saved after the app started.

        The macro loop and fishing worker call this several times a second, so
        skip the JSON read/parse entirely when the config file is unchanged
        since the last load (UI saves rewrite the file, bumping its mtime)."""
        mtime = self._config_file_mtime()
        if mtime is None:
            return
        if mtime == self._config_mtime and self._config:
            return
        self._config = load_json(self._config_path, self._config)
        migrate_biome_webhook_config(self._config)
        self._config_mtime = mtime

    def _potion_crafting_enabled(self) -> bool:
        return config_enabled(self._config, "enable_potion_crafting")

    def _sync_potion_switching_with_craft(self, *, persist: bool = False) -> None:
        """Auto switcher only applies when potion crafting is on."""
        if self._potion_crafting_enabled():
            return
        if not config_enabled(self._config, "enable_potion_switching"):
            return
        self._config["enable_potion_switching"] = False
        if not persist:
            return
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(
                json.dumps(self._config, indent=2),
                encoding="utf-8",
            )
        except OSError as error:
            print(f"[config] could not clear enable_potion_switching: {error}")

    def _potion_switching_enabled(self) -> bool:
        if not self._potion_crafting_enabled():
            return False
        return config_enabled(self._config, "enable_potion_switching")

    def _potion_rotation_filenames(self) -> list[str]:
        files: list[str] = []
        for key in ("potion_file_1", "potion_file_2", "potion_file_3"):
            raw = self._config.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            try:
                normalized = potion_filename(raw.strip())
            except ValueError:
                continue
            if normalized not in files:
                files.append(normalized)
        return files

    def _sync_potion_rotation_index(self) -> None:
        rotation = self._potion_rotation_filenames()
        if not rotation:
            self._potion_rotation_index = 0
            return
        for key in ("potion_last_file", "selected_potion_file"):
            raw = self._config.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            try:
                normalized = potion_filename(raw.strip())
            except ValueError:
                continue
            if normalized in rotation:
                self._potion_rotation_index = rotation.index(normalized)
                return
        self._potion_rotation_index = 0

    def _active_potion_name(self) -> str | None:
        if self._potion_switching_enabled():
            rotation = self._potion_rotation_filenames()
            if rotation:
                idx = self._potion_rotation_index % len(rotation)
                return Path(rotation[idx]).stem.strip()
        filename = self._selected_potion_file()
        if not filename:
            return None
        return Path(filename).stem.strip()

    def _persist_potion_rotation_state(self, filename: str) -> None:
        self._config["potion_last_file"] = filename
        self._config["selected_potion_file"] = filename
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(
                json.dumps(self._config, indent=2),
                encoding="utf-8",
            )
        except OSError as error:
            print(f"[main macro] could not save active potion to config: {error}")

    def _advance_potion_rotation(self) -> None:
        rotation = self._potion_rotation_filenames()
        if len(rotation) < 2:
            return
        self._potion_rotation_index = (self._potion_rotation_index + 1) % len(rotation)
        current = rotation[self._potion_rotation_index]
        self._persist_potion_rotation_state(current)
        print(
            f"[main macro] switched to {Path(current).stem} "
            f"({self._potion_rotation_index + 1}/{len(rotation)})"
        )

    def _macro_potion_tasks_enabled(self) -> bool:
        return self._potion_crafting_enabled()

    @property
    def _window(self) -> webview.Window:
        return webview.windows[0]

    def get_config(self):
        cfg = deepcopy(self._config)
        migrate_biome_webhook_config(cfg)
        return cfg

    def save_config(self, config):
        previous_keys = self._macro_hotkey_pair()
        self._config = dict(config or {})
        migrate_biome_webhook_config(self._config)
        self._sync_potion_switching_with_craft(persist=False)
        if config_enabled(self._config, "enable_potion_crafting"):
            self._remove_currency_screenshot_file()
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            json.dumps(self._config, indent=2),
            encoding="utf-8",
        )
        if self._macro_hotkey_pair() != previous_keys:
            self._hotkeys.reload()
        if "always_on_top" in self._config:
            self._apply_always_on_top(config_enabled(self._config, "always_on_top"))
        return True

    def _macro_hotkey_pair(self) -> tuple[str | None, str | None]:
        return (
            resolve_hotkey_setting(self._config, "macro_start_hotkey", DEFAULT_MACRO_START_KEY),
            resolve_hotkey_setting(self._config, "macro_stop_hotkey", DEFAULT_MACRO_STOP_KEY),
        )

    def _notify_shortcut(self, action: str) -> None:
        try:
            self._window.evaluate_js(
                "(() => {"
                f"const action = {json.dumps(action)};"
                "if (window.onShortcutEvent) window.onShortcutEvent(action);"
                "if (window.BlossomMacroLabels?.refresh) window.BlossomMacroLabels.refresh();"
                "})();"
            )
        except Exception as error:
            print(f"[macro hotkeys] UI notify failed: {error}")

    def _valid_calibration_key(self, key) -> str | None:
        cleaned = str(key or "").strip()
        if not CALIBRATION_KEY_RE.fullmatch(cleaned):
            return None
        return cleaned

    def focus_macro_window(self) -> bool:
        hwnd = int(getattr(self._window, "handle", 0) or 0)
        if hwnd and self._hotkeys._force_foreground(hwnd):
            print("[macro focus] focused main window via handle")
            return True

        try:
            import pygetwindow as gw
        except ImportError:
            print("[macro focus] pygetwindow missing")
            return False

        keywords = ("coteab", "blossom")
        try:
            for window in gw.getAllWindows():
                title = (window.title or "").strip().lower()
                if not title or "roblox" in title:
                    continue
                if any(word in title for word in keywords) and "macro" in title:
                    target_hwnd = int(getattr(window, "_hWnd", 0) or 0)
                    if target_hwnd and self._hotkeys._force_foreground(target_hwnd):
                        print(f"[macro focus] focused {window.title!r}")
                        return True
                    try:
                        window.activate()
                        time.sleep(0.18)
                        return True
                    except Exception:
                        continue
        except Exception as error:
            print(f"[macro focus] scan failed: {error}")
        print("[macro focus] could not focus macro window")
        return False

    def _clear_calibration_hotkey(self) -> None:
        if self._calibration_hotkey is None:
            return
        try:
            import keyboard

            keyboard.remove_hotkey(self._calibration_hotkey)
        except Exception:
            pass
        self._calibration_hotkey = None

    def _store_calibration_value(self, key: str, value: list[int], mode: str) -> None:
        self._config[key] = value
        patch = apply_calibration_side_effects(self._config, key, value)
        if patch:
            self._config.update(patch)
        self.save_config(self._config)
        self._calibration_capture_seq += 1
        self._calibration_capture_state = {
            "seq": self._calibration_capture_seq,
            "key": key,
            "value": value,
            "mode": mode,
            "timestamp": int(time.time() * 1000),
        }
        print(f"[calibration] {key} = {value} ({mode})")
        self._emit_calibration_result(key, value, mode)

    def _run_drag_calibration_session(self, key: str, mode: str = "region") -> None:
        cleaned = self._valid_calibration_key(key)
        if not cleaned:
            return

        capture_mode = "region" if str(mode).lower() == "region" else "point"
        try:
            roblox_focused = self._hotkeys.focus_roblox()
            time.sleep(0.35)
            dragged = capture_region_drag()
            if dragged is None:
                print(f"[calibration] {cleaned} cancelled")
                return

            if capture_mode == "point":
                left, top, width, height = dragged
                value = [
                    int(left + width // 2),
                    int(top + height // 2),
                    1,
                    1,
                ]
            else:
                value = [int(v) for v in dragged]

            self._store_calibration_value(cleaned, value, capture_mode)
        except Exception as error:
            print(f"[calibration] {cleaned} failed: {error}")
        finally:
            macro_focused = self.focus_macro_window()
            self._calibration_capture_active = False

    def _start_drag_calibration(self, key: str, mode: str = "region") -> dict:
        cleaned = self._valid_calibration_key(key)
        if not cleaned:
            return {"ok": False, "error": "Unsupported calibration key"}
        if self._calibration_capture_active:
            return {"ok": False, "error": "Calibration already in progress"}

        self._clear_calibration_hotkey()
        self._calibration_capture_active = True
        Thread(
            target=self._run_drag_calibration_session,
            args=(cleaned, mode),
            daemon=True,
        ).start()
        return {
            "ok": True,
            "status": "Switched to Roblox — drag a box over the button (ESC cancels)",
            "key": cleaned,
            "mode": mode,
            "seq": self._calibration_capture_seq,
        }

    def _emit_calibration_result(self, key: str, value: list[int], mode: str) -> None:
        payload = json.dumps({"key": key, "value": value, "mode": mode})
        try:
            self._window.evaluate_js(
                f"if (window.onCalibrationResult) window.onCalibrationResult({payload});"
            )
        except Exception as error:
            print(f"[calibration] UI notify failed: {error}")

    def create_calibration_window(self, key, mode="point"):
        cleaned = self._valid_calibration_key(key)
        capture_mode = "region" if str(mode).lower() == "region" else "point"
        if not cleaned:
            return {"ok": False, "error": "Unsupported calibration key"}
        return self._start_drag_calibration(cleaned, capture_mode)

    def _evaluate_js(self, script: str) -> None:
        try:
            self._window.evaluate_js(script)
        except Exception as error:
            print(f"[update] UI notify failed: {error}")

    def _notify_update_available(self, version: str, url: str) -> None:
        v, u = json.dumps(version), json.dumps(url)
        self._evaluate_js(
            f"if (window.BlossomUpdate?.prompt) window.BlossomUpdate.prompt({v}, {u});"
            f" else if (window.onUpdateAvailable) window.onUpdateAvailable({v}, {u});"
        )

    def _notify_update_status(self, status: str) -> None:
        self._evaluate_js(
            f"if (window.onUpdateStatus) window.onUpdateStatus({json.dumps(status)});"
        )

    def _notify_download_progress(
        self, percent: float, downloaded: int, total: int
    ) -> None:
        """Push live download progress to the update overlay.

        percent is -1 when the total size is unknown (no Content-Length), which
        the frontend renders as an indeterminate bar.
        """
        self._evaluate_js(
            "if (window.BlossomUpdate?.onDownloadProgress) "
            f"window.BlossomUpdate.onDownloadProgress({percent}, {downloaded}, {total});"
        )

    def _make_download_progress_cb(self):
        """Throttled (~10/sec) progress callback for apply_exe_update.

        Runs on the dedicated update thread, so the brief evaluate_js call here
        never touches the macro threads. Start (0) and final (100/complete)
        frames are always sent; intermediate frames are rate-limited.
        """
        last_emit = [0.0]

        def callback(downloaded: int, total: int) -> None:
            total_i = int(total or 0)
            downloaded_i = int(downloaded or 0)
            if total_i > 0:
                percent = round(downloaded_i / total_i * 100, 1)
                final = downloaded_i >= total_i
            else:
                percent = -1
                final = False
            now = time.monotonic()
            if not final and downloaded_i > 0 and (now - last_emit[0]) < 0.1:
                return
            last_emit[0] = now
            self._notify_download_progress(percent, downloaded_i, total_i)

        return callback

    def _reveal_in_explorer(self, path: str) -> None:
        """Open Explorer with the staged installer selected (manual reinstall)."""
        target = str(path or "").strip()
        if not target or not Path(target).exists():
            return
        try:
            subprocess.Popen(["explorer", "/select,", target])
        except Exception as error:
            print(f"[update] could not open file location: {error}")

    def _notify_update_check_state(self, state: str) -> None:
        """Quiet, non-modal hint about the check itself (ok/checking/offline)."""
        self._update_last_status = state
        self._evaluate_js(
            "if (window.onUpdateCheckState) "
            f"window.onUpdateCheckState({json.dumps(state)});"
        )

    def _updates_disabled(self) -> bool:
        return bool(self._config.get("dont_ask_for_update"))

    def _run_update_check(self) -> None:
        if self._updates_disabled():
            return
        if self._update_check_running:
            return
        self._update_check_running = True
        self._notify_update_check_state("checking")
        try:
            last_error: str | None = None
            for attempt in range(UPDATE_CHECK_ATTEMPTS):
                try:
                    result = check_update_status()
                except Exception as error:  # defensive: never crash the thread
                    result = {"ok": False, "error": str(error)}
                if result.get("ok"):
                    release = result.get("release")
                    if release:
                        self._update_cache = release
                        self._notify_update_available(release["version"], release["url"])
                    self._notify_update_check_state("ok")
                    return
                last_error = result.get("error")
                if attempt < UPDATE_CHECK_ATTEMPTS - 1:
                    delay_idx = min(attempt, len(UPDATE_CHECK_BACKOFF_SEC) - 1)
                    self._update_recheck_stop.wait(UPDATE_CHECK_BACKOFF_SEC[delay_idx])
            # All attempts failed to reach GitHub: surface quietly, don't nag.
            print(f"[update] check unreachable after retries: {last_error}")
            self._notify_update_check_state("offline")
        finally:
            self._update_check_running = False

    def _update_recheck_loop(self) -> None:
        """Single daemon thread: sleep a long interval, then re-run the check.

        Sleeping costs effectively nothing. Keeps rechecking for the life of the
        app (only stopping when updates are disabled) so a release published
        while the app is open still surfaces the popup. _run_update_check
        re-notifies on each find; the frontend suppresses an already-dismissed
        version and shows newly published ones. No tight polling: the interval
        is long (UPDATE_RECHECK_SECONDS).
        """
        while not self._update_recheck_stop.wait(UPDATE_RECHECK_SECONDS):
            if self._updates_disabled():
                return
            self._run_update_check()

    def _start_update_rechecker(self) -> None:
        if self._update_recheck_thread and self._update_recheck_thread.is_alive():
            return
        if self._updates_disabled():
            return
        thread = Thread(target=self._update_recheck_loop, daemon=True)
        self._update_recheck_thread = thread
        thread.start()

    def get_macro_version(self):
        return display_version()

    def get_version_info(self):
        return version_info()

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
        if self._is_fishing_mode_enabled():
            incompatibilities.append(
                "Fishing mode is active — merchant, quests, potion craft, obby, BR/SC, and biome selector are paused; fishing runs on its own thread."
            )
        if self._potion_crafting_enabled() and self._is_fishing_mode_enabled():
            incompatibilities.append(
                "Potion Crafting is enabled: it takes priority over Fishing Mode, so fishing will not run until crafting is off."
            )
        if self._config.get("teleport_portable_crack") and (
            self._config.get("fishing_mode")
            or self._potion_crafting_enabled()
            or self._auto_obby_enabled()
        ):
            incompatibilities.append(
                "Portable Crack teleport only works when fishing mode, potion crafting, auto obby, "
                "and auto egg pathing are OFF."
            )

        return {"modules": modules, "incompatibilities": incompatibilities}

    def get_session_stats(self):
        """Lightweight live stats for the floating Stats side panel."""
        try:
            modules = (self.get_active_modules() or {}).get("modules", {})
        except Exception:
            modules = {}
        enabled = sum(1 for m in modules.values() if isinstance(m, dict) and m.get("enabled"))
        active = sum(1 for m in modules.values() if isinstance(m, dict) and m.get("active"))
        running = bool(self._macro_running)
        started = self._macro_started_at if running else None
        uptime = (time.time() - started) if started else 0.0
        return {
            "running": running,
            "version": display_version(),
            "uptime_seconds": round(uptime, 1),
            "enabled_modules": enabled,
            "active_modules": active,
            "total_modules": len(modules),
            "always_on_top": config_enabled(self._config, "always_on_top"),
        }

    def get_update_available(self):
        if self._updates_disabled():
            return None
        # Always keep the long-interval rechecker alive so a release published
        # while the app is open still surfaces later.
        self._start_update_rechecker()
        release = self._update_cache or check_newer_than_local()
        if release:
            self._update_cache = release
            # Drive the popup directly. The React startup path calls this and
            # returns early without going through check_for_updates, so without
            # this notify the redesigned popup would never appear on startup.
            self._notify_update_available(release["version"], release["url"])
            return dict(release)
        return None

    def check_for_updates(self):
        if self._updates_disabled():
            return {"available": False, "skipped": True}
        self._start_update_rechecker()
        if self._update_cache:
            self._notify_update_available(
                self._update_cache["version"],
                self._update_cache["url"],
            )
            return {"available": True, **self._update_cache}
        Thread(target=self._run_update_check, daemon=True).start()
        return {"available": False, "checking": True}

    def get_update_check_state(self):
        """Quiet status for the UI / manual check: ok, checking, or offline."""
        return {
            "state": self._update_last_status,
            "available": bool(self._update_cache),
            "checking": self._update_check_running,
        }

    def apply_update(self, url: str, version: str | None = None) -> dict:
        if not is_frozen_build():
            webbrowser.open(
                f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
            )
            return {
                "ok": False,
                "dev_mode": True,
                "error": "Dev build cannot auto-install. Opened releases page in browser.",
            }

        download_url = str(url or "").strip()
        if not download_url:
            cached = self._update_cache or fetch_latest_release()
            if cached:
                download_url = cached.get("url", "")
                version = version or cached.get("version")
        if not download_url:
            self._notify_update_status("failed")
            return {"ok": False, "error": "No download URL"}

        self._notify_update_status("downloading")
        self._notify_download_progress(-1, 0, 0)

        def work() -> None:
            try:
                cached = self._update_cache or fetch_latest_release()
                asset_name = (cached or {}).get("asset_name")
                reinstall_required = bool((cached or {}).get("reinstall_required"))
                result = apply_exe_update(
                    INSTALL_ROOT,
                    download_url,
                    frozen=getattr(sys, "frozen", False),
                    target_exe_name=asset_name,
                    progress_cb=self._make_download_progress_cb(),
                    reinstall_required=reinstall_required,
                )
                if not result.get("ok"):
                    if result.get("dev_mode"):
                        webbrowser.open(
                            f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
                        )
                    self._notify_update_status("failed")
                    print(f"[update] {result.get('error', 'failed')}")
                    return
                version_label = str(version or "").strip() or APP_VERSION
                if result.get("reinstall"):
                    staged_path = str(result.get("path") or "")
                    self._reveal_in_explorer(staged_path)
                    self._notify_update_status(f"manual|{version_label}|{staged_path}")
                    return
                self._notify_update_status(f"done|{version_label}")
                time.sleep(0.35)
                self.close_window()
            except Exception as error:
                print(f"[update] apply failed: {error}")
                self._notify_update_status("failed")

        Thread(target=work, daemon=True).start()
        return {"ok": True, "started": True}

    # ----------------------------------------------------------------- #
    # OpenCV ("fishing vision") runtime — explicit in-app installer
    # ----------------------------------------------------------------- #
    def _notify_install_state(self, state: str, message: str = "") -> None:
        self._evaluate_js(
            "if (window.BlossomRuntime?.onInstallState) "
            f"window.BlossomRuntime.onInstallState({json.dumps(state)}, {json.dumps(message)});"
        )

    def _notify_install_progress(
        self, percent: float, downloaded: int, total: int
    ) -> None:
        """Push live install download progress to the runtime installer card.

        percent is -1 when the total size is unknown (no Content-Length), which
        the frontend renders as an indeterminate bar.
        """
        self._evaluate_js(
            "if (window.BlossomRuntime?.onInstallProgress) "
            f"window.BlossomRuntime.onInstallProgress({percent}, {downloaded}, {total});"
        )

    def _make_install_progress_cb(self):
        """Throttled (~10/sec) progress callback for the OpenCV install.

        Runs on the dedicated install thread, so the brief evaluate_js call here
        never touches the macro threads. Final frame is always sent; intermediate
        frames are rate-limited.
        """
        last_emit = [0.0]

        def callback(downloaded: int, total: int) -> None:
            total_i = int(total or 0)
            downloaded_i = int(downloaded or 0)
            if total_i > 0:
                percent = round(downloaded_i / total_i * 100, 1)
                final = downloaded_i >= total_i
            else:
                percent = -1
                final = False
            now = time.monotonic()
            if not final and downloaded_i > 0 and (now - last_emit[0]) < 0.1:
                return
            last_emit[0] = now
            self._notify_install_progress(percent, downloaded_i, total_i)

        return callback

    def get_opencv_status(self) -> dict:
        """Status of the optional OpenCV runtime, without forcing a download.

        While an install is in flight this returns ``state="installing"`` so the
        UI stays consistent if it re-checks; otherwise it reflects the on-disk
        verified cache (installed / not_installed / unavailable).
        """
        with self._opencv_install_lock:
            installing = self._opencv_installing
        if installing:
            return {"state": "installing", "abi": abi_key()}
        try:
            return cv2_status()
        except Exception as error:  # defensive: never crash the bridge
            return {"state": "error", "abi": abi_key(), "message": str(error)}

    def install_opencv(self) -> dict:
        """Explicitly download + verify + load the OpenCV runtime on a daemon.

        Idempotent and concurrency-guarded: a second call while a install is
        running is a no-op. Progress and final state are pushed to the UI via
        ``window.BlossomRuntime.onInstallProgress`` / ``onInstallState``. On
        failure (e.g. asset not uploaded yet, offline, hash mismatch) the macro
        keeps working through its built-in NumPy fallback.
        """
        with self._opencv_install_lock:
            if self._opencv_installing:
                return {"ok": True, "started": False, "already_running": True}
            current = cv2_status()
            if current.get("state") == "unavailable":
                # Nothing verified to install for this build/ABI yet.
                self._notify_install_state(
                    "unavailable",
                    current.get("message")
                    or "No verified vision component is published for this build yet.",
                )
                return {"ok": False, "state": "unavailable", **current}
            self._opencv_installing = True

        self._notify_install_state("installing", "Preparing download…")
        self._notify_install_progress(-1, 0, 0)

        def work() -> None:
            try:
                module = ensure_opencv(
                    progress_cb=self._make_install_progress_cb(), force=True
                )
                if module is not None:
                    status = cv2_status()
                    version = status.get("version")
                    msg = (
                        f"Installed (OpenCV {version})."
                        if version
                        else "Installed."
                    )
                    self._notify_install_progress(100, 0, 0)
                    self._notify_install_state("installed", msg)
                    return
                # ensure_opencv returned None: figure out why for a clear message.
                status = cv2_status()
                if status.get("state") == "unavailable":
                    self._notify_install_state(
                        "unavailable",
                        status.get("message")
                        or "Component not available yet; using built-in fallback.",
                    )
                else:
                    self._notify_install_state(
                        "error",
                        "Could not download or verify the component yet. "
                        "Fishing still works using the built-in fallback.",
                    )
            except Exception as error:  # noqa: BLE001 - report, never crash thread
                print(f"[runtime] opencv install failed: {error}")
                self._notify_install_state(
                    "error",
                    "Install failed. Fishing still works using the built-in fallback.",
                )
            finally:
                with self._opencv_install_lock:
                    self._opencv_installing = False

        thread = Thread(target=work, daemon=True)
        self._opencv_install_thread = thread
        thread.start()
        return {"ok": True, "started": True}

    def boot_install_runtime_deps(self) -> None:
        """Check for required optional runtime deps on boot and install them.

        The Discord bot no longer brokers these dependencies — the app owns the
        whole flow now. On startup we check the verified on-disk cache and, if a
        component is missing but a verified build exists for this Python/arch, we
        fetch it on a daemon thread so it is ready before the user needs it
        (e.g. fishing vision). Everything degrades to the built-in fallback, so a
        failed or offline check never blocks launch.
        """

        def _check_and_install() -> None:
            try:
                status = cv2_status()
            except Exception as error:  # noqa: BLE001 - boot must never crash
                print(f"[runtime] boot dependency check failed: {error}")
                return
            state = status.get("state")
            if state == "installed":
                print("[runtime] boot dependency check: OpenCV already present.")
                return
            if state == "unavailable":
                # No verified build pinned for this ABI; fishing uses the fallback.
                print(
                    "[runtime] boot dependency check: no verified vision "
                    f"component for this build ({status.get('abi')}); using fallback."
                )
                return
            print("[runtime] boot dependency check: installing OpenCV runtime…")
            self.install_opencv()

        Thread(
            target=_check_and_install, name="BlossomBootDeps", daemon=True
        ).start()

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

    def add_potion(self, name: str) -> dict:
        try:
            filename = potion_filename(name)
        except ValueError as error:
            return {"ok": False, "error": str(error)}

        path = POTION_DIR / filename
        stem = Path(filename).stem
        created = not path.exists()
        if created:
            save_macro_json(path, {"name": stem, "registered": True})
            print(f"[potion] added {path}")
        return {
            "ok": True,
            "filename": filename,
            "name": stem,
            "created": created,
            "message": f"Added {stem}" if created else f"{stem} is already in your list",
        }

    def delete_potion(self, name: str) -> dict:
        try:
            filename = potion_filename(name)
        except ValueError as error:
            return {"ok": False, "error": str(error)}

        path = POTION_DIR / filename
        if not path.exists():
            return {"ok": False, "error": f"{filename} not found"}

        try:
            path.unlink()
        except OSError as error:
            return {"ok": False, "error": str(error)}

        stem = Path(filename).stem
        for key in ("selected_potion_file", "potion_last_file", "potion_file_1", "potion_file_2", "potion_file_3"):
            if self._config.get(key) == filename:
                self._config[key] = ""
        self.save_config(self._config)
        print(f"[potion] removed {path}")
        return {"ok": True, "filename": filename, "message": f"Removed {stem}"}

    def get_macro_hotkeys(self) -> dict:
        start, stop = self._macro_hotkey_pair()
        return {
            "start": start or "",
            "stop": stop or "",
            "start_display": self._hotkey_display(start),
            "stop_display": self._hotkey_display(stop),
            "default_start": DEFAULT_MACRO_START_KEY,
            "default_stop": DEFAULT_MACRO_STOP_KEY,
            "default_start_display": self._hotkey_display(DEFAULT_MACRO_START_KEY),
            "default_stop_display": self._hotkey_display(DEFAULT_MACRO_STOP_KEY),
        }

    def _hotkey_display(self, key: str | None) -> str:
        if not key:
            return "No bind"
        parts = [part.strip() for part in str(key).split("+") if part.strip()]
        return " + ".join(part[:1].upper() + part[1:] if part else part for part in parts)

    def _apply_hotkey_slot(self, config_key: str, value: object) -> str | None:
        if value is None:
            return None
        if is_unbound_hotkey(value):
            self._config[config_key] = ""
            return None
        normalized = normalize_hotkey(str(value))
        self._config[config_key] = normalized
        return normalized

    def _macro_hotkeys_response(self, *, ok: bool = True, error: str | None = None) -> dict:
        start, stop = self._macro_hotkey_pair()
        payload = {
            "ok": ok,
            "start": start or "",
            "stop": stop or "",
            "start_display": self._hotkey_display(start),
            "stop_display": self._hotkey_display(stop),
            "default_start": DEFAULT_MACRO_START_KEY,
            "default_stop": DEFAULT_MACRO_STOP_KEY,
            "default_start_display": self._hotkey_display(DEFAULT_MACRO_START_KEY),
            "default_stop_display": self._hotkey_display(DEFAULT_MACRO_STOP_KEY),
        }
        if error:
            payload["error"] = error
        return payload

    def set_macro_hotkeys(self, payload: dict | None = None, **kwargs) -> dict:
        data = dict(payload or {})
        data.update(kwargs)
        snapshot = deepcopy(self._config)

        if data.get("reset"):
            self._config.pop("macro_start_hotkey", None)
            self._config.pop("macro_stop_hotkey", None)
            self.save_config(self._config)
            self._hotkeys.reload()
            return self._macro_hotkeys_response()

        rewrite = bool(data.get("rewrite"))
        has_start = "start_key" in data or "start" in data
        has_stop = "stop_key" in data or "stop" in data
        start_key = data.get("start_key") if "start_key" in data else data.get("start")
        stop_key = data.get("stop_key") if "stop_key" in data else data.get("stop")

        try:
            if rewrite and has_start and has_stop:
                self._apply_hotkey_slot("macro_start_hotkey", start_key)
                self._apply_hotkey_slot("macro_stop_hotkey", stop_key)
            else:
                if has_start:
                    self._apply_hotkey_slot("macro_start_hotkey", start_key)
                if has_stop:
                    self._apply_hotkey_slot("macro_stop_hotkey", stop_key)
        except ValueError as error:
            self._config = snapshot
            return self._macro_hotkeys_response(ok=False, error=str(error))

        start, stop = self._macro_hotkey_pair()
        if start and stop and start == stop:
            self._config = snapshot
            return self._macro_hotkeys_response(
                ok=False,
                error="Start and stop hotkeys must be different",
            )

        self.save_config(self._config)
        self._hotkeys.reload()
        return self._macro_hotkeys_response()

    def check_obby_path_exists(self):
        for folder in OBBY_PATHS_DIRS:
            if folder.is_dir() and any(folder.glob("*.json")):
                return True
        return False

    def _path_filename(self, name: str | None) -> str:
        stem = Path(str(name or "obby").strip()).stem or "obby"
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", stem):
            raise ValueError("Path name must be 1-64 letters, numbers, underscore, or hyphen")
        return f"{stem}.json"

    def _resolve_path_file(self, name: str | None) -> Path | None:
        filename = self._path_filename(name)
        for folder in OBBY_PATHS_DIRS:
            candidate = folder / filename
            if candidate.is_file():
                return candidate
        return None

    def list_path_files(self) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for folder in OBBY_PATHS_DIRS:
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.json")):
                if ".manifest" in path.name:
                    continue
                stem = path.stem
                if stem not in seen:
                    seen.add(stem)
                    names.append(stem)
        return names

    def _hotkey_main_start(self) -> None:
        start_key, _ = self._macro_hotkey_pair()
        print(f"[main macro] {start_key} pressed")
        self.set_biome_detection(True)
        self._notify_shortcut("START")

    def _emergency_stop(self) -> None:
        """Stop hotkey: cancel everything immediately (safe to call repeatedly)."""
        was_running = self._macro_running
        self._macro_stop.set()
        self._stop_fishing_worker()
        self._replayer.cancel()
        self._macro_running = False
        self._macro_session_gate.force_release()
        release_stuck_inputs(reason="stop hotkey")
        if was_running:
            self._send_status_notif("stopped")

    def _is_fishing_mode_enabled(self) -> bool:
        if config_enabled(self._config, "enable_idle_mode"):
            return False
        return config_enabled(self._config, "fishing_mode")

    def _fishing_can_run(self) -> bool:
        if not self._macro_running or self._macro_stop.is_set():
            return False
        if not self._is_fishing_mode_enabled():
            return False
        if self._potion_crafting_enabled():
            return False
        if self._replayer.is_running:
            return False
        owner = self._macro_session_gate.owner()
        if owner is not None and not str(owner).startswith("fishing:"):
            return False
        return True

    def _fishing_config_provider(self) -> dict:
        self._reload_config_from_disk()
        return dict(self._config)

    def _fishing_calibration_issues(self) -> list[str]:
        required_points = (
            "fishing_detect_pixel",
            "fishing_click_position",
            "fishing_midbar_sample_pos",
            "fishing_close_button_pos",
            "collections_button",
            "exit_collections_button",
        )
        missing: list[str] = []
        region = self._config.get("fishing_bar_region")
        if not isinstance(region, (list, tuple)) or len(region) < 4:
            missing.append("fishing_bar_region")
        for key in required_points:
            if self._calibration_point(key) is None:
                missing.append(key)
        return missing

    def _on_fishing_failsafe_timeout(self) -> None:
        print(
            "[FishingMode] Failsafe: no minigame for 60s — "
            "enable Auto Reconnect + fishing failsafe rejoin in settings (rejoin handler pending)."
        )

    def _fishing_close_chat(self) -> None:
        self._reload_config_from_disk()
        close_roblox_chat_from_config(self._config)

    def _fishing_replay_movement_path(self, stem: str) -> bool:
        if not self._resolve_path_file(stem):
            return False
        with self._macro_session(f"fishing:{stem}") as acquired:
            if not acquired:
                return False
            result = self._replay_recording_impl(stem)
        ok = not str(result).startswith("Error") and result != "Cancelled"
        if ok:
            print(f"[FishingMode] replayed path {stem}: {result}")
        else:
            print(f"[FishingMode] path {stem} failed: {result}")
        return ok

    def _fishing_merchant_ocr_check(self) -> None:
        if not config_enabled(self._config, "fishing_use_merchant_ocr_every_x_fish"):
            return
        self._reload_config_from_disk()
        with self._macro_session("fishing:merchant_ocr") as acquired:
            if not acquired:
                print("[FishingMode] merchant OCR skipped: macro session busy")
                return
            self._run_merchant_tasks(reason="fishing-merchant-ocr")

    def _run_fishing_br_sc_sequence(self) -> bool:
        ran = False
        if config_enabled(self._config, "strange_controller"):
            result = run_use_item(
                SC_ITEM_NAME,
                config=self._config,
                get_point=self._calibration_point,
                focus_roblox=self._hotkeys.focus_roblox,
                cancel_event=self._fishing_stop_event,
                reason="fishing-sc",
            )
            ran = ran or str(result).startswith("OK")
        if config_enabled(self._config, "biome_randomizer"):
            result = run_use_item(
                BR_ITEM_NAME,
                config=self._config,
                get_point=self._calibration_point,
                focus_roblox=self._hotkeys.focus_roblox,
                cancel_event=self._fishing_stop_event,
                reason="fishing-br",
            )
            ran = ran or str(result).startswith("OK")
        return ran

    def _run_fishing_merchant_sequence(self) -> bool:
        self._fishing_runtime_state["merchant_requires_reset"] = False
        if not (
            config_enabled(self._config, "merchant_teleporter")
            or config_enabled(self._config, "auto_merchant_teleporter")
        ):
            print("[FishingMode] merchant sequence skipped: teleporter not enabled")
            return False
        try:
            self._hotkeys.focus_roblox()
        except Exception:
            pass
        ran = False
        try:
            result = run_merchant_teleporter(
                config=self._config,
                get_point=self._merchant_calibration_point,
                get_region=self._calibration_region,
                focus_roblox=self._hotkeys.focus_roblox,
                cancel_event=self._fishing_stop_event,
                reason="fishing-merchant",
            )
            ran = str(result).startswith("OK")
            print(f"[FishingMode] merchant teleporter result: {result}")
        except Exception as error:
            print(f"[FishingMode] merchant sequence failed: {error}")
        return ran

    def _start_fishing_worker(self) -> None:
        with self._fishing_lock:
            if self._fishing_thread and self._fishing_thread.is_alive():
                return
            self._fishing_stop_event.clear()

            def _run_fishing() -> None:
                try:
                    run_fishing_loop(
                        stop_event=self._fishing_stop_event,
                        can_run_cb=self._fishing_can_run,
                        config_provider=self._fishing_config_provider,
                        log_prefix="[FishingMode]",
                        print_start_stop=True,
                        on_failsafe_timeout=self._on_fishing_failsafe_timeout,
                        run_br_sc_sequence_cb=self._run_fishing_br_sc_sequence,
                        run_merchant_sequence_cb=self._run_fishing_merchant_sequence,
                        merchant_ocr_check_cb=self._fishing_merchant_ocr_check,
                        activate_roblox_cb=self._hotkeys.focus_roblox,
                        close_chat_fn=self._fishing_close_chat,
                        replay_movement_path_cb=self._fishing_replay_movement_path,
                        runtime_state=self._fishing_runtime_state,
                        set_fishing_busy_cb=lambda busy: setattr(
                            self, "_fishing_busy", bool(busy)
                        ),
                        on_f2_pressed_cb=self._hotkey_main_stop,
                    )
                except Exception as error:
                    print(f"[FishingMode] worker failed: {error}")

            self._fishing_thread = Thread(target=_run_fishing, daemon=True)
            self._fishing_thread.start()

    def _stop_fishing_worker(self) -> None:
        with self._fishing_lock:
            self._fishing_stop_event.set()
            thread = self._fishing_thread
            # Never join from within the fishing thread itself (the worker can
            # trigger an emergency stop via its F2 callback) — that would raise.
            if (
                thread
                and thread.is_alive()
                and thread is not threading.current_thread()
            ):
                thread.join(timeout=1.5)
            if not thread or not thread.is_alive():
                self._fishing_thread = None
            self._fishing_busy = False

    def _sync_fishing_worker(self) -> None:
        if self._is_fishing_mode_enabled() and self._macro_running:
            self._start_fishing_worker()
        else:
            self._stop_fishing_worker()

    # ── Auto Eden (port of the original Noteab eden OCR loop) ────────────
    def _auto_eden_enabled(self) -> bool:
        return auto_eden_enabled(self._config, config_enabled=config_enabled)

    def _eden_config_provider(self) -> dict:
        self._reload_config_from_disk()
        return dict(self._config)

    def _eden_can_run(self) -> bool:
        if not self._macro_running or self._macro_stop.is_set():
            return False
        # Don't fight other interactive tasks for the screen / cursor.
        if self._replayer.is_running or getattr(self, "_fishing_busy", False):
            return False
        if self._potion_crafting_enabled():
            return False
        if self._macro_session_gate.owner() is not None:
            return False
        return True

    def _send_eden_alert(self, screenshot_path: str | None) -> None:
        """Send the Discord 'Eden has appeared' ping (faithful to the original)."""
        urls = self._webhook_urls()
        if not urls:
            print("[AutoEden] Eden detected but no webhook configured.")
            return
        ping = self._config.get("eden_user_id") if self._config.get("ping_eden") else None

        def _send() -> None:
            try:
                send_eden_webhook(urls, ping=ping, screenshot_path=screenshot_path)
            except Exception as error:  # noqa: BLE001
                print(f"[AutoEden] webhook send failed: {error}")

        Thread(target=_send, name="BlossomEdenWebhook", daemon=True).start()

    def _start_eden_worker(self) -> None:
        with self._eden_lock:
            if self._eden_thread and self._eden_thread.is_alive():
                return
            self._eden_stop_event.clear()

            def _run_eden() -> None:
                try:
                    run_auto_eden_loop(
                        stop_event=self._eden_stop_event,
                        can_run_cb=self._eden_can_run,
                        config_provider=self._eden_config_provider,
                        config_enabled=config_enabled,
                        focus_roblox_cb=self._hotkeys.focus_roblox,
                        send_eden_alert_cb=self._send_eden_alert,
                        log_prefix="[AutoEden]",
                    )
                except Exception as error:  # noqa: BLE001
                    print(f"[AutoEden] worker failed: {error}")

            self._eden_thread = Thread(target=_run_eden, daemon=True)
            self._eden_thread.start()

    def _stop_eden_worker(self) -> None:
        with self._eden_lock:
            self._eden_stop_event.set()
            thread = self._eden_thread
            if (
                thread
                and thread.is_alive()
                and thread is not threading.current_thread()
            ):
                thread.join(timeout=1.5)
            if not thread or not thread.is_alive():
                self._eden_thread = None

    def _sync_eden_worker(self) -> None:
        if self._auto_eden_enabled() and self._macro_running:
            self._start_eden_worker()
        else:
            self._stop_eden_worker()

    def _hotkey_main_stop(self) -> None:
        _, stop_key = self._macro_hotkey_pair()
        print(f"[main macro] {stop_key} pressed — emergency stop")
        self._emergency_stop()
        self._config["enable_biome_detection"] = False
        self._notify_shortcut("STOP")

    def _selected_potion_file(self) -> str | None:
        """Single-potion mode: selected / last only (not switch slots #1–#3)."""
        for key in ("selected_potion_file", "potion_last_file"):
            raw = self._config.get(key)
            if isinstance(raw, str) and raw.strip():
                try:
                    return potion_filename(raw.strip())
                except ValueError:
                    continue
        return None

    def _selected_potion_name(self) -> str | None:
        return self._active_potion_name()

    def _calibration_point(self, key: str, *, fallback: str | None = None) -> tuple[int, int] | None:
        value = self._config.get(key)
        if value is None and fallback:
            value = self._config.get(fallback)
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return None
        try:
            if len(value) >= 4:
                left = float(value[0])
                top = float(value[1])
                width = float(value[2])
                height = float(value[3])
                x = int(round(left + width / 2))
                y = int(round(top + height / 2))
            else:
                x = int(round(float(value[0])))
                y = int(round(float(value[1])))
        except (TypeError, ValueError):
            return None
        if x <= 0 and y <= 0:
            return None
        return x, y

    def _calibration_region(self, key: str, *, fallback: str | None = None) -> tuple[int, int, int, int] | None:
        value = self._config.get(key)
        if value is None and fallback:
            value = self._config.get(fallback)
        return parse_calibration_region(value)

    def _click_green_guard_button_if_needed(
        self,
        point: tuple[int, int],
        calibration_key: str,
        *,
        label: str,
    ) -> tuple[bool, str | None]:
        """Global rule: skip click when a green-guarded button is already active."""
        if self._macro_stop.is_set():
            return False, "Cancelled"
        if not _sleep_sec(0.08, self._macro_stop):
            return False, "Cancelled"
        should_click, stats = green_guard_allows_click(self._config, calibration_key)
        ratio = stats.get("green_ratio", 0)
        if not should_click:
            print(f"[main macro] {label} is green ({ratio:.0%}) — not clicking")
            return True, None
        print(f"[main macro] {label} not green ({ratio:.0%}) — clicking")
        if not github_original_click_at(
            *point,
            click=1,
            pre_sleep_sec=POTION_CLICK_PRE_SLEEP_SEC * POTION_CRAFT_SLOWDOWN,
            cancel=self._macro_stop,
        ):
            return False, "Cancelled"
        return True, None

    def _potion_switch_interval_seconds(self) -> float:
        """How long to stay on each potion before switching (UI: Switch interval seconds)."""
        raw = self._config.get("potion_switch_interval", 60)
        try:
            return float(max(1, int(float(raw))))
        except (TypeError, ValueError):
            return 60.0

    def _potion_craft_duration_seconds(self) -> float:
        if self._potion_switching_enabled():
            return self._potion_switch_interval_seconds()
        raw = self._config.get("potion_craft_interval", 180)
        try:
            return float(max(10, int(float(raw))))
        except (TypeError, ValueError):
            return 180.0

    def _potion_schedule_delay_seconds(self) -> float:
        """Extra wait before the next potion run (switching uses switch interval only, no second timer)."""
        if self._potion_switching_enabled():
            return POTION_SWITCH_GAP_SEC
        return self._potion_craft_duration_seconds()

    def _potion_interval_seconds(self) -> int:
        return int(self._potion_schedule_delay_seconds())

    def _obby_interval_seconds(self) -> int:
        raw = self._config.get("auto_obby_interval") or self._config.get("obby_claim_interval") or 15
        try:
            minutes = float(raw)
        except (TypeError, ValueError):
            minutes = 15.0
        return max(60, int(minutes * 60))

    def _auto_obby_enabled(self) -> bool:
        return config_enabled(self._config, "enable_auto_obby")

    def _merchant_calibration_point(self, key: str) -> tuple[int, int] | None:
        fallbacks = {
            "items_tab": "potion_items_tab",
            "search_bar": "potion_search_bar",
        }
        return self._calibration_point(key, fallback=fallbacks.get(key))

    def _merchant_teleporter_ready(self) -> bool:
        ready, _missing = merchant_teleporter_ready(
            self._config, self._merchant_calibration_point
        )
        return ready

    def _merchant_limbo_ready(self) -> bool:
        return self._calibration_point("merchant_open_button") is not None

    def _merchant_tasks_enabled(self) -> bool:
        tele = merchant_teleporter_enabled(
            self._config, config_enabled=config_enabled
        ) and self._merchant_teleporter_ready()
        limbo = merchant_in_limbo_enabled(
            self._config, config_enabled=config_enabled
        ) and self._merchant_limbo_ready()
        return tele or limbo

    def _warn_merchant_misconfigured(self) -> None:
        if merchant_teleporter_enabled(
            self._config, config_enabled=config_enabled
        ) and not self._merchant_teleporter_ready():
            _, missing = merchant_teleporter_ready(
                self._config, self._merchant_calibration_point
            )
            print(
                "[main macro] merchant teleporter is ON but calibrations are incomplete — "
                + ", ".join(missing)
            )
        if merchant_in_limbo_enabled(
            self._config, config_enabled=config_enabled
        ) and not self._merchant_limbo_ready():
            print(
                "[main macro] merchant in limbo is ON but merchant_open_button "
                "is not calibrated"
            )

    def _mt_interval_seconds(self) -> int:
        return mt_interval_seconds(self._config)

    def _merchant_actionable(self, *, now: float, next_merchant_at: float) -> bool:
        """Merchant is due AND off its internal 190s cooldown (no pointless no-op runs)."""
        if now < next_merchant_at:
            return False
        return merchant_cooldown_remaining() <= 0.0

    def _quest_tasks_enabled(self) -> bool:
        return daily_quests_enabled(
            self._config, config_enabled=config_enabled
        ) and daily_quests_ready(self._calibration_point)[0]

    def _quest_interval_seconds(self) -> int:
        return quest_interval_seconds(self._config)

    def _warn_quest_misconfigured(self) -> None:
        if not daily_quests_enabled(self._config, config_enabled=config_enabled):
            return
        ready, missing = daily_quests_ready(self._calibration_point)
        if not ready:
            print(
                "[main macro] auto claim daily quests is ON but calibrations are incomplete — "
                + ", ".join(missing)
            )

    def _run_quest_tasks(self, *, reason: str) -> None:
        if self._macro_stop.is_set():
            return
        if not daily_quests_enabled(self._config, config_enabled=config_enabled):
            return
        result = run_daily_quest_claim(
            get_point=self._calibration_point,
            focus_roblox=self._hotkeys.focus_roblox,
            cancel_event=self._macro_stop,
            reason=reason,
        )
        print(f"[main macro] daily quests result: {result}")

    def _run_merchant_and_quest_batch(
        self, *, reason: str, run_quests: bool
    ) -> None:
        """Merchant first (closes inventory); quests only when run_quests is True."""
        if self._macro_stop.is_set():
            return

        merchant_ran = False
        if self._merchant_tasks_enabled():
            print(f"[main macro] merchant batch ({reason}): running before other UI tasks")
            self._run_merchant_tasks(reason=reason)
            merchant_ran = True

        if not run_quests or not self._quest_tasks_enabled() or self._macro_stop.is_set():
            return

        if merchant_ran:
            print(
                "[main macro] daily quests deferred until after merchant "
                "(inventory should be closed)"
            )
            if not _sleep_sec(QUEST_AFTER_MERCHANT_SETTLE_SEC, self._macro_stop):
                return

        self._run_quest_tasks(
            reason=f"after merchant ({reason})" if merchant_ran else reason
        )

    @contextmanager
    def _macro_session(self, owner: str):
        acquired = self._macro_session_gate.try_acquire(
            owner,
            replayer_running=self._replayer.is_running,
            stop_set=self._macro_stop.is_set(),
        )
        try:
            yield acquired
        finally:
            if acquired:
                self._macro_session_gate.release(owner)

    def _ui_task_random_tiebreak(self) -> bool:
        value = self._config.get("ui_task_random_tiebreak", True)
        if isinstance(value, str):
            return value.strip().lower() not in ("0", "false", "no", "off")
        return bool(value)

    def _collect_interval_ui_tasks(
        self,
        *,
        merchant_due: bool,
        quest_due: bool,
        potion_due: bool,
        obby_due: bool,
        merchant_enabled: bool,
        quest_enabled: bool,
        potion_enabled: bool,
        obby_enabled: bool,
        buffs_due: bool = False,
        sc_due: bool = False,
        br_due: bool = False,
        biome_selector_due: bool = False,
    ) -> list[ScheduledUiTask]:
        tasks: list[ScheduledUiTask] = []
        if buffs_due:
            tasks.append(schedule(MacroUiTask.BUFFS))
        if merchant_due:
            if quest_due and quest_enabled:
                tasks.append(schedule(MacroUiTask.MERCHANT_THEN_QUESTS))
            else:
                tasks.append(schedule(MacroUiTask.MERCHANT))
        elif quest_due and quest_enabled:
            # Merchant isn't due, so don't tie quests behind a merchant attempt.
            tasks.append(schedule(MacroUiTask.QUEST))
        if sc_due:
            tasks.append(schedule(MacroUiTask.SC))
        if br_due:
            tasks.append(schedule(MacroUiTask.BR))
        if biome_selector_due:
            tasks.append(schedule(MacroUiTask.BIOME_SELECTOR))
        if potion_due and potion_enabled:
            tasks.append(schedule(MacroUiTask.POTION))
        if obby_due and obby_enabled:
            tasks.append(schedule(MacroUiTask.OBBY))
        return tasks

    def _run_scheduled_ui_task(
        self,
        task: MacroUiTask,
        *,
        switching_enabled: bool,
        reason: str,
    ) -> None:
        if self._macro_stop.is_set():
            return

        print(f"[main macro] UI task start: {task.name} ({reason})")
        if task == MacroUiTask.MERCHANT:
            self._run_merchant_tasks(reason=reason)
        elif task == MacroUiTask.MERCHANT_THEN_QUESTS:
            self._run_merchant_and_quest_batch(reason=reason, run_quests=True)
        elif task == MacroUiTask.BUFFS:
            self._run_buffs_task(reason=reason)
        elif task == MacroUiTask.SC:
            self._run_use_item_task(SC_ITEM_NAME, reason=reason)
        elif task == MacroUiTask.BR:
            self._run_use_item_task(BR_ITEM_NAME, reason=reason)
        elif task == MacroUiTask.BIOME_SELECTOR:
            self._run_biome_selector_task(reason=reason)
        elif task == MacroUiTask.QUEST:
            self._run_quest_tasks(reason=reason)
        elif task == MacroUiTask.POTION:
            if switching_enabled:
                switch_sec = self._potion_switch_interval_seconds()
                self._run_selected_potion_once(
                    reason=f"{reason} switch {switch_sec:.0f}s",
                    loop_add_craft=True,
                )
                self._advance_potion_rotation()
            else:
                self._run_selected_potion_once(
                    reason=reason,
                    loop_add_craft=True,
                )
        elif task == MacroUiTask.OBBY:
            self._run_obby_path(reason=reason)
        print(f"[main macro] UI task done: {task.name}")

    def _advance_timers_after_ui_task(
        self,
        task: MacroUiTask,
        *,
        switching_enabled: bool,
    ) -> dict[str, float]:
        now = time.monotonic()
        updates: dict[str, float] = {}
        if task in (MacroUiTask.MERCHANT, MacroUiTask.MERCHANT_THEN_QUESTS):
            updates["next_merchant_at"] = now + self._mt_interval_seconds()
        if task in (MacroUiTask.QUEST, MacroUiTask.MERCHANT_THEN_QUESTS):
            updates["next_quest_at"] = now + self._quest_interval_seconds()
        if task == MacroUiTask.SC:
            updates["next_sc_at"] = now + self._sc_interval_seconds()
        if task == MacroUiTask.BR:
            updates["next_br_at"] = now + self._br_interval_seconds()
        if task == MacroUiTask.BIOME_SELECTOR:
            updates["next_biome_selector_at"] = now + self._biome_selector_interval_seconds()
        if task == MacroUiTask.POTION:
            if switching_enabled:
                updates["next_potion_at"] = now + POTION_SWITCH_GAP_SEC
            else:
                updates["next_potion_at"] = now + self._potion_schedule_delay_seconds()
        if task == MacroUiTask.OBBY:
            updates["next_obby_at"] = now + self._obby_interval_seconds()
        return updates

    def _run_startup_ui_sequence(
        self,
        *,
        merchant_enabled: bool,
        quest_enabled: bool,
        potion_enabled: bool,
        obby_enabled: bool,
        switching_enabled: bool,
    ) -> tuple[float, float, float, float]:
        """Run each enabled UI task once, priority order, with settle gaps."""
        now = time.monotonic()
        startup_tasks: list[MacroUiTask] = []
        if merchant_enabled:
            # Merchant + quests run in ONE session (MERCHANT_THEN_QUESTS) so the
            # post-merchant quest claim isn't dropped by the session settle cooldown.
            startup_tasks.append(
                MacroUiTask.MERCHANT_THEN_QUESTS if quest_enabled else MacroUiTask.MERCHANT
            )
        elif quest_enabled:
            startup_tasks.append(MacroUiTask.QUEST)
        if potion_enabled:
            startup_tasks.append(MacroUiTask.POTION)
        if obby_enabled:
            startup_tasks.append(MacroUiTask.OBBY)

        for task in startup_order(startup_tasks):
            if self._macro_stop.is_set():
                break
            with self._macro_session(f"startup:{task.name}") as acquired:
                if not acquired:
                    continue
                self._run_scheduled_ui_task(
                    task,
                    switching_enabled=switching_enabled,
                    reason="startup",
                )

        next_merchant_at = (
            now + self._mt_interval_seconds() if merchant_enabled else 0.0
        )
        next_quest_at = (
            now + self._quest_interval_seconds() if quest_enabled else 0.0
        )
        next_potion_at = 0.0
        if potion_enabled:
            next_potion_at = (
                now + POTION_SWITCH_GAP_SEC
                if switching_enabled
                else now + self._potion_schedule_delay_seconds()
            )
        next_obby_at = now + self._obby_interval_seconds() if obby_enabled else 0.0
        return next_merchant_at, next_quest_at, next_potion_at, next_obby_at

    def _log_macro_task_audit(self) -> None:
        """Runtime audit: which UI modules are enabled vs implemented in _macro_loop."""
        cfg = self._config
        audit = {
            "potion": self._macro_potion_tasks_enabled(),
            "obby": self._auto_obby_enabled(),
            "merchant_teleporter": merchant_teleporter_enabled(
                cfg, config_enabled=config_enabled
            ),
            "merchant_limbo": merchant_in_limbo_enabled(cfg, config_enabled=config_enabled),
            "merchant_teleporter_cfg": bool(cfg.get("merchant_teleporter")),
            "auto_merchant_teleporter_cfg": bool(cfg.get("auto_merchant_teleporter")),
            "merchant_teleporter_ready": self._merchant_teleporter_ready(),
            "merchant_limbo_ready": self._merchant_limbo_ready(),
            "potion_craft": self._potion_crafting_enabled(),
            "potion_switch_effective": self._potion_switching_enabled(),
            "fishing_mode": bool(cfg.get("fishing_mode")),
            "mt_duration": cfg.get("mt_duration"),
            "daily_quests": self._quest_tasks_enabled(),
            "auto_claim_daily_quests_cfg": bool(cfg.get("auto_claim_daily_quests")),
            "biome_randomizer": self._br_enabled(),
            "strange_controller": self._sc_enabled(),
            "biome_selector": self._biome_selector_enabled(),
            "glitched_buffs": self._buffs_enabled(),
            "br_duration": cfg.get("br_duration"),
            "sc_duration": cfg.get("sc_duration"),
            "biome_selector_duration": cfg.get("biome_selector_duration"),
            "fishing_worker": self._is_fishing_mode_enabled(),
            "fishing_busy": self._fishing_busy,
            "implemented_in_loop": [
                "potion",
                "obby",
                "merchant",
                "daily_quests",
                "br",
                "sc",
                "biome_selector",
                "buffs",
                "fishing (dedicated thread when fishing_mode)",
            ],
            "ui_scheduler": (
                "one UI task per tick; priority "
                "buffs<merchant<sc<br<biome_selector<potion<quest<obby"
            ),
            "ui_random_tiebreak": self._ui_task_random_tiebreak(),
            "macro_session_owner": self._macro_session_gate.owner(),
            "macro_session_idle": self._macro_session_gate.is_idle(
                replayer_running=self._replayer.is_running,
                stop_set=self._macro_stop.is_set(),
            ),
        }
        print(f"[main macro] task audit: {audit}")

    def _run_merchant_tasks(self, *, reason: str) -> None:
        if self._macro_stop.is_set():
            return
        if merchant_teleporter_enabled(self._config, config_enabled=config_enabled):
            result = run_merchant_teleporter(
                config=self._config,
                get_point=self._merchant_calibration_point,
                get_region=self._calibration_region,
                focus_roblox=self._hotkeys.focus_roblox,
                cancel_event=self._macro_stop,
                reason=reason,
            )
            print(f"[main macro] merchant teleporter result: {result}")
        if merchant_in_limbo_enabled(self._config, config_enabled=config_enabled):
            result = run_merchant_limbo_interact(
                config=self._config,
                get_point=self._merchant_calibration_point,
                get_region=self._calibration_region,
                focus_roblox=self._hotkeys.focus_roblox,
                cancel_event=self._macro_stop,
                reason=reason,
            )
            print(f"[main macro] merchant limbo result: {result}")

    # ----- Biome Randomizer / Strange Controller / glitched buffs ----- #
    def _brsc_ready(self) -> bool:
        ready, _missing = brsc_ready(self._calibration_point)
        return ready

    def _br_enabled(self) -> bool:
        return (
            biome_randomizer_enabled(self._config, config_enabled=config_enabled)
            and self._brsc_ready()
        )

    def _sc_enabled(self) -> bool:
        return (
            strange_controller_enabled(self._config, config_enabled=config_enabled)
            and self._brsc_ready()
        )

    def _br_interval_seconds(self) -> int:
        return br_interval_seconds(self._config)

    def _sc_interval_seconds(self) -> int:
        return sc_interval_seconds(self._config)

    def _biome_selector_enabled(self) -> bool:
        return (
            biome_selector_enabled(self._config, config_enabled=config_enabled)
            and biome_selector_ready(
                self._calibration_point,
                get_region=self._calibration_region,
                config=self._config,
            )[0]
        )

    def _biome_selector_interval_seconds(self) -> int:
        return biome_selector_interval_seconds(self._config)

    def _run_biome_selector_task(self, *, reason: str) -> None:
        if self._macro_stop.is_set():
            return
        result = run_biome_selector(
            config=self._config,
            get_point=self._calibration_point,
            get_region=self._calibration_region,
            focus_roblox=self._hotkeys.focus_roblox,
            cancel_event=self._macro_stop,
            reason=reason,
        )
        print(f"[main macro] biome selector result: {result}")

    def run_biome_selector_now(self) -> dict:
        """Manual test from the Automated Actions UI."""
        if self._macro_stop.is_set():
            return {"ok": False, "error": "Macro is stopping"}
        with self._macro_session("manual:biome_selector") as acquired:
            if not acquired:
                return {
                    "ok": False,
                    "error": "Another inventory task is running — try again shortly",
                }
            result = run_biome_selector(
                config=self._config,
                get_point=self._calibration_point,
                get_region=self._calibration_region,
                focus_roblox=self._hotkeys.focus_roblox,
                cancel_event=self._macro_stop,
                reason="manual",
            )
        return {"ok": "OK" in result, "status": result}

    def get_biome_selector_status(self) -> dict:
        return {
            "ok": True,
            **calibration_status(
                self._calibration_point,
                self._calibration_region,
                self._config,
            ),
        }

    def save_biome_selector_drives(self, drives: dict) -> dict:
        if not isinstance(drives, dict):
            return {"ok": False, "error": "drives must be an object"}
        self._config["biome_selector_drives"] = normalize_drive_toggles(drives)
        self.save_config(self._config)
        return {"ok": True, "drives": self._config["biome_selector_drives"]}

    def save_biome_selector_layout(self, layout: dict) -> dict:
        if not isinstance(layout, dict):
            return {"ok": False, "error": "layout must be an object"}
        for key in (
            "biome_selector_button_width",
            "biome_selector_button_height",
            "biome_selector_button_count",
            "biome_selector_button_spacing",
        ):
            if key in layout:
                try:
                    self._config[key] = int(float(layout[key]))
                except (TypeError, ValueError):
                    pass
        self.save_config(self._config)
        status = calibration_status(
            self._calibration_point,
            self._calibration_region,
            self._config,
        )
        return {"ok": True, "layout": status.get("layout"), "slots": status.get("slots")}

    def _buffs_enabled(self) -> bool:
        return (
            auto_buff_glitched_enabled(self._config, config_enabled=config_enabled)
            and buffs_ready(self._calibration_point)[0]
        )

    def _run_use_item_task(self, item_name: str, *, reason: str) -> None:
        if self._macro_stop.is_set():
            return
        result = run_use_item(
            item_name,
            config=self._config,
            get_point=self._calibration_point,
            focus_roblox=self._hotkeys.focus_roblox,
            cancel_event=self._macro_stop,
            reason=reason,
        )
        print(f"[main macro] use item '{item_name}' result: {result}")

    def _run_buffs_task(self, *, reason: str) -> None:
        if self._macro_stop.is_set():
            return
        self._buff_pop_requested.clear()
        result = run_auto_pop_buffs(
            config=self._config,
            get_point=self._calibration_point,
            focus_roblox=self._hotkeys.focus_roblox,
            cancel_event=self._macro_stop,
            reason=reason,
        )
        print(f"[main macro] auto-pop buffs result: {result}")

    def _biome_notifier_enabled(self) -> bool:
        notifier = self._config.get("biome_notifier")
        if not isinstance(notifier, dict):
            return False
        if not any(
            biome_notify_enabled(notifier, str(k))
            for k in notifier
            if str(k).upper() != "NORMAL"
        ):
            return False
        return bool(self._webhook_urls())

    def _handle_biome(self, name: str) -> None:
        """Called by BiomeWatcher on every biome change (off the macro threads)."""
        upper = str(name).strip().upper()
        if upper in REMOVED_BIOMES:
            return

        # Preserve GLITCHED -> auto-pop buffs behaviour.
        if upper == GLITCHED_BIOME and self._buffs_enabled():
            self._buff_pop_requested.set()

        notifier = self._config.get("biome_notifier") or {}
        if not biome_notify_enabled(notifier, upper):
            print(f"[biome] {upper} detected but its notifier toggle is off — not sending")
            return
        urls = self._webhook_urls()
        if not urls:
            print(f"[biome] {upper} notifier on but no webhook URL configured — not sending")
            return
        print(f"[biome] {upper} — sending webhook")

        biome_data = self.get_full_biome_data()
        info = biome_data.get(name) or biome_data.get(upper) or {}
        pings = self._config.get("biome_pings") or {}
        ping = pings.get(upper) or pings.get(name)
        rare_mode = self._config.get("rare_biome_mention_mode") or DEFAULT_RARE_MENTION_MODE
        username = self._config.get("roblox_username") or None
        ps_link = self._config.get("private_server_link") or None

        def _send() -> None:
            try:
                send_biome_webhook(
                    urls,
                    biome_name=upper,
                    color=info.get("color"),
                    thumbnail_url=info.get("thumbnail_url"),
                    username=username,
                    ps_link=ps_link,
                    ping=ping,
                    rare_mention_mode=str(rare_mode),
                )
            except Exception as error:  # never let a webhook crash the watcher
                print(f"[webhook] biome send failed: {error}")

        Thread(target=_send, name="BlossomBiomeWebhook", daemon=True).start()

    def _aura_detection_enabled(self) -> bool:
        return config_enabled(self._config, "enable_aura_detection") and bool(self._webhook_urls())

    def _handle_aura(self, name: str) -> None:
        """Called by BiomeWatcher whenever the equipped aura changes."""
        if not self._aura_detection_enabled():
            return
        urls = self._webhook_urls()
        if not urls:
            return

        ok, rarity = should_ping_aura(
            name,
            aura_table_path=AURAS_PATH,
            ping_minimum=self._config.get("ping_minimum"),
            force_ping_auras=self._config.get("force_ping_auras"),
        )
        if not ok:
            print(f"[aura] {name} — below ping threshold, skipping")
            return

        username = self._config.get("roblox_username") or None
        ps_link = self._config.get("private_server_link") or None
        raw_uid = str(self._config.get("aura_user_id") or "").strip()
        ping = {"id": raw_uid, "type": "userid"} if raw_uid.isdigit() else None
        want_shot = config_enabled(self._config, "aura_detection_screenshot")
        print(f"[aura] {name} — sending webhook (rarity={rarity or '?'})")

        def _send() -> None:
            screenshot_path = self._capture_aura_screenshot() if want_shot else None
            try:
                send_aura_webhook(
                    urls,
                    aura_name=name,
                    username=str(username).strip() if username else None,
                    ps_link=str(ps_link).strip() if ps_link else None,
                    ping=ping,
                    rarity=rarity,
                    screenshot_path=screenshot_path,
                )
            except Exception as error:
                print(f"[webhook] aura send failed: {error}")

        Thread(target=_send, name="BlossomAuraWebhook", daemon=True).start()

    def start_listeners(self) -> None:
        """Start the always-on biome + aura watcher (app lifetime, macro-independent)."""
        if self._biome_watcher is not None:
            return
        self._biome_watcher = BiomeWatcher(
            on_biome=self._handle_biome,
            on_aura=self._handle_aura,
            stop_event=self._listener_stop,
        )
        self._biome_watcher.start()

    def stop_listeners(self) -> None:
        self._listener_stop.set()
        self._biome_watcher = None

    # ----- License gating (beta builds only) ----- #
    def get_license_status(self, refresh: bool = False) -> dict:
        """Current license status for the UI. refresh=True hits the server."""
        try:
            return blossom_license.get_status(refresh=bool(refresh))
        except Exception as error:
            print(f"[license] status error: {error}")
            return {
                "required": blossom_license.licensing_required(),
                "licensed": not blossom_license.licensing_required(),
                "state": "offline",
                "reason": "offline",
                "message": "Could not check license.",
                "key_masked": "",
                "server_configured": False,
                "hwid": "",
                "expiry": None,
            }

    def submit_license_key(self, key: str) -> dict:
        status = blossom_license.activate(str(key or ""))
        self._push_license_status(status)
        return status

    def _push_license_status(self, status: dict) -> None:
        try:
            payload = json.dumps(status)
            self._window.evaluate_js(
                f"if (window.onLicenseStatus) window.onLicenseStatus({payload});"
            )
        except Exception as error:
            print(f"[license] UI push failed: {error}")

    def start_license_guard(self) -> None:
        """Initial license check + periodic re-validation (app lifetime)."""
        if not blossom_license.licensing_required():
            return
        if self._license_thread is not None:
            return

        def _loop() -> None:
            first = True
            while not self._license_stop.is_set():
                try:
                    status = blossom_license.get_status(refresh=True)
                    self._push_license_status(status)
                    # Revoked / wrong machine while running -> stop the macro.
                    if not status.get("licensed") and self._macro_running:
                        print("[license] lost license while running — stopping macro")
                        self._emergency_stop()
                except Exception as error:
                    print(f"[license] guard error: {error}")
                first = False
                self._license_stop.wait(blossom_license.REVALIDATE_INTERVAL_SEC)
            del first

        self._license_thread = Thread(target=_loop, name="BlossomLicenseGuard", daemon=True)
        self._license_thread.start()

    def stop_license_guard(self) -> None:
        self._license_stop.set()

    def _start_biome_watcher(self) -> None:
        # Kept for the macro loop: ensure the always-on watcher is running and
        # reset the glitched-buff request flag for a fresh run.
        self._buff_pop_requested.clear()
        self.start_listeners()

    def _stop_biome_watcher(self) -> None:
        # The watcher is app-lifetime now; only clear the per-run buff request.
        self._buff_pop_requested.clear()

    def _run_movement_path(self, path_name: str, *, reason: str) -> str:
        """Camera align → wait → char_align → path (see blossom_prepath)."""
        if self._macro_stop.is_set():
            return "Cancelled"
        print(f"[main macro] starting path {path_name} ({reason})")
        result = self._replay_recording_impl(path_name)
        print(f"[main macro] path {path_name} finished: {result}")
        return result

    def _run_obby_path(self, *, reason: str) -> str:
        if not self._resolve_path_file("obby"):
            return "Error: obby.json not found — record a path in Movements or copy into AppData\\Blossom\\paths\\"
        return self._run_movement_path("obby", reason=reason)

    def _run_selected_potion_once(
        self,
        *,
        reason: str,
        loop_add_craft: bool = False,
        allow_when_disabled: bool = False,
    ) -> str:
        if not allow_when_disabled and not self._macro_potion_tasks_enabled():
            print(f"[main macro] skip potion ({reason}): auto craft / switching off")
            return "Skipped: auto potion crafting disabled"
        potion_name = self._active_potion_name()
        if not potion_name:
            if self._potion_switching_enabled():
                return "Error: assign potions in switch slots #1–#3"
            return "Error: no selected potion"
        craft_duration = self._potion_craft_duration_seconds() if loop_add_craft else None
        return self._run_calibrated_potion(
            potion_name,
            reason=reason,
            loop_add_craft=loop_add_craft,
            craft_duration_sec=craft_duration,
        )

    def _run_calibrated_potion(
        self,
        potion_name: str,
        *,
        reason: str,
        loop_add_craft: bool = False,
        craft_duration_sec: float | None = None,
    ) -> str:
        if self._recorder.is_recording:
            return "Skipped: another recording is in progress"

        potion_name = Path(potion_name or "").stem.strip()
        if not potion_name:
            return "Error: no potion name"

        items_tab = self._calibration_point("potion_items_tab", fallback="items_tab")
        search_bar = self._calibration_point("potion_search_bar", fallback="search_bar")
        first_slot = self._calibration_point("potion_first_potion_slot_pos", fallback="first_item_inventory_slot_pos")
        recipe_auto_button = self._calibration_point("potion_recipe_auto_button")
        recipe_button = self._calibration_point("potion_recipe_button")
        auto_add_button = self._calibration_point("potion_auto_add_button", fallback="potion_auto_button")
        craft_button = self._calibration_point("potion_craft_button", fallback="potion_auto_button")
        missing = [
            name
            for name, point in {
                "potion_items_tab/items_tab": items_tab,
                "potion_search_bar/search_bar": search_bar,
                "potion_first_potion_slot_pos/first_item_inventory_slot_pos": first_slot,
                "potion_recipe_auto_button": recipe_auto_button,
                "potion_recipe_button": recipe_button,
                "potion_auto_add_button": auto_add_button,
                "potion_craft_button": craft_button,
            }.items()
            if point is None
        ]
        if missing:
            return "Error: missing potion calibration: " + ", ".join(missing)

        if self._macro_stop.is_set():
            return "Cancelled"

        print(f"[main macro] {reason}: crafting {potion_name} with calibrated buttons")
        focused = self._hotkeys.focus_roblox()
        print(f"[main macro] Roblox focus before craft: {focused}")
        if not focused:
            return "Error: Roblox not focused"

        def pause_for_potion_step() -> bool:
            return not self._macro_stop.is_set() if loop_add_craft else True

        def potion_click(label: str, point: tuple[int, int], *, cycle: int | None = None, click: int = 1) -> bool:
            if self._macro_stop.is_set():
                return False
            in_add_craft_loop = label in ("add_everything", "craft_button") and cycle is not None
            pre_sleep = POTION_CLICK_PRE_SLEEP_SEC * POTION_CRAFT_SLOWDOWN
            if in_add_craft_loop:
                pre_sleep *= POTION_LOOP_SLOWDOWN
            if not github_original_click_at(
                *point,
                click=click,
                pre_sleep_sec=pre_sleep,
                cancel=self._macro_stop,
            ):
                return False
            return pause_for_potion_step()

        try:
            import pyautogui
            import autoit

            pyautogui.PAUSE = 0.04 * POTION_CRAFT_SLOWDOWN
            if not potion_click("items_tab", items_tab):
                return f"Stopped while setting up {potion_name}"
            if not potion_click("search_bar", search_bar, click=2):
                return f"Stopped while setting up {potion_name}"
            submit_potion_search_text(potion_name)
            if not pause_for_potion_step():
                return f"Stopped while searching {potion_name}"
            print(f"[main macro] search submitted: {potion_name} (Enter at search bar)")
            if not potion_click("first_slot", first_slot):
                return f"Stopped while selecting {potion_name}"

            if not self._click_green_guard_button_if_needed(
                recipe_auto_button,
                "potion_recipe_auto_button",
                label="recipe Auto",
            )[0]:
                return f"Stopped while checking auto for {potion_name}"
            if not pause_for_potion_step():
                return f"Stopped while checking auto for {potion_name}"

            if not potion_click("recipe_button", recipe_button):
                return f"Stopped while opening recipe for {potion_name}"

            craft_deadline = None
            if loop_add_craft and craft_duration_sec:
                craft_deadline = time.monotonic() + craft_duration_sec
                if self._potion_switching_enabled():
                    print(
                        f"[main macro] crafting {potion_name} for switch interval "
                        f"{craft_duration_sec:.0f}s"
                    )
                else:
                    print(
                        f"[main macro] crafting {potion_name} for {craft_duration_sec:.0f}s"
                    )

            cycle = 0
            while True:
                cycle += 1
                if not potion_click("add_everything", auto_add_button, cycle=cycle):
                    return f"Stopped while adding everything for {potion_name}"
                if not potion_click("craft_button", craft_button, cycle=cycle):
                    return f"Stopped while crafting {potion_name}"
                if not loop_add_craft:
                    break
                if craft_deadline is not None and time.monotonic() >= craft_deadline:
                    print(f"[main macro] craft window ended for {potion_name}")
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
        self._reload_config_from_disk()
        self._log_macro_task_audit()
        self._warn_merchant_misconfigured()
        self._warn_quest_misconfigured()
        obby_enabled = self._auto_obby_enabled()
        potion_enabled = self._macro_potion_tasks_enabled()
        merchant_enabled = self._merchant_tasks_enabled()
        quest_enabled = self._quest_tasks_enabled()
        switching_enabled = self._potion_switching_enabled()
        br_enabled = self._br_enabled()
        sc_enabled = self._sc_enabled()
        biome_selector_enabled_loop = self._biome_selector_enabled()
        buffs_enabled = self._buffs_enabled()
        if switching_enabled:
            self._sync_potion_rotation_index()
        fishing_enabled = self._is_fishing_mode_enabled()
        print(
            f"[main macro] enabled tasks: fishing={fishing_enabled}, "
            f"auto_obby={obby_enabled}, "
            f"auto_potion_craft={self._potion_crafting_enabled()}, "
            f"potion_switching={switching_enabled}, "
            f"merchant={merchant_enabled}, "
            f"daily_quests={quest_enabled}, "
            f"biome_randomizer={br_enabled}, "
            f"strange_controller={sc_enabled}, "
            f"biome_selector={biome_selector_enabled_loop}, "
            f"glitched_buffs={buffs_enabled}, "
            f"rotation={self._potion_rotation_filenames()}"
        )
        if fishing_enabled:
            missing = self._fishing_calibration_issues()
            if missing:
                print(f"[FishingMode] missing calibrations: {', '.join(missing)}")
            self._sync_fishing_worker()
        if self._auto_eden_enabled():
            ready, eden_missing = auto_eden_ready(self._config)
            if not ready:
                print(f"[AutoEden] missing calibrations: {', '.join(eden_missing)}")
            self._sync_eden_worker()
        self._start_biome_watcher()
        next_obby_at = 0.0
        next_potion_at = 0.0
        next_merchant_at = 0.0
        next_quest_at = 0.0
        # BR/SC use their own cooldowns; first use happens after one interval.
        next_br_at = time.monotonic() + self._br_interval_seconds() if br_enabled else 0.0
        next_sc_at = time.monotonic() + self._sc_interval_seconds() if sc_enabled else 0.0
        next_biome_selector_at = (
            time.monotonic() + self._biome_selector_interval_seconds()
            if biome_selector_enabled_loop
            else 0.0
        )
        # Currency screenshot is non-intrusive (region grab only). Take the first
        # one ~3s after start (effectively on start), then every interval.
        currency_on = self._currency_screenshot_enabled()
        next_currency_at = time.monotonic() + 3.0 if currency_on else 0.0
        self._log_webhook_features()

        try:
            if (
                not self._macro_stop.is_set()
                and (potion_enabled or obby_enabled or merchant_enabled or quest_enabled)
            ):
                next_merchant_at, next_quest_at, next_potion_at, next_obby_at = (
                    self._run_startup_ui_sequence(
                        merchant_enabled=merchant_enabled,
                        quest_enabled=quest_enabled,
                        potion_enabled=potion_enabled,
                        obby_enabled=obby_enabled,
                        switching_enabled=switching_enabled,
                    )
                )
            if not any(
                (
                    fishing_enabled,
                    potion_enabled,
                    obby_enabled,
                    merchant_enabled,
                    quest_enabled,
                    br_enabled,
                    sc_enabled,
                    biome_selector_enabled_loop,
                    buffs_enabled,
                )
            ):
                print(
                    "[main macro] no tasks enabled "
                    "(turn on Fishing Mode, Auto Obby, Potion Craft/Switching, Merchant, Daily Quests, "
                    "Biome Randomizer, Strange Controller, Biome Selector, and/or Glitched Buffs)"
                )

            while not self._macro_stop.wait(0.15):
                self._reload_config_from_disk()
                self._sync_fishing_worker()
                self._sync_eden_worker()
                if self._is_fishing_mode_enabled():
                    continue
                now = time.monotonic()
                obby_enabled = self._auto_obby_enabled()
                potion_enabled = self._macro_potion_tasks_enabled()
                merchant_enabled = self._merchant_tasks_enabled()
                quest_enabled = self._quest_tasks_enabled()
                switching_enabled = self._potion_switching_enabled()
                br_enabled = self._br_enabled()
                sc_enabled = self._sc_enabled()
                biome_selector_enabled_loop = self._biome_selector_enabled()

                # Currency screenshot runs on its own timer, independent of the
                # UI session gate (it only grabs a screen region, no Roblox UI).
                if self._currency_screenshot_enabled():
                    if now >= next_currency_at:
                        self._run_currency_screenshot(reason="interval")
                        next_currency_at = now + self._currency_interval_seconds()
                else:
                    next_currency_at = 0.0

                if self._replayer.is_running:
                    continue
                if not self._macro_session_gate.is_idle(
                    replayer_running=self._replayer.is_running,
                    stop_set=self._macro_stop.is_set(),
                ):
                    continue

                merchant_due = merchant_enabled and self._merchant_actionable(
                    now=now, next_merchant_at=next_merchant_at
                )
                quest_due = quest_enabled and now >= next_quest_at
                potion_due = potion_enabled and now >= next_potion_at
                obby_due = obby_enabled and now >= next_obby_at
                br_due = br_enabled and now >= next_br_at
                sc_due = sc_enabled and now >= next_sc_at
                biome_selector_due = (
                    biome_selector_enabled_loop and now >= next_biome_selector_at
                )
                buffs_due = self._buff_pop_requested.is_set()

                due_tasks = self._collect_interval_ui_tasks(
                    merchant_due=merchant_due,
                    quest_due=quest_due,
                    potion_due=potion_due,
                    obby_due=obby_due,
                    merchant_enabled=merchant_enabled,
                    quest_enabled=quest_enabled,
                    potion_enabled=potion_enabled,
                    obby_enabled=obby_enabled,
                    buffs_due=buffs_due,
                    sc_due=sc_due,
                    br_due=br_due,
                    biome_selector_due=biome_selector_due,
                )
                picked = pick_task(
                    due_tasks, randomize_ties=self._ui_task_random_tiebreak()
                )
                if picked is None:
                    continue

                if picked.task in (
                    MacroUiTask.QUEST,
                    MacroUiTask.MERCHANT_THEN_QUESTS,
                ):
                    quest_min = self._quest_interval_seconds() / 60.0
                    print(
                        f"[main macro] daily quests due (claim interval {quest_min:.0f} min)"
                    )

                reason = f"interval {picked.task.name.lower()}"
                timer_updates: dict[str, float] = {}
                with self._macro_session(f"interval:{picked.task.name}") as acquired:
                    if not acquired:
                        continue
                    self._run_scheduled_ui_task(
                        picked.task,
                        switching_enabled=switching_enabled,
                        reason=reason,
                    )
                    timer_updates = self._advance_timers_after_ui_task(
                        picked.task, switching_enabled=switching_enabled
                    )
                if "next_merchant_at" in timer_updates:
                    next_merchant_at = timer_updates["next_merchant_at"]
                if "next_quest_at" in timer_updates:
                    next_quest_at = timer_updates["next_quest_at"]
                if "next_potion_at" in timer_updates:
                    next_potion_at = timer_updates["next_potion_at"]
                if "next_obby_at" in timer_updates:
                    next_obby_at = timer_updates["next_obby_at"]
                if "next_sc_at" in timer_updates:
                    next_sc_at = timer_updates["next_sc_at"]
                if "next_br_at" in timer_updates:
                    next_br_at = timer_updates["next_br_at"]
                if "next_biome_selector_at" in timer_updates:
                    next_biome_selector_at = timer_updates["next_biome_selector_at"]
        finally:
            self._stop_fishing_worker()
            self._stop_eden_worker()
            self._stop_biome_watcher()
            self._macro_running = False
            print("[main macro] worker stopped")

    def _teardown_macro_threads(self) -> None:
        """Signal stop and join the macro + fishing worker threads.

        Idempotent and safe to call when nothing is running. After this returns,
        the previous macro loop thread has fully exited (run its finally block),
        so a fresh start can clear the stop event without reviving a stale loop.
        """
        self._macro_stop.set()
        self._replayer.cancel()
        self._stop_fishing_worker()
        self._stop_eden_worker()
        thread = self._macro_thread
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=MACRO_THREAD_JOIN_TIMEOUT_SEC)
            if thread.is_alive():
                print("[main macro] warning: previous worker did not exit in time")
        if thread is None or not thread.is_alive():
            self._macro_thread = None

    def _start_local_macro(self) -> None:
        with self._macro_lifecycle_lock:
            if self._macro_running:
                print("[main macro] already running")
                return

            if blossom_license.licensing_required() and not blossom_license.is_licensed():
                print("[main macro] blocked: build not activated")
                status = blossom_license.get_status(refresh=False)
                self._push_license_status(status)
                return

            # Fully tear down any previous run before starting fresh. A quick
            # stop->start (hotkey or UI) can otherwise leave the old loop thread
            # alive; clearing _macro_stop below would then revive it, running two
            # loops and letting the old thread's finally clobber the new run's
            # state (fishing worker, _macro_running). Joining here prevents that.
            self._teardown_macro_threads()

            # Reset all per-run state so every start begins from a clean slate.
            self._macro_stop.clear()
            self._fishing_stop_event.clear()
            self._eden_stop_event.clear()
            self._buff_pop_requested.clear()
            self._macro_session_gate.force_release()
            self._fishing_busy = False
            self._macro_running = True
            self._macro_started_at = time.time()
            self._macro_thread = Thread(target=self._macro_loop, daemon=True)
            self._macro_thread.start()
            print("[main macro] started")
            self._send_status_notif("started")

    def _stop_local_macro(self) -> None:
        print("[main macro] stopping")
        with self._macro_lifecycle_lock:
            self._emergency_stop()
            self._teardown_macro_threads()

    def init_hotkeys(self) -> None:
        self._hotkeys.register()

    def pause_macro_hotkeys(self) -> bool:
        """Unregister global macro hotkeys while the UI captures a new bind."""
        self._hotkeys.unregister()
        return True

    def resume_macro_hotkeys(self) -> bool:
        """Re-register macro hotkeys from the current config."""
        self._hotkeys.reload()
        return True

    def set_hotkey_capture(self, active: bool) -> bool:
        """Backward-compatible alias used by older blossom-hotkeys builds."""
        if active:
            return self.pause_macro_hotkeys()
        return self.resume_macro_hotkeys()

    def start_macro_recording(self):
        if not self._macro_session_gate.is_idle(
            replayer_running=self._replayer.is_running,
            stop_set=self._macro_stop.is_set(),
        ):
            busy = self._macro_session_gate.owner() or "cooldown"
            return {
                "ok": False,
                "error": f"Macro busy ({busy}) — wait before recording a path",
            }
        try:
            self._hotkeys.focus_roblox()
            self._recorder.start(clicks_only=False)
            return {"ok": True, "error": None}
        except Exception as error:
            print(f"[macro recording] start failed: {error}")
            return {"ok": False, "error": str(error)}

    def stop_macro_recording(self, path_name: str | None = None):
        self._recorder.stop()
        payload = self._recorder.build_payload(include_screen=True)
        try:
            filename = self._path_filename(path_name)
        except ValueError as error:
            print(f"[macro recording] {error}")
            return False
        dest = OBBY_PATHS_DIR / filename
        save_macro_json(dest, payload)
        print(f"[macro recording] saved {len(payload.get('events') or [])} events -> {dest}")
        return True

    def craft_selected_potion(self):
        if self._recorder.is_recording:
            return {"ok": False, "error": "Stop the active recording before crafting"}
        if self._replayer.is_running:
            return {"ok": False, "error": "Replay already running"}
        if not self._macro_session_gate.is_idle(
            replayer_running=self._replayer.is_running,
            stop_set=self._macro_stop.is_set(),
        ):
            busy = self._macro_session_gate.owner() or "cooldown"
            return {
                "ok": False,
                "error": f"Macro busy ({busy}) — wait for the current action to finish",
            }

        def run() -> None:
            with self._macro_session("manual:craft_selected") as acquired:
                if not acquired:
                    print("[main macro] manual craft skipped: session busy")
                    return
                result = self._run_selected_potion_once(
                    reason="manual", allow_when_disabled=True
                )
                print(f"[main macro] manual craft selected result: {result}")

        thread = Thread(target=run, daemon=True)
        thread.start()
        return {"ok": True, "error": None, "status": "Craft started"}

    def craft_potion_by_name(self, name):
        cleaned = Path(str(name or "")).stem.strip()
        if not cleaned:
            return {"ok": False, "error": "Potion name is required"}
        if self._recorder.is_recording:
            return {"ok": False, "error": "Stop the active recording before crafting"}
        if self._replayer.is_running:
            return {"ok": False, "error": "Replay already running"}
        if not self._macro_session_gate.is_idle(
            replayer_running=self._replayer.is_running,
            stop_set=self._macro_stop.is_set(),
        ):
            busy = self._macro_session_gate.owner() or "cooldown"
            return {
                "ok": False,
                "error": f"Macro busy ({busy}) — wait for the current action to finish",
            }

        def run() -> None:
            with self._macro_session(f"manual:craft:{cleaned}") as acquired:
                if not acquired:
                    print(f"[main macro] manual craft {cleaned} skipped: session busy")
                    return
                result = self._run_calibrated_potion(cleaned, reason="manual-name")
                print(f"[main macro] manual craft {cleaned}: {result}")

        Thread(target=run, daemon=True).start()
        return {"ok": True, "error": None, "status": f"Crafting {cleaned}"}

    def set_calibration_point(self, key):
        allowed = {
            "potion_items_tab",
            "potion_search_bar",
            "potion_first_potion_slot_pos",
            "potion_recipe_auto_button",
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
            "potion_recipe_auto_button",
            "potion_recipe_button",
            "potion_auto_add_button",
            "potion_craft_button",
            # Auto Merchant (Mari / Jester) calibrations.
            "merchant_name_ocr_pos",
            "item_name_ocr_pos",
            "merchant_slot_1_pos",
            "merchant_slot_2_pos",
            "merchant_slot_3_pos",
            "merchant_slot_4_pos",
            "merchant_slot_5_pos",
            "purchase_amount_button",
            "merchant_set_max_button",
            "purchase_button",
            "merchant_close_button",
            # Currency display region for periodic webhook screenshots.
            "currency_region",
            # Biome Selector UI + inventory (drag a box unless noted).
            "inventory_menu",
            "search_bar",
            "first_item_inventory_slot_pos",
            "use_button",
            "inventory_close_button",
            "biome_selector_frame_pos",
            "biome_selector_first_drive_pos",
            "biome_selector_confirm_pos",
        }
        if key not in allowed:
            return {"ok": False, "error": "Unsupported calibration key"}

        return self._start_drag_calibration(key, "region")

    def get_calibration_status(self):
        return {
            "ok": True,
            "seq": self._calibration_capture_seq,
            "capture": dict(self._calibration_capture_state),
        }

    def _replay_recording_impl(self, path_name: str | None = None) -> str:
        path = self._resolve_path_file(path_name)
        if path is None:
            label = self._path_filename(path_name) if path_name else "path"
            return (
                f"Error: {label} not found — record a path or copy a .json "
                "into %LOCALAPPDATA%\\Blossom\\paths\\"
            )

        try:
            payload = load_macro_json(path)
        except (OSError, json.JSONDecodeError) as error:
            return f"Error: {error}"

        return replay_movement_path(
            self._replayer,
            payload,
            path_file=path,
            search_dirs=OBBY_PATHS_DIRS,
            camera_down_px=camera_align_down_px_from_config(),
        )

    def replay_recording(self, path_name: str | None = None):
        if self._macro_session_gate.owner() is not None:
            return self._replay_recording_impl(path_name)

        label = self._path_filename(path_name) if path_name else "path"
        with self._macro_session(f"replay:{label}") as acquired:
            if not acquired:
                busy = self._macro_session_gate.owner() or "cooldown"
                return f"Error: macro busy ({busy}) — try again shortly"
            return self._replay_recording_impl(path_name)

    def align_camera(self, down_px: int | None = None):
        """Collections → exit → camera look-down, 3s wait, then char_align."""
        with self._macro_session("align_camera") as acquired:
            if not acquired:
                busy = self._macro_session_gate.owner() or "cooldown"
                return f"Error: macro busy ({busy}) — try again shortly"
            try:
                self._hotkeys.focus_roblox()
                time.sleep(0.12)
                if down_px is None:
                    raw = self._config.get("camera_align_down_px", 80)
                    try:
                        down_px = int(raw)
                    except (TypeError, ValueError):
                        down_px = 80
                pre_error = run_pre_path_alignment(
                    self._replayer,
                    search_dirs=OBBY_PATHS_DIRS,
                    camera_down_px=down_px,
                    cancel=self._macro_stop,
                )
                if pre_error:
                    return pre_error
                return "Aligned!"
            except Exception as error:
                print(f"[camera align] failed: {error}")
                return f"Error: {error}"

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

    def _webhook_urls(self) -> list[str]:
        return normalize_webhook_urls(
            self._config.get("webhook_url") or self._config.get("webhooks")
        )

    def send_webhook_status(self, message, color=5814783):
        urls = self._webhook_urls()
        username = self._config.get("webhook_username") or self._config.get("webhook_name")
        avatar = self._config.get("webhook_avatar") or self._config.get("webhook_avatar_url")
        sent = send_discord_webhook(
            urls,
            message=str(message or ""),
            color=color,
            username=str(username).strip() if username else None,
            avatar_url=str(avatar).strip() if avatar else None,
            title=self._config.get("webhook_title"),
        )
        print(f"[webhook] sent to {sent}/{len(urls)} url(s): {message}")
        return True

    def _log_webhook_features(self) -> None:
        """One-line summary of webhook feature wiring (helps diagnose 'nothing sent')."""
        urls = self._webhook_urls()
        notifier = self._config.get("biome_notifier") or {}
        on_biomes = [
            k
            for k in notifier
            if str(k).upper() != "NORMAL" and biome_notify_enabled(notifier, str(k))
        ]
        region = self._calibration_region("currency_region")
        print(
            "[webhook] features: "
            f"urls={len(urls)}, "
            f"status_notifs={self._status_notifs_enabled()}, "
            f"currency_enabled={self._currency_screenshot_enabled()}, "
            f"currency_region={'set' if region else 'NOT set'}, "
            f"currency_interval_min={self._currency_interval_seconds() // 60}, "
            f"biome_notifier_on={on_biomes or 'none'}, "
            f"aura_detection={self._aura_detection_enabled()}, "
            f"watcher={'on' if self._biome_watcher is not None else 'off'}"
        )

    # ----- Macro status notifications ----- #
    def _status_notifs_enabled(self) -> bool:
        if not self._webhook_urls():
            return False
        flag = self._config.get("notify_macro_status")
        return True if flag is None else bool(flag)

    def _send_status_notif(self, event: str, *, detail: str | None = None) -> None:
        if not self._status_notifs_enabled():
            return
        urls = self._webhook_urls()
        username = self._config.get("roblox_username") or None

        def _send() -> None:
            try:
                send_status_webhook(
                    urls,
                    event=event,
                    detail=detail,
                    version=display_version(),
                    username=str(username).strip() if username else None,
                )
            except Exception as error:
                print(f"[webhook] status '{event}' failed: {error}")

        Thread(target=_send, name="BlossomStatusWebhook", daemon=True).start()

    # ----- Periodic currency screenshot ----- #
    def _currency_screenshot_path(self) -> str:
        return os.path.join(os.getcwd(), "images", "currency_screenshot.png")

    def _remove_currency_screenshot_file(self) -> None:
        path = self._currency_screenshot_path()
        try:
            if os.path.isfile(path):
                os.remove(path)
                print(f"[currency] removed {path} (potion crafting active)")
        except OSError as error:
            print(f"[currency] could not remove screenshot file: {error}")

    def _currency_screenshot_enabled(self) -> bool:
        if self._potion_crafting_enabled():
            return False
        if not config_enabled(self._config, "currency_screenshot"):
            return False
        if not self._webhook_urls():
            return False
        return self._calibration_region("currency_region") is not None

    def _currency_interval_seconds(self) -> int:
        raw = self._config.get("currency_screenshot_interval", 15)
        try:
            minutes = float(raw)
        except (TypeError, ValueError):
            minutes = 15.0
        return max(60, int(minutes * 60))

    def _capture_aura_screenshot(self) -> str | None:
        try:
            import pyautogui

            shots_dir = os.path.join(os.getcwd(), "images")
            os.makedirs(shots_dir, exist_ok=True)
            path = os.path.join(shots_dir, "aura_screenshot.png")
            pyautogui.screenshot().save(path)
            return path
        except Exception as error:
            print(f"[aura] screenshot failed: {error}")
            return None

    def _capture_region_screenshot(
        self, region: tuple[int, int, int, int], filename: str
    ) -> str | None:
        try:
            import pyautogui

            shots_dir = os.path.join(os.getcwd(), "images")
            os.makedirs(shots_dir, exist_ok=True)
            path = os.path.join(shots_dir, filename)
            left, top, width, height = (int(v) for v in region)
            if width <= 0 or height <= 0:
                return None
            pyautogui.screenshot(region=(left, top, width, height)).save(path)
            return path
        except Exception as error:
            print(f"[currency] screenshot failed: {error}")
            return None

    def _run_currency_screenshot(self, *, reason: str) -> None:
        region = self._calibration_region("currency_region")
        if region is None:
            return
        urls = self._webhook_urls()
        if not urls:
            return
        path = self._capture_region_screenshot(region, "currency_screenshot.png")
        if not path:
            return
        username = self._config.get("roblox_username") or None
        ps_link = self._config.get("private_server_link") or None

        def _send() -> None:
            try:
                send_currency_webhook(
                    urls,
                    screenshot_path=path,
                    username=str(username).strip() if username else None,
                    ps_link=str(ps_link).strip() if ps_link else None,
                )
                print(f"[currency] sent screenshot ({reason})")
            except Exception as error:
                print(f"[webhook] currency send failed: {error}")

        Thread(target=_send, name="BlossomCurrencyWebhook", daemon=True).start()

    def send_currency_screenshot_now(self):
        """Manual 'Send now' from the calibration panel."""
        if self._potion_crafting_enabled():
            return {
                "ok": False,
                "error": "Currency screenshots are off while Auto Potion Craft is enabled",
            }
        if self._calibration_region("currency_region") is None:
            return {"ok": False, "error": "Mark the currency region first"}
        if not self._webhook_urls():
            return {"ok": False, "error": "Add a webhook URL on the Webhooks tab first"}
        self._run_currency_screenshot(reason="manual")
        return {"ok": True, "status": "Currency screenshot sent"}

    def _apply_always_on_top(self, enabled: bool) -> dict:
        """Idempotent Win32-only always-on-top (avoids pywebview on_top freezes)."""
        enabled = bool(enabled)
        with self._always_on_top_lock:
            if self._always_on_top_applied is enabled:
                return {"ok": True, "enabled": enabled, "skipped": True}
            if sys.platform != "win32":
                return {"ok": False, "error": "Always on top is only supported on Windows"}
            hwnd = _window_hwnd(self._window)
            if not hwnd:
                return {"ok": False, "error": "Window handle not ready — try again in a moment"}
            if not _set_always_on_top_win32(hwnd, enabled):
                return {"ok": False, "error": "SetWindowPos failed"}
            self._always_on_top_applied = enabled
            return {"ok": True, "enabled": enabled, "method": "win32"}

    def get_window_always_on_top(self):
        return {"enabled": config_enabled(self._config, "always_on_top")}

    def set_window_always_on_top(self, enabled):
        enabled = bool(enabled)
        self._config["always_on_top"] = enabled
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(
                json.dumps(self._config, indent=2),
                encoding="utf-8",
            )
        except OSError as error:
            return {"ok": False, "error": str(error)}
        return self._apply_always_on_top(enabled)

    def set_always_on_top(self, enabled):
        """Legacy React pin API — no-op path disabled in UI; delegates safely."""
        return self._apply_always_on_top(bool(enabled))

    def get_window_size(self):
        try:
            w = int(getattr(self._window, "width", 0) or 0)
            h = int(getattr(self._window, "height", 0) or 0)
            if w > 0 and h > 0:
                return {"width": w, "height": h}
        except Exception:
            pass
        w, h = _resolve_initial_window_size(self._config)
        return {"width": w, "height": h}

    def set_window_size(self, width, height, save=True):
        w, h = _clamp_window_size(width, height)
        try:
            self._window.resize(w, h)
        except Exception as error:
            return {"ok": False, "error": str(error)}
        self._config["ui_window_width"] = w
        self._config["ui_window_height"] = h
        if save:
            try:
                self._config_path.parent.mkdir(parents=True, exist_ok=True)
                self._config_path.write_text(
                    json.dumps(self._config, indent=2),
                    encoding="utf-8",
                )
            except OSError as error:
                return {"ok": False, "error": str(error)}
        return {"ok": True, "width": w, "height": h}

    def _schedule_persist_window_size(self, width: int, height: int) -> None:
        w, h = _clamp_window_size(width, height)
        self._config["ui_window_width"] = w
        self._config["ui_window_height"] = h

        def _flush() -> None:
            try:
                on_disk = load_json(self._config_path, {})
                if not isinstance(on_disk, dict):
                    on_disk = {}
                on_disk["ui_window_width"] = w
                on_disk["ui_window_height"] = h
                self._config["ui_window_width"] = w
                self._config["ui_window_height"] = h
                self._config_path.parent.mkdir(parents=True, exist_ok=True)
                self._config_path.write_text(
                    json.dumps(on_disk, indent=2),
                    encoding="utf-8",
                )
            except OSError:
                pass

        with self._window_size_save_lock:
            if self._window_size_save_timer is not None:
                self._window_size_save_timer.cancel()
            self._window_size_save_timer = threading.Timer(0.45, _flush)
            self._window_size_save_timer.daemon = True
            self._window_size_save_timer.start()

    def list_custom_ui_themes(self):
        return {"themes": list_custom_ui_themes()}

    def read_custom_ui_css(self, filename: str):
        return read_custom_ui_css(filename)

    def set_biome_detection(self, enabled):
        enabled = bool(enabled)
        self._config["enable_biome_detection"] = enabled
        if enabled:
            self._reload_config_from_disk()
            print("[main macro] START requested")
            self._hotkeys.focus_roblox()
            self._start_local_macro()
        else:
            print("[main macro] STOP requested")
            self._emergency_stop()
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
        self.stop_listeners()
        self.stop_license_guard()
        self._update_recheck_stop.set()
        self._stop_local_macro()
        self._window.destroy()

    def close(self):
        self.close_window()

    def quit_app(self):
        self.close_window()

    def window_close(self):
        self.close_window()

    def is_window_maximized(self) -> bool:
        return bool(getattr(self._window, "maximized", False))

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

    def start_window_resize(self, edge: str = "right") -> bool:
        """Begin edge resize (frameless pywebview uses manual SetWindowPos loop)."""
        if sys.platform != "win32":
            return False
        edge_key = str(edge or "").strip().lower()
        if edge_key not in _WIN32_RESIZE_EDGES:
            return False
        hwnd = _window_hwnd(self._window)
        if not hwnd:
            return False
        if not self._resize_lock.acquire(blocking=False):
            return False

        def _worker() -> None:
            try:
                _manual_resize_window(hwnd, edge_key, WIN32_MIN_WINDOW)
            finally:
                self._resize_lock.release()

        Thread(target=_worker, daemon=True).start()
        return True

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

    ensure_app_data_dirs()
    migrate_all_user_data(INSTALL_ROOT)

    config_path = resolve_config_path()
    print(f"Data folder: {APP_DATA_DIR}")
    print(f"Using config: {config_path}")
    if config_path == LOCAL_CONFIG_PATH and not APP_CONFIG_PATH.exists():
        print("No config in AppData yet — using config.json beside the app until you save settings.")

    api = LocalUiApi()
    init_w, init_h = _resolve_initial_window_size(api._config)
    window = webview.create_window(
        "Blossom",
        url=ui_url(),
        width=init_w,
        height=init_h,
        min_size=WIN32_MIN_WINDOW,
        resizable=True,
        frameless=True,
        easy_drag=False,
        shadow=True,
        background_color="#09090b",
        js_api=api,
    )

    def on_ready():
        apply_windows_window_icon(window, APP_ICON_PATH)
        apply_windows_frameless_chrome(window)

        def _on_window_resized(_width, _height) -> None:
            try:
                api._schedule_persist_window_size(_width, _height)
                window.evaluate_js(
                    "window.BlossomTitlebar&&window.BlossomTitlebar.syncChromeState&&"
                    "window.BlossomTitlebar.syncChromeState();"
                    "window.BlossomAppearance&&window.BlossomAppearance.refreshWindowFields&&"
                    "window.BlossomAppearance.refreshWindowFields();"
                )
            except Exception:
                pass

        events = getattr(window, "events", None)
        if events is not None and hasattr(events, "resized"):
            events.resized += _on_window_resized

        def _retry_window_chrome() -> None:
            time.sleep(0.35)
            apply_windows_window_icon(window, APP_ICON_PATH)
            apply_windows_frameless_chrome(window)

        def _restore_always_on_top() -> None:
            time.sleep(0.55)
            if config_enabled(api._config, "always_on_top"):
                api._apply_always_on_top(True)

        Thread(target=_retry_window_chrome, daemon=True).start()
        Thread(target=_restore_always_on_top, daemon=True).start()
        api.init_hotkeys()
        api.start_listeners()
        api.start_license_guard()
        api.check_for_updates()
        api.boot_install_runtime_deps()

    webview.start(debug=False, func=on_ready)
    api._stop_local_macro()
    api._hotkeys.unregister()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
