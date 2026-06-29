"""User data directory: %LOCALAPPDATA%\\Blossom (config, paths, potions)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

LEGACY_COTEAB_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "CoteabMacro"
APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "Blossom"
LOGS_DIR = APP_DATA_DIR / "logs"
APP_CONFIG_PATH = APP_DATA_DIR / "config.json"
POTION_DIR = APP_DATA_DIR / "crafting_files_do_not_open"
OBBY_PATHS_DIR = APP_DATA_DIR / "paths"
# Externalized optional runtime dependencies (e.g. OpenCV) are downloaded on
# demand and cached here instead of bloating the shipped exe. Native code loaded
# from this dir is hash-verified against a pinned constant before use; see
# blossom_runtime_deps.py.
RUNTIME_DEPS_DIR = APP_DATA_DIR / "runtime"
RUNTIME_MANIFEST_STATE = RUNTIME_DEPS_DIR / "manifest-state.json"
APP_STABLE_DIR = APP_DATA_DIR / "app" / "stable"
APP_BETA_DIR = APP_DATA_DIR / "app" / "beta"
THEMES_DIR = APP_DATA_DIR / "themes"
CHAR_ALIGN_FILENAME = "char_align.json"
CHAR_ALIGN_PATH = OBBY_PATHS_DIR / CHAR_ALIGN_FILENAME


def dev_repo_root() -> Path:
    """Repository root when running from source (parent of src/)."""
    here = Path(__file__).resolve().parent
    if here.name == "src":
        return here.parent
    return here


def install_adjacent_blossom(install_root: Path) -> Path:
    """Old layout: Blossom/ next to BlossomMacro.exe or the repo root."""
    return install_root / "Blossom"


def ensure_app_data_dirs() -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    POTION_DIR.mkdir(parents=True, exist_ok=True)
    OBBY_PATHS_DIR.mkdir(parents=True, exist_ok=True)
    THEMES_DIR.mkdir(parents=True, exist_ok=True)


def reveal_folder_in_explorer(folder: Path | str) -> dict[str, object]:
    """Open *folder* in Windows Explorer, creating it first if missing.

    pywebview dispatches JS-API calls on a worker thread where ``os.startfile``
    can land Explorer behind the app window — Windows blocks a background
    thread from claiming the foreground, so the user sees "nothing happen".
    Spawning ``explorer`` as its own process hands the open request to the
    already-running Explorer instance (reliable across threads);
    ``os.startfile`` / ``webbrowser`` stay as fallbacks.
    """
    path = Path(folder)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return {"ok": False, "path": str(path), "error": f"could not create folder: {error}"}

    target = str(path.resolve())
    errors: list[str] = []

    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
        except Exception:
            pass
        for opener in (
            lambda: subprocess.Popen(["explorer", target]),
            lambda: os.startfile(target),  # noqa: S606
        ):
            try:
                opener()
                return {"ok": True, "path": target}
            except Exception as error:  # noqa: BLE001
                errors.append(str(error))
    else:
        try:
            import webbrowser

            webbrowser.open(target)
            return {"ok": True, "path": target}
        except Exception as error:  # noqa: BLE001
            errors.append(str(error))

    return {"ok": False, "path": target, "error": "; ".join(errors) or "could not open folder"}


def ensure_runtime_deps_dir() -> Path:
    """Create and return the cache dir for externalized runtime dependencies."""
    RUNTIME_DEPS_DIR.mkdir(parents=True, exist_ok=True)
    return RUNTIME_DEPS_DIR


def app_channel_dir(channel: str | None = None) -> Path:
    """Managed app payload dir: %LOCALAPPDATA%\\Blossom\\app\\{stable|beta}."""
    ch = str(channel or "stable").strip().lower()
    return APP_BETA_DIR if ch == "beta" else APP_STABLE_DIR


def current_app_json_path(channel: str | None = None) -> Path:
    return app_channel_dir(channel) / "current.json"


def ui_ready_marker_path() -> Path:
    """Written by the main app when pywebview is ready; bootstrap polls this."""
    return APP_DATA_DIR / ".ui-ready"


def is_managed_install() -> bool:
    return os.environ.get("BLOSSOM_MANAGED", "").strip() == "1"


def managed_channel() -> str:
    raw = os.environ.get("BLOSSOM_CHANNEL", "").strip().lower()
    if raw in ("stable", "beta"):
        return raw
    try:
        from blossom_updater import build_channel

        return build_channel()
    except Exception:
        return "stable"


def _copy_tree_files(source_dir: Path, dest_dir: Path, pattern: str, label: str) -> None:
    if not source_dir.is_dir():
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    for source in source_dir.glob(pattern):
        dest = dest_dir / source.name
        if not dest.exists():
            shutil.copy2(source, dest)
            print(f"[blossom] migrated {label} {source.name}")


def migrate_from_legacy_coteab() -> None:
    """One-time copy from %LOCALAPPDATA%\\CoteabMacro."""
    legacy = LEGACY_COTEAB_DIR
    if not legacy.is_dir():
        return

    legacy_config = legacy / "config.json"
    if legacy_config.is_file() and not APP_CONFIG_PATH.exists():
        ensure_app_data_dirs()
        shutil.copy2(legacy_config, APP_CONFIG_PATH)
        print(f"[blossom] migrated config from {legacy_config}")

    _copy_tree_files(
        legacy / "crafting_files_do_not_open",
        POTION_DIR,
        "*.json",
        "potion",
    )
    _copy_tree_files(legacy / "paths", OBBY_PATHS_DIR, "*.json", "path")


def migrate_from_install_folder(install_root: Path) -> None:
    """One-time copy from Blossom/ beside the exe or dev repo (older Blossom layout)."""
    adjacent = install_adjacent_blossom(install_root)
    if not adjacent.is_dir() or adjacent.resolve() == APP_DATA_DIR.resolve():
        return

    ensure_app_data_dirs()

    adjacent_config = adjacent / "config.json"
    if adjacent_config.is_file() and not APP_CONFIG_PATH.exists():
        shutil.copy2(adjacent_config, APP_CONFIG_PATH)
        print(f"[blossom] migrated config from {adjacent_config}")

    _copy_tree_files(
        adjacent / "crafting_files_do_not_open",
        POTION_DIR,
        "*.json",
        "potion",
    )
    _copy_tree_files(adjacent / "paths", OBBY_PATHS_DIR, "*.json", "path")


def migrate_all_user_data(install_root: Path) -> None:
    migrate_from_legacy_coteab()
    migrate_from_install_folder(install_root)
