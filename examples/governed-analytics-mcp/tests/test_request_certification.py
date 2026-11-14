"""request_certification: a minimal queue of exploratory results for BI."""

from __future__ import annotations

import pytest
from support import LAST_QUARTER, call_many, make_config, needs_warehouse, read_jsonl

from governed_analytics.trace_report import report

pytestmark = [pytest.mark.integration, needs_warehouse]

DAYS_TO_SELL = (
    "SELECT o.dealer_region, avg(datediff('day', l.first_listed, o.order_date)) AS days_to_sell "
    "FROM marts.fct_orders o JOIN (SELECT listing_id, min(snapshot_date) AS first_listed "
    "FROM marts.fct_listings GROUP BY 1) l USING (listing_id) GROUP BY 1 ORDER BY 1"
)


def explore(config, sql=DAYS_TO_SELL) -> str:
    [result] = call_many(config, [("explore_sql", {"sql": sql})])
    return result.structured_content["receipt_id"]


def test_logs_a_request_linked_to_the_receipt(tmp_path):
    config = make_config(tmp_path, persona="sales_ops_lead")
    receipt_id = explore(config)
    [result] = call_many(config, [("request_certification", {
        "receipt_id": receipt_id, "question_shape": "average days from listing to sale, by region"})])

    answer = result.structured_content
    assert answer["status"] == "queued for BI review" and answer["request_id"].startswith("creq_")
    [request] = read_jsonl(tmp_path / "certification_requests.jsonl")
    [receipt] = read_jsonl(tmp_path / "receipts.jsonl")
    assert (request["receipt_id"], request["sql_fingerprint"]) == (receipt_id, receipt["sql_fingerprint"])
    assert (request["source"], request["metric"], request["persona"]) == ("explore_sql", None, "sales_ops_lead")
    [_, span] = read_jsonl(tmp_path / "traces.jsonl")
    assert span["attributes"]["kit.certification_request.id"] == request["request_id"]


def test_uncertified_metric_results_can_be_requested(tmp_path):
    config = make_config(tmp_path)
    [result] = call_many(config, [("query_metric", {"metric": "active_listings", "time_grain": "month", "period": "last_month"})])
    call_many(config, [("request_certification", {
        "receipt_id": result.structured_content["receipt_id"], "question_shape": "active listings per month"})])
    [request] = read_jsonl(tmp_path / "certification_requests.jsonl")
    assert request["metric"] == "active_listings"


@pytest.mark.parametrize(
    ("receipt_id", "message"),
    [("rcpt_" + "0" * 26, "No receipt"), ("not-a-receipt", "pattern")],
)
def test_rejects_unknown_or_malformed_receipts(tmp_path, receipt_id, message):
    [result] = call_many(make_config(tmp_path), [("request_certification", {"receipt_id": receipt_id, "question_shape": "x"})])
    assert result.is_error and message in result.content[0].text
    assert read_jsonl(tmp_path / "certification_requests.jsonl") == []


def test_rejects_certified_results(tmp_path):
    config = make_config(tmp_path)
    [result] = call_many(config, [("query_metric", LAST_QUARTER)])
    [rejected] = call_many(config, [("request_certification", {
        "receipt_id": result.structured_content["receipt_id"], "question_shape": "net merchandise value"})])
    assert rejected.is_error and "already a certified result" in rejected.content[0].text


def test_shape_is_capped(tmp_path):
    receipt_id = explore(make_config(tmp_path))
    [result] = call_many(make_config(tmp_path), [("request_certification", {"receipt_id": receipt_id, "question_shape": "x" * 301})])
    assert result.is_error


def test_trace_report_lists_requests_with_usage(tmp_path):
    config = make_config(tmp_path)
    receipt_id = explore(config)
    explore(config, DAYS_TO_SELL.replace("o.dealer_region", "o.dealer_tier"))  # different shape (literals alone would not be)
    explore(config)  # same shape again
    call_many(config, [("request_certification", {"receipt_id": receipt_id, "question_shape": "days to sell by region"})])

    [row] = report(tmp_path)["certification_requests"]
    assert (row["what"], row["requests"], row["uses"]) == ("explore_sql", 1, 2)
    assert row["example_shape"] == "days to sell by region"
