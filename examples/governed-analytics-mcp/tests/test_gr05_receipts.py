"""GR-05: every result has a replayable receipt. Evidence for `pytest -m gr05`."""

from __future__ import annotations

import pytest
from support import LAST_QUARTER, call_many, make_config, needs_warehouse, read_jsonl

from governed_analytics.replay import replay

pytestmark = [pytest.mark.gr05, pytest.mark.integration, needs_warehouse]

DATA_CALLS = [
    ("query_metric", LAST_QUARTER),
    ("query_metric", {**LAST_QUARTER, "dimensions": ["dealer_tier"], "filters": [{"column": "dealer_region", "op": "in", "value": ["DE", "AT"]}]}),
    ("query_metric", {"metric": "take_rate", "time_grain": "month", "period": "last_quarter"}),
    ("query_metric", {"metric": "active_listings", "time_grain": "week", "period": "last_4_weeks"}),
    ("explore_sql", {"sql": "SELECT dealer_tier, count(*) AS orders FROM marts.fct_orders GROUP BY 1 ORDER BY 1"}),
]
CONTRACT_FIELDS = {
    "schema_version", "receipt_id", "created_at", "classification", "source", "intent", "metric_version",
    "compiler_version", "compiled_sql", "sql_fingerprint", "data_snapshot", "result", "trace_id", "span_id",
}


@pytest.fixture
def run(tmp_path):
    results = call_many(make_config(tmp_path), DATA_CALLS)
    return results, read_jsonl(tmp_path / "receipts.jsonl")


def test_every_data_response_has_a_stored_receipt(run):
    results, receipts = run
    assert all(not r.is_error for r in results)
    assert [r.structured_content["receipt_id"] for r in results] == [r["receipt_id"] for r in receipts]
    assert all(set(r) == CONTRACT_FIELDS for r in receipts)


def test_every_receipt_replays(run, tmp_path):
    # The replay command BI would run: definition and data both reproduce.
    _, receipts = run
    for receipt in receipts:
        report = replay(make_config(tmp_path), receipt)
        assert (report.definition, report.result, report.verdict) == ("match", "match", "reproduced"), report


def test_failed_calls_write_no_receipt(tmp_path):
    call_many(make_config(tmp_path), [("query_metric", {**LAST_QUARTER, "period": None})])
    assert read_jsonl(tmp_path / "receipts.jsonl") == []
