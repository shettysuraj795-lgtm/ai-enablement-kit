"""Compile a structured intent and one metric definition into SQL.

The model chooses the intent; this module turns it into SQL deterministically.
Same intent + same metric version + same COMPILER_VERSION must give
byte-identical SQL, because receipts and replay depend on it (ADR-002).
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

from governed_analytics.catalogue import Metric
from governed_analytics.intent import OPS, Filter, Intent

COMPILER_VERSION = "0.1.0"

MARTS_SCHEMA = "marts"

PERIOD = "period"

_COMPARISONS = ("=", "!=", "<", "<=", ">", ">=")
_LIST_OPS = {"in": "IN", "not_in": "NOT IN"}
_NULL_OPS = {"is_null": "IS NULL", "is_not_null": "IS NOT NULL"}


class IntentError(ValueError):
    """The intent is not valid for the metric.

    The message is returned to the model as a tool error, so it must say what
    to do next: name the valid options (see skills/certified/mcp-tool-design).
    """


def compile_intent(intent: Intent, metric: Metric) -> str:
    """Return the SQL that answers `intent` using `metric`.

    The expected format is pinned by tests/test_compiler.py; the first test is
    the worked example in docs/contracts/receipt.md.
    """
    _validate(intent, metric)

    # Sorting is what makes the output independent of the order the model
    # happened to list things in.
    dimensions = sorted(set(intent.dimensions))
    user_filters = sorted({_render_filter(f) for f in intent.filters})

    time_column = metric.time_dimension
    select = [
        f"date_trunc('{intent.time_grain}', {time_column}) AS {PERIOD}",
        *dimensions,
        f"{metric.expression} AS {metric.name}",
    ]
    where = [
        *(_render_filter(f) for f in metric.filters),  # the metric's own, in definition order
        *user_filters,
        f"{time_column} >= {_literal(intent.time_range.start)}",
        f"{time_column} < {_literal(intent.time_range.end)}",
    ]
    group = ", ".join([PERIOD, *dimensions])

    return (
        f"SELECT {', '.join(select)} "
        f"FROM {MARTS_SCHEMA}.{metric.model} "
        f"WHERE {' AND '.join(where)} "
        f"GROUP BY {group} ORDER BY {group}"
    )


def _validate(intent: Intent, metric: Metric) -> None:
    allowed = ", ".join(metric.allowed_dimensions)

    if intent.metric != metric.name:
        raise IntentError(
            f"Intent asks for metric '{intent.metric}' but was given the definition of "
            f"'{metric.name}'. Look up '{intent.metric}' in the catalogue and compile against that."
        )
    if intent.time_grain not in metric.time_grains:
        raise IntentError(
            f"Time grain '{intent.time_grain}' is not available for {metric.name}. "
            f"Use one of: {', '.join(metric.time_grains)}."
        )
    for dimension in intent.dimensions:
        if dimension not in metric.allowed_dimensions:
            raise IntentError(
                f"Dimension '{dimension}' is not available for {metric.name}. "
                f"Use one of: {allowed}."
            )
    for f in intent.filters:
        if f.column not in metric.allowed_dimensions:
            raise IntentError(
                f"Cannot filter {metric.name} on '{f.column}'. "
                f"Filter on one of: {allowed}."
            )
        _check_filter(f)
    if intent.time_range.start >= intent.time_range.end:
        raise IntentError(
            f"Time range is empty: start {intent.time_range.start.isoformat()} must be before "
            f"end {intent.time_range.end.isoformat()} (end is exclusive)."
        )


def _check_filter(f: Filter) -> None:
    if f.op not in OPS:
        raise IntentError(
            f"Unknown filter operator '{f.op}' on '{f.column}'. Use one of: {', '.join(OPS)}."
        )
    if f.op in _LIST_OPS:
        if not isinstance(f.value, (list, tuple)) or not f.value:
            raise IntentError(
                f"Operator '{f.op}' on '{f.column}' needs a non-empty list of values, "
                f"e.g. [\"DE\", \"AT\"]. For a single value use '='."
            )
        for item in f.value:
            _literal(item)
    elif f.op in _COMPARISONS:
        if f.value is None or isinstance(f.value, (list, tuple)):
            raise IntentError(
                f"Operator '{f.op}' on '{f.column}' needs a single value. "
                f"Use 'in' for a list, or 'is_null' / 'is_not_null' to test for missing values."
            )
        _literal(f.value)


def _render_filter(f: Filter) -> str:
    if f.op in _NULL_OPS:
        return f"{f.column} {_NULL_OPS[f.op]}"
    if f.op in _LIST_OPS:
        values = ", ".join(sorted({_literal(v) for v in f.value}))
        return f"{f.column} {_LIST_OPS[f.op]} ({values})"
    return f"{f.column} {f.op} {_literal(f.value)}"


def _literal(value: Any) -> str:
    """Render a Python value as a SQL literal. Values never reach SQL any other way."""
    if isinstance(value, bool):  # before int: bool is a subclass of int
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and not math.isfinite(value):
        raise IntentError(
            f"Unsupported filter value {value!r}: numbers must be finite. Use a real number."
        )
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, dt.datetime):  # before date: datetime is a subclass of date
        raise IntentError(
            f"Unsupported filter value {value!r}: timestamps are not supported. "
            f"Use an ISO date such as '2026-07-01'."
        )
    if isinstance(value, dt.date):
        return f"DATE '{value.isoformat()}'"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    raise IntentError(
        f"Unsupported filter value {value!r}. Use a string, number, boolean or ISO date."
    )