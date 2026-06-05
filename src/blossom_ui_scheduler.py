"""Pick one UI-heavy macro task at a time (used with MacroSessionGate for exclusivity)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum, auto


class MacroUiTask(Enum):
    MERCHANT = auto()
    MERCHANT_THEN_QUESTS = auto()
    BUFFS = auto()
    SC = auto()
    BR = auto()
    BIOME_SELECTOR = auto()
    POTION = auto()
    QUEST = auto()
    OBBY = auto()


# Lower number = runs before other due tasks (inventory-sensitive first).
# Glitched buffs are time-critical (the biome window is short), so they win.
TASK_PRIORITY: dict[MacroUiTask, int] = {
    MacroUiTask.BUFFS: 5,
    MacroUiTask.MERCHANT: 10,
    MacroUiTask.MERCHANT_THEN_QUESTS: 10,
    MacroUiTask.SC: 14,
    MacroUiTask.BR: 16,
    MacroUiTask.BIOME_SELECTOR: 17,
    MacroUiTask.POTION: 20,
    MacroUiTask.QUEST: 30,
    MacroUiTask.OBBY: 40,
}


@dataclass(frozen=True)
class ScheduledUiTask:
    task: MacroUiTask
    priority: int


def schedule(task: MacroUiTask) -> ScheduledUiTask:
    return ScheduledUiTask(task=task, priority=TASK_PRIORITY[task])


def pick_task(
    tasks: list[ScheduledUiTask],
    *,
    randomize_ties: bool = True,
) -> ScheduledUiTask | None:
    """Return a single task to run; optional random choice among equal priority."""
    if not tasks:
        return None
    best = min(entry.priority for entry in tasks)
    pool = [entry for entry in tasks if entry.priority == best]
    if randomize_ties and len(pool) > 1:
        chosen = random.choice(pool)
        names = ", ".join(entry.task.name for entry in pool)
        print(f"[main macro] UI scheduler: tie-break {chosen.task.name} among [{names}]")
        return chosen
    return pool[0]


def startup_order(tasks: list[MacroUiTask]) -> list[MacroUiTask]:
    """Run every startup task once, highest priority (lowest number) first."""
    return sorted(set(tasks), key=lambda task: TASK_PRIORITY[task])
