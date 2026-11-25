from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

_FIELDS = {
    "Material": ("材料工程", 10000, "获得 1 件传说或神话装备"),
    "Energy": ("能源工程", 20000, "全队参与击杀敌方实验体 5 次"),
    "Biotechnology": ("生命工程", 30000, "全队击败 60 只指定怪物"),
}
_REPEAT_CONDITIONS = {
    21: "获得 3 件传说或神话装备",
    22: "全队参与击杀敌方实验体 2 次",
    23: "全队击杀 25 只指定怪物",
}


def experiment_summary(players: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Read a team's research tasks from DAK.GG player records."""
    for player in players:
        field = player.get("experimentResultType")
        if isinstance(field, str) and field in _FIELDS:
            break
    else:
        return None

    name, group, start_condition = _FIELDS[field]
    first_clear = None
    repeat_counts = dict.fromkeys(_REPEAT_CONDITIONS, 0)
    for player in players:
        steps = player.get("questStepClear")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, Mapping):
                continue
            group_id = step.get("experimentGroupId")
            count = step.get("clearCount")
            if type(group_id) is not int or type(count) is not int or count <= 0:
                continue
            offset = group_id - group
            if offset in repeat_counts:
                # DAK repeats shared progress on multiple players in the same team.
                repeat_counts[offset] = max(repeat_counts[offset], count)
            elif offset == 11:
                elapsed = step.get("firstClearElapsedSeconds")
                if type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0:
                    seconds = int(elapsed)
                    first_clear = seconds if first_clear is None else min(first_clear, seconds)
    return {
        "type": field,
        "name": name,
        "startCondition": start_condition,
        "firstClearSeconds": first_clear,
        "repeatTasks": [
            {"condition": condition, "count": repeat_counts[offset]}
            for offset, condition in _REPEAT_CONDITIONS.items()
        ],
    }
