"""Structured intent, as defined by the receipt contract (docs/contracts/receipt.md#intent).

The compiler receives an intent whose time range is already resolved to
absolute dates; resolving "last quarter" is the server's job.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

OPS = ("=", "!=", "<", "<=", ">", ">=", "in", "not_in", "is_null", "is_not_null")


@dataclass(frozen=True)
class Filter:
    column: str
    op: str
    value: Any = None  # scalar; list for in/not_in; None for is_null/is_not_null

    @classmethod
    def from_dict(cls, data: dict) -> Filter:
        return cls(column=data["column"], op=data["op"], value=data.get("value"))


@dataclass(frozen=True)
class TimeRange:
    start: dt.date  # inclusive
    end: dt.date  # exclusive
    as_of: dt.date
    relative: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> TimeRange:
        return cls(
            start=_date(data["start"]),
            end=_date(data["end"]),
            as_of=_date(data["as_of"]),
            relative=data.get("relative"),
        )


@dataclass(frozen=True)
class Intent:
    metric: str
    time_grain: str
    time_range: TimeRange
    dimensions: tuple[str, ...] = ()
    filters: tuple[Filter, ...] = ()

    @classmethod
    def from_dict(cls, data: dict) -> Intent:
        return cls(
            metric=data["metric"],
            time_grain=data["time_grain"],
            time_range=TimeRange.from_dict(data["time_range"]),
            dimensions=tuple(data.get("dimensions", ())),
            filters=tuple(Filter.from_dict(f) for f in data.get("filters", ())),
        )


def _date(value: str | dt.date) -> dt.date:
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(value)
