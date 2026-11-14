"""Trace queries: success metrics and promotion candidates from a known log."""

from __future__ import annotations

import pytest
from support import LAST_QUARTER, call_many, make_config, needs_warehouse

from governed_analytics.trace_report import QUERIES, report, split_queries

pytestmark = [pytest.mark.integration, needs_warehouse]

REPEAT_ORDERS = (
    "SELECT dealer_region, count(*) AS orders FROM marts.fct_orders "
    "WHERE order_date >= DATE '{start}' AND order_date < DATE '{end}' GROUP BY 1"
)


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    log_dir = tmp_path_factory.mktemp("logs")
    finance = make_config(log_dir, persona="finance_analyst")
    sales = make_config(log_dir, persona="sales_ops_lead")
    call_many(finance, [
        ("query_metric", LAST_QUARTER),  # certified
        ("query_metric", {**LAST_QUARTER, "metric": "gross_merchandise_value"}),  # certified
        ("query_metric", {**LAST_QUARTER, "metric": "revenue"}),  # schema error
        ("explore_sql", {"sql": REPEAT_ORDERS.format(start="2026-07-01", end="2026-08-01"),
                         "question": "Orders by region in July?"}),
        ("explore_sql", {"sql": "SELECT * FROM raw.orders"}),  # GR-02 block
    ])
    call_many(sales, [
        ("query_metric", {"metric": "active_listings", "time_grain": "month", "period": "last_month"}),  # uncertified
        ("explore_sql", {"sql": REPEAT_ORDERS.format(start="2026-08-01", end="2026-09-01")}),
        ("explore_sql", {"sql": REPEAT_ORDERS.format(start="2026-09-01", end="2026-10-01")}),
        ("explore_sql", {"sql": "SELECT count(*) AS listings FROM marts.fct_listings"}),  # asked once
        ("list_metrics", {"term": "revenue"}),
    ])
    return report(log_dir)


def test_every_named_query_runs():
    _, queries = split_queries(QUERIES.read_text())
    assert list(queries) == [
        "overview", "by_tool", "certified_share_by_persona", "errors_by_reason",
        "guardrail_hits", "promotion_candidates", "uncertified_metric_usage", "certification_requests",
    ]


def test_overview(results):
    [overview] = results["overview"]
    assert overview["calls"] == 10
    assert overview["data_answers"] == 7  # 3 metric answers + 4 explore_sql answers
    assert overview["certified_share"] == pytest.approx(2 / 7, abs=0.001)
    assert overview["error_rate"] == 0.2
    assert overview["p95_ms"] >= overview["p50_ms"] >= 0


def test_certified_share_by_persona(results):
    shares = {r["persona"]: (r["data_answers"], r["certified"]) for r in results["certified_share_by_persona"]}
    assert shares == {"finance_analyst": (3, 2), "sales_ops_lead": (4, 0)}


def test_errors_and_guardrails(results):
    assert {(r["error_reason"], r["tool"]): r["calls"] for r in results["errors_by_reason"]} == {
        ("invalid_intent", "query_metric"): 1,
        ("guardrail_blocked", "explore_sql"): 1,
    }
    assert results["guardrail_hits"] == [{"requirement": "GR-02", "calls": 1}]


def test_promotion_candidates_group_by_shape_not_literals(results):
    [candidate] = results["promotion_candidates"]  # the one-off listings count is below min_uses
    assert candidate["uses"] == 3 and candidate["personas"] == 2
    assert candidate["who"] == "finance_analyst, sales_ops_lead"
    assert candidate["example_question"] == "Orders by region in July?"
    assert "fct_orders" in candidate["example_sql"]


def test_uncertified_metric_usage(results):
    [row] = results["uncertified_metric_usage"]
    assert (row["metric"], row["uses"], row["personas"]) == ("active_listings", 1, 1)


def test_empty_logs_give_empty_results(tmp_path):
    empty = report(tmp_path)
    assert empty["overview"][0]["calls"] == 0 and empty["promotion_candidates"] == []
