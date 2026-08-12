"""Field-level data quality tags for UZI reports.

The report pipeline mixes live API values, formula-derived fields, estimates,
and genuinely unavailable fields. Keeping that distinction explicit prevents
rule output and role-play commentary from presenting assumptions as facts.
"""
from __future__ import annotations

from typing import Any


class DataQuality:
    ACTUAL = "actual"
    DERIVED = "derived"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


def mark_field(value: Any, quality: str, source: str = "", note: str = "") -> dict[str, Any]:
    return {"value": value, "quality": quality, "source": source, "note": note}


def unwrap(data: Any, default: Any = None) -> Any:
    if isinstance(data, dict) and "value" in data:
        return data["value"]
    return data if data is not None else default


def build_quality_report(fields: dict[str, Any]) -> dict[str, Any]:
    counts = {
        DataQuality.ACTUAL: 0,
        DataQuality.DERIVED: 0,
        DataQuality.ESTIMATED: 0,
        DataQuality.UNAVAILABLE: 0,
    }
    estimated_fields: list[str] = []
    unavailable_fields: list[str] = []

    for name, field in fields.items():
        if not isinstance(field, dict) or "quality" not in field:
            continue
        quality = str(field.get("quality") or "")
        if quality not in counts:
            continue
        counts[quality] += 1
        if quality == DataQuality.ESTIMATED:
            estimated_fields.append(name)
        elif quality == DataQuality.UNAVAILABLE:
            unavailable_fields.append(name)

    weak_count = counts[DataQuality.ESTIMATED] + counts[DataQuality.UNAVAILABLE]
    if weak_count == 0:
        overall = "high"
    elif weak_count <= 2:
        overall = "medium"
    else:
        overall = "low"

    return {
        "actual_count": counts[DataQuality.ACTUAL],
        "derived_count": counts[DataQuality.DERIVED],
        "estimated_count": counts[DataQuality.ESTIMATED],
        "unavailable_count": counts[DataQuality.UNAVAILABLE],
        "estimated_fields": estimated_fields,
        "unavailable_fields": unavailable_fields,
        "overall_quality": overall,
    }
