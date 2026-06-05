"""User data directory: %LOCALAPPDATA%\\Blossom (config, paths, potions)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

LEGACY_COTEAB_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "CoteabMacro"
APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "Blossom"
APP_CONFIG_PATH = APP_DATA_DIR / "config.json"
POTION_DIR = APP_DATA_DIR / "crafting_files_do_not_open"
OBBY_PATHS_DIR = APP_DATA_DIR / "paths"
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
    POTION_DIR.mkdir(parents=True, exist_ok=True)
    OBBY_PATHS_DIR.mkdir(parents=True, exist_ok=True)


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
