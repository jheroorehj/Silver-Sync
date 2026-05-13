from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:\.\d)?", str(value))
    return float(match.group(0)) if match else None


def parse_blood_pressure(value: Any) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    if isinstance(value, dict):
        return _to_int(value.get("systolic")), _to_int(value.get("diastolic"))
    numbers = re.findall(r"\d+", str(value))
    if len(numbers) >= 2:
        return int(numbers[0]), int(numbers[1])
    return None, None


def normalize_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    return str(value) if value else "N/A"


def latest_numeric(values: list[float | int | None]) -> float | None:
    for value in values:
        if value is not None:
            return float(value)
    return None


def trend_delta_desc(values_newest_first: list[float | int | None]) -> float | None:
    clean = [float(v) for v in values_newest_first if v is not None]
    if len(clean) < 2:
        return None
    return round(clean[0] - clean[-1], 2)


def contains_any(texts: list[str], keywords: list[str]) -> bool:
    joined = " ".join(t.lower() for t in texts if t)
    return any(keyword.lower() in joined for keyword in keywords)


def clamp(value: int | float, low: int = 0, high: int = 100) -> int:
    return int(max(low, min(high, round(value))))


def _to_int(value: Any) -> int | None:
    parsed = to_float(value)
    return int(parsed) if parsed is not None else None

