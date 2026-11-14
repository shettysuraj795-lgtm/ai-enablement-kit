"""Resolve relative periods to absolute, half-open date ranges.

The server resolves "last quarter" against a recorded as-of date, so the
compiled SQL never depends on the current date (receipt contract,
mcp-tool-design step 2). Periods are complete: the as-of day itself is
excluded because its data is not complete yet.
"""

from __future__ import annotations

import datetime as dt

from governed_analytics.intent import TimeRange

RELATIVE_PERIODS = ("last_quarter", "last_month", "last_4_weeks", "year_to_date")


def resolve(relative: str, as_of: dt.date) -> TimeRange:
    if relative == "last_quarter":
        this_quarter = dt.date(as_of.year, 3 * ((as_of.month - 1) // 3) + 1, 1)
        start, end = _add_months(this_quarter, -3), this_quarter
    elif relative == "last_month":
        this_month = as_of.replace(day=1)
        start, end = _add_months(this_month, -1), this_month
    elif relative == "last_4_weeks":
        this_week = as_of - dt.timedelta(days=as_of.weekday())  # weeks start on Monday
        start, end = this_week - dt.timedelta(weeks=4), this_week
    elif relative == "year_to_date":
        start, end = dt.date(as_of.year, 1, 1), as_of
    else:
        raise ValueError(f"Unknown period '{relative}'. Use one of: {', '.join(RELATIVE_PERIODS)}.")
    return TimeRange(start=start, end=end, as_of=as_of, relative=relative)


def _add_months(first_of_month: dt.date, months: int) -> dt.date:
    index = first_of_month.year * 12 + first_of_month.month - 1 + months
    return dt.date(index // 12, index % 12 + 1, 1)
