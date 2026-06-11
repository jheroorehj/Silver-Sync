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


# JSON 파싱 후 문자열 리스트로 안전하게 강제. 모델이 list 대신 str("없음" 등)을 내면
# Python 기본 `[str(x) for x in value]`는 char 단위로 깨져 안전 게이트가 오작동(예: red_flags).
_NEG_LIST_TOKENS = {"", "없음", "없다", "없어요", "n/a", "none", "null", "[]", "-", "x"}


def coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.lower() in _NEG_LIST_TOKENS or text in _NEG_LIST_TOKENS:
            return []
        return [text]
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            s = str(item).strip()
            if not s:
                continue
            if s.lower() in _NEG_LIST_TOKENS:
                continue
            out.append(s)
        return out
    s = str(value).strip()
    return [s] if s else []


def coerce_bool(value: Any) -> bool:
    """JSON 출력에서 안전한 boolean. 'false'/'no'/'0' 같은 문자열을 False로 처리."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "t", "예", "참"}
    return False


def _to_int(value: Any) -> int | None:
    parsed = to_float(value)
    return int(parsed) if parsed is not None else None

