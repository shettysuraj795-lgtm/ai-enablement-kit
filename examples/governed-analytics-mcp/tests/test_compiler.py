"""Unit tests for compile_intent, using net_merchandise_value.

These tests pin the exact SQL format. Exact strings matter: receipts store
the compiled SQL, and replay compares it byte for byte (ADR-002).
"""

from __future__ import annotations

import datetime as dt

import pytest

from governed_analytics.compiler import IntentError, compile_intent
from governed_analytics.intent import Intent

SELECT = "SELECT date_trunc('quarter', order_date) AS period"
MEASURE = "sum(net_amount_eur) AS net_merchandise_value FROM marts.fct_orders"
Q3 = "order_date >= DATE '2026-07-01' AND order_date < DATE '2026-10-01'"


def make_intent(**overrides) -> Intent:
    data = {
        "metric": "net_merchandise_value",
        "dimensions": [],
        "filters": [],
        "time_grain": "quarter",
        "time_range": {
            "start": "2026-07-01",
            "end": "2026-10-01",
            "as_of": "2026-11-14",
            "relative": "last_quarter",
        },
    }
    data.update(overrides)
    return Intent.from_dict(data)


# The happy path


def test_receipt_contract_worked_example(nmv):
    # Verbatim from docs/contracts/receipt.md.
    assert compile_intent(make_intent(), nmv) == (
        "SELECT date_trunc('quarter', order_date) AS period, "
        "sum(net_amount_eur) AS net_merchandise_value "
        "FROM marts.fct_orders "
        "WHERE is_paid = TRUE "
        "AND order_date >= DATE '2026-07-01' AND order_date < DATE '2026-10-01' "
        "GROUP BY period ORDER BY period"
    )


@pytest.mark.parametrize("grain", ["day", "week", "month", "quarter", "year"])
def test_time_grain_sets_date_trunc(nmv, grain):
    sql = compile_intent(make_intent(time_grain=grain), nmv)
    assert sql.startswith(f"SELECT date_trunc('{grain}', order_date) AS period, ")


def test_dimension_is_selected_grouped_and_ordered(nmv):
    sql = compile_intent(make_intent(dimensions=["dealer_region"]), nmv)
    assert sql == (
        f"{SELECT}, dealer_region, {MEASURE} "
        f"WHERE is_paid = TRUE AND {Q3} "
        "GROUP BY period, dealer_region ORDER BY period, dealer_region"
    )


def test_user_filter_follows_fixed_filters(nmv):
    filters = [{"column": "dealer_region", "op": "=", "value": "DE"}]
    sql = compile_intent(make_intent(filters=filters), nmv)
    assert f"WHERE is_paid = TRUE AND dealer_region = 'DE' AND {Q3} " in sql


@pytest.mark.parametrize(
    ("op", "value", "rendered"),
    [
        ("!=", "DE", "dealer_region != 'DE'"),
        ("in", ["DE", "AT"], "dealer_region IN ('AT', 'DE')"),
        ("not_in", ["DE", "AT"], "dealer_region NOT IN ('AT', 'DE')"),
        ("is_null", None, "dealer_region IS NULL"),
        ("is_not_null", None, "dealer_region IS NOT NULL"),
    ],
)
def test_filter_operators(nmv, op, value, rendered):
    filters = [{"column": "dealer_region", "op": op, "value": value}]
    sql = compile_intent(make_intent(filters=filters), nmv)
    assert f"WHERE is_paid = TRUE AND {rendered} AND {Q3} " in sql


def test_string_values_are_escaped(nmv):
    filters = [{"column": "listing_category", "op": "=", "value": "diver' OR '1'='1"}]
    sql = compile_intent(make_intent(filters=filters), nmv)
    assert "listing_category = 'diver'' OR ''1''=''1'" in sql


# Determinism: one question, one SQL string


def test_same_intent_same_sql(nmv):
    assert compile_intent(make_intent(), nmv) == compile_intent(make_intent(), nmv)


def test_dimension_order_does_not_change_sql(nmv):
    a = compile_intent(make_intent(dimensions=["listing_category", "dealer_region"]), nmv)
    b = compile_intent(make_intent(dimensions=["dealer_region", "listing_category"]), nmv)
    assert a == b
    assert "AS period, dealer_region, listing_category, sum(" in a


def test_filter_order_does_not_change_sql(nmv):
    f1 = {"column": "dealer_region", "op": "=", "value": "DE"}
    f2 = {"column": "dealer_tier", "op": "=", "value": "premium"}
    a = compile_intent(make_intent(filters=[f1, f2]), nmv)
    b = compile_intent(make_intent(filters=[f2, f1]), nmv)
    assert a == b
    assert "AND dealer_region = 'DE' AND dealer_tier = 'premium' AND" in a


def test_as_of_and_relative_do_not_change_sql(nmv):
    other = make_intent(
        time_range={"start": "2026-07-01", "end": "2026-10-01", "as_of": "2026-12-01"}
    )
    assert compile_intent(other, nmv) == compile_intent(make_intent(), nmv)


# Invalid intents: errors name the way forward


def _error(nmv, **overrides) -> str:
    with pytest.raises(IntentError) as excinfo:
        compile_intent(make_intent(**overrides), nmv)
    return str(excinfo.value)


def test_wrong_metric(nmv):
    message = _error(nmv, metric="gross_merchandise_value")
    assert "gross_merchandise_value" in message and "net_merchandise_value" in message


def test_grain_not_allowed(nmv):
    message = _error(nmv, time_grain="hour")
    assert "hour" in message and "day, week, month, quarter, year" in message


def test_dimension_not_allowed(nmv):
    message = _error(nmv, dimensions=["dealer_name"])
    assert "dealer_name" in message
    assert "dealer_region, dealer_tier, listing_category, order_currency" in message


def test_filter_column_not_allowed(nmv):
    # buyer_id is personal data (GR-04): never a dimension, so never a filter.
    message = _error(nmv, filters=[{"column": "buyer_id", "op": "=", "value": "b1"}])
    assert "buyer_id" in message and "dealer_region" in message


def test_unknown_operator(nmv):
    message = _error(nmv, filters=[{"column": "dealer_region", "op": "like", "value": "D%"}])
    assert "like" in message and "not_in" in message


@pytest.mark.parametrize("value", [[], "DE", None])
def test_in_needs_a_non_empty_list(nmv, value):
    _error(nmv, filters=[{"column": "dealer_region", "op": "in", "value": value}])


def test_timestamp_value_is_rejected(nmv):
    value = dt.datetime(2026, 7, 1, 12, 0)
    message = _error(nmv, filters=[{"column": "dealer_region", "op": "=", "value": value}])
    assert "ISO date" in message


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_number_is_rejected(nmv, value):
    message = _error(nmv, filters=[{"column": "dealer_region", "op": "=", "value": value}])
    assert "finite" in message


def test_empty_time_range(nmv):
    message = _error(
        nmv, time_range={"start": "2026-10-01", "end": "2026-10-01", "as_of": "2026-11-14"}
    )
    assert "2026-10-01" in message
