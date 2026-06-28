from __future__ import annotations

from conductor.adapters.base import Usage

THRESHOLDS = (50, 25, 15, 10, 5, 2)


def crossed_thresholds(usage: Usage, already_fired: tuple[int, ...]) -> tuple[int, ...]:
    fired = set(already_fired)
    remaining = usage.pct_remaining
    for threshold in THRESHOLDS:
        if remaining <= threshold:
            fired.add(threshold)
    return tuple(sorted(fired, reverse=True))
