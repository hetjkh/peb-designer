"""Parse bay/span spacing strings used in PEB inputs.

Supported forms (metres):
    20          → [20.0]
    2@30        → [30.0, 30.0]
    30+30       → [30.0, 30.0]
    3@20+15     → [20.0, 20.0, 20.0, 15.0]
    10+2@15+10  → [10.0, 15.0, 15.0, 10.0]

This is a convenience syntax only — not a design-code rule.
"""

from __future__ import annotations

import re
from typing import List


_TOKEN = re.compile(
    r"^\s*(?:(?P<count>\d+)\s*@\s*)?(?P<value>\d+(?:\.\d+)?)\s*$"
)


def parse_spacing_list(text: str, *, field_name: str = "Spacing") -> List[float]:
    """Parse a spacing expression into a list of positive lengths."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError(f"{field_name} is required.")

    parts = re.split(r"[+,;]+", raw)
    values: List[float] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        match = _TOKEN.match(part)
        if not match:
            raise ValueError(
                f"{field_name} has invalid token '{part}'. "
                "Use forms like 20, 2@30, or 30+30."
            )
        count = int(match.group("count") or "1")
        value = float(match.group("value"))
        if count < 1:
            raise ValueError(f"{field_name}: repeat count must be ≥ 1.")
        if value <= 0:
            raise ValueError(f"{field_name}: lengths must be > 0.")
        values.extend([value] * count)

    if not values:
        raise ValueError(f"{field_name} produced no lengths.")
    return values


def spacing_total(values: List[float]) -> float:
    return float(sum(values))
