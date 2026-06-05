"""Exclusive gate so only one Roblox UI macro action runs at a time."""

from __future__ import annotations

import time
from threading import Lock


class MacroSessionGate:
    """Serializes inventory, menus, crafting, merchant, quests, and path replay."""

    def __init__(self, *, settle_sec: float = 0.75) -> None:
        self._lock = Lock()
        self._owner: str | None = None
        self._free_after = 0.0
        self._settle_sec = max(0.0, settle_sec)

    def owner(self) -> str | None:
        with self._lock:
            return self._owner

    def is_idle(self, *, replayer_running: bool = False, stop_set: bool = False) -> bool:
        if stop_set or replayer_running:
            return False
        with self._lock:
            if self._owner is not None:
                return False
            return time.monotonic() >= self._free_after

    def try_acquire(
        self,
        owner: str,
        *,
        replayer_running: bool = False,
        stop_set: bool = False,
    ) -> bool:
        if stop_set:
            return False
        if replayer_running:
            print(f"[main macro] session skip {owner}: path replay running")
            return False
        now = time.monotonic()
        with self._lock:
            if self._owner is not None:
                print(
                    f"[main macro] session busy ({self._owner}); "
                    f"skipped {owner}"
                )
                return False
            if now < self._free_after:
                wait = self._free_after - now
                print(
                    f"[main macro] session cooldown ({wait:.2f}s left); "
                    f"skipped {owner}"
                )
                return False
            self._owner = owner
            print(f"[main macro] session acquired: {owner}")
            return True

    def release(self, owner: str) -> None:
        with self._lock:
            if self._owner != owner:
                return
            self._owner = None
            self._free_after = time.monotonic() + self._settle_sec
            print(
                f"[main macro] session released: {owner} "
                f"(cooldown {self._settle_sec:.2f}s)"
            )

    def force_release(self) -> None:
        with self._lock:
            prev = self._owner
            self._owner = None
            self._free_after = 0.0
            if prev:
                print(f"[main macro] session force-released: {prev}")
