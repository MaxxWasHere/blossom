"""Aura rarity lookup for webhook pings (assets/auras.json)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_AURA_KEY_RE = re.compile(r"[^a-z0-9]+", re.IGNORECASE)


def _normalize_key(name: str) -> str:
    return _AURA_KEY_RE.sub("", str(name or "").strip().lower())


def load_aura_table(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _index_table(path_str: str) -> dict[str, dict[str, Any]]:
    table = load_aura_table(Path(path_str))
    index: dict[str, dict[str, Any]] = {}
    for key, entry in table.items():
        if not isinstance(entry, dict):
            continue
        norm = _normalize_key(key)
        if norm:
            index[norm] = entry
        spaced = _normalize_key(str(key).replace("_", " "))
        if spaced:
            index.setdefault(spaced, entry)
    return index


def aura_rarity(path: Path, aura_name: str) -> int | None:
    """Return 1-in-X rarity for an equipped aura name, or None if unknown."""
    index = _index_table(str(path.resolve()))
    norm = _normalize_key(aura_name)
    if not norm:
        return None
    entry = index.get(norm)
    if not entry:
        return None
    try:
        value = int(entry.get("rarity"))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def parse_force_ping_auras(raw: Any) -> set[str]:
    """Comma-separated aura names that always trigger a ping."""
    text = str(raw or "").strip()
    if not text:
        return set()
    out: set[str] = set()
    for part in text.split(","):
        name = part.strip()
        if name:
            out.add(_normalize_key(name))
    return out


def should_ping_aura(
    aura_name: str,
    *,
    aura_table_path: Path,
    ping_minimum: Any,
    force_ping_auras: Any,
) -> tuple[bool, int | None]:
    """True when rarity meets the threshold or the aura is in the force list."""
    force = parse_force_ping_auras(force_ping_auras)
    norm = _normalize_key(aura_name)
    if norm and norm in force:
        return True, aura_rarity(aura_table_path, aura_name)

    try:
        minimum = int(str(ping_minimum or "100000").strip().replace(",", "") or "100000")
    except ValueError:
        minimum = 100_000

    rarity = aura_rarity(aura_table_path, aura_name)
    if rarity is None:
        return False, None
    return rarity >= minimum, rarity
