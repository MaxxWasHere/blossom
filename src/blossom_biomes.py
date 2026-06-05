"""Roblox-log biome + aura reader (port of Noteab detection).

Tails the newest Roblox log on Windows (%LOCALAPPDATA%\\Roblox\\logs). Sol's RNG
writes Bloxstrap-style RichPresence lines:
  - biome name in   largeImage.hoverText   ("NORMAL" = no biome)
  - equipped aura in state                  (Equipped "X" / Equipped _None_)

Fires callbacks so the consumer decides what to do (GLITCHED -> buff pop, or send
biome / aura Discord webhooks). The watcher can run for the whole app lifetime so
biomes and aura changes are never missed, even when the macro is idle.
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import Callable

GLITCHED_BIOME = "GLITCHED"
# Per-key re-trigger guard so one continuous biome/aura window only fires once.
BIOME_COOLDOWN_SEC = 300.0
AURA_COOLDOWN_SEC = 20.0

# Biome lives in largeImage.hoverText (smallImage.hoverText is always "Sol's RNG").
_HOVER_RE = re.compile(
    r'"largeImage"\s*:\s*\{\s*"hoverText"\s*:\s*"([^"]+)"', re.IGNORECASE
)
# Equipped aura, e.g.  "state":"Equipped \"Celestial\"","smallImage"
_AURA_RE = re.compile(
    r'"state"\s*:\s*"Equipped\s+(.+?)"\s*,\s*"smallImage"', re.IGNORECASE
)


def _clean_aura(raw: str) -> str | None:
    cleaned = raw.replace("\\", "").strip().strip('"').strip()
    if not cleaned or cleaned.upper() in ("_NONE_", "NONE"):
        return None
    # RPC encodes spaces/colons as underscores (e.g. Astral_Legendarium).
    return cleaned.replace("_", " ").strip()


def _roblox_logs_dir() -> Path | None:
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return None
    logs = Path(local) / "Roblox" / "logs"
    return logs if logs.is_dir() else None


def get_latest_log_file() -> str | None:
    logs_dir = _roblox_logs_dir()
    if logs_dir is None:
        return None
    try:
        candidates = sorted(
            logs_dir.glob("*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    return str(candidates[0]) if candidates else None


class BiomeWatcher:
    """Background thread that tails the newest Roblox log for biome + aura changes."""

    def __init__(
        self,
        *,
        on_biome: Callable[[str], None],
        on_aura: Callable[[str], None] | None = None,
        stop_event: threading.Event,
        poll_interval: float = 1.0,
        cooldown: float = BIOME_COOLDOWN_SEC,
    ) -> None:
        self._on_biome = on_biome
        self._on_aura = on_aura
        self._stop = stop_event
        self._poll = max(0.25, float(poll_interval))
        self._cooldown = max(0.0, float(cooldown))
        self._thread: threading.Thread | None = None
        self._last_position = 0
        self._last_log_file: str | None = None
        self._current_biome: str | None = None
        self._current_aura: str | None = None
        self._last_fired: dict[str, float] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="BlossomBiomeWatcher", daemon=True)
        self._thread.start()
        print("[biome] watcher started (always-on)")

    def _prime_current(self, log_file: str) -> None:
        """On first attach: announce the biome we're CURRENTLY in (once) and set
        the current aura silently (so we only ping on aura *changes*, not the
        already-equipped one). No replaying of past biomes."""
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read()
                self._last_position = handle.tell()
        except OSError:
            self._last_position = 0
            return

        biome = None
        for match in _HOVER_RE.finditer(content):
            name = match.group(1).strip().upper()
            biome = None if name == "NORMAL" else name
        self._current_biome = biome

        aura = None
        for match in _AURA_RE.finditer(content):
            aura = _clean_aura(match.group(1)) or aura
        self._current_aura = aura

        if biome:
            print(f"[biome] current biome at start: {biome}")
            self._fire_biome(biome)

    def _read_new_lines(self, log_file: str) -> list[str]:
        if log_file != self._last_log_file:
            self._last_log_file = log_file
            self._current_biome = None
            self._current_aura = None
            self._prime_current(log_file)
            return []
        if not os.path.exists(log_file):
            return []
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as handle:
                handle.seek(self._last_position)
                lines = handle.readlines()
                self._last_position = handle.tell()
                return lines
        except OSError as error:
            print(f"[biome] read failed: {error}")
            return []

    def _cooldown_ok(self, key: str) -> bool:
        now = time.time()
        if now - self._last_fired.get(key, 0.0) < self._cooldown:
            return False
        self._last_fired[key] = now
        return True

    def _fire_biome(self, name: str) -> None:
        if not self._cooldown_ok("biome:" + name):
            return
        print(f"[biome] {name} detected")
        try:
            self._on_biome(name)
        except Exception as error:
            print(f"[biome] callback error for {name}: {error}")

    def _fire_aura(self, name: str) -> None:
        if self._on_aura is None:
            return
        now = time.time()
        if now - self._last_fired.get("aura:" + name, 0.0) < AURA_COOLDOWN_SEC:
            return
        self._last_fired["aura:" + name] = now
        print(f"[aura] equipped {name}")
        try:
            self._on_aura(name)
        except Exception as error:
            print(f"[aura] callback error for {name}: {error}")

    def _check_lines(self, lines: list[str]) -> None:
        for line in lines:
            bmatch = _HOVER_RE.search(line)
            if bmatch:
                name = bmatch.group(1).strip().upper()
                if name and name == "NORMAL":
                    self._current_biome = None
                elif name and name != self._current_biome:
                    self._current_biome = name
                    self._fire_biome(name)

            amatch = _AURA_RE.search(line)
            if amatch:
                aura = _clean_aura(amatch.group(1))
                if aura is None:
                    self._current_aura = None
                elif aura != self._current_aura:
                    self._current_aura = aura
                    self._fire_aura(aura)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                log_file = get_latest_log_file()
                if log_file is None:
                    self._stop.wait(self._poll * 3)
                    continue
                lines = self._read_new_lines(log_file)
                if lines:
                    self._check_lines(lines)
            except Exception as error:
                print(f"[biome] watcher loop error: {error}")
            self._stop.wait(self._poll)
        print("[biome] watcher stopped")
