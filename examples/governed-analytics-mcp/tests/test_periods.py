from __future__ import annotations

import datetime as dt

import pytest
import yaml
from golden_answers import GOLDEN, answer_nodes

from governed_analytics.intent import TimeRange
from governed_analytics.periods import RELATIVE_PERIODS, resolve


def _golden_ranges():
    seen = set()
    for question in yaml.safe_load(GOLDEN.read_text())["questions"]:
        for node in answer_nodes(question):
            time_range = node["intent"]["time_range"]
            if "relative" in time_range and time_range["relative"] not in seen:
                seen.add(time_range["relative"])
                yield pytest.param(time_range, id=time_range["relative"])


@pytest.mark.parametrize("expected", list(_golden_ranges()))
def test_matches_golden_time_ranges(expected):
    resolved = resolve(expected["relative"], dt.date.fromisoformat(expected["as_of"]))
    assert resolved == TimeRange.from_dict(expected)


def test_golden_questions_use_only_known_periods():
    used = {p.values[0]["relative"] for p in _golden_ranges()}
    assert used <= set(RELATIVE_PERIODS)


@pytest.mark.parametrize(
    ("relative", "as_of", "start", "end"),
    [
        ("last_quarter", "2026-01-15", "2025-10-01", "2026-01-01"),  # across a year end
        ("last_month", "2026-01-01", "2025-12-01", "2026-01-01"),
        ("last_4_weeks", "2026-11-09", "2026-10-12", "2026-11-09"),  # as_of is a Monday
        ("year_to_date", "2026-01-01", "2026-01-01", "2026-01-01"),  # empty on 1 January
    ],
)
def test_edges(relative, as_of, start, end):
    resolved = resolve(relative, dt.date.fromisoformat(as_of))
    assert (resolved.start.isoformat(), resolved.end.isoformat()) == (start, end)


def test_unknown_period_names_the_options():
    with pytest.raises(ValueError, match="last_quarter, last_month"):
        resolve("last_fortnight", dt.date(2026, 11, 14))
