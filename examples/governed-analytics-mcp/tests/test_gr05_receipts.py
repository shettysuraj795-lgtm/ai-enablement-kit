"""GR-05: every result has a replayable receipt. Evidence for `pytest -m gr05`."""

from __future__ import annotations

import pytest
from support import CONFIG, LAST_QUARTER, call_many, make_config, needs_warehouse, read_jsonl

from governed_analytics.catalogue import load_catalogue
from governed_analytics.compiler import COMPILER_VERSION, compile_intent
from governed_analytics.intent import Intent
from governed_analytics.receipts import render, result_hash
from governed_analytics.service import connect_read_only

pytestmark = [pytest.mark.gr05, pytest.mark.integration, needs_warehouse]

DATA_CALLS = [
    ("query_metric", LAST_QUARTER),
    ("query_metric", {**LAST_QUARTER, "dimensions": ["dealer_tier"], "filters": [{"column": "dealer_region", "op": "in", "value": ["DE", "AT"]}]}),
    ("query_metric", {"metric": "take_rate", "time_grain": "month", "period": "last_quarter"}),
    ("query_metric", {"metric": "active_listings", "time_grain": "week", "period": "last_4_weeks"}),
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


def test_receipts_replay_definition_and_data(run):
    _, receipts = run
    catalogue = load_catalogue()
    with connect_read_only(CONFIG.warehouse) as con:
        for receipt in receipts:
            # Definition: same intent, metric version and compiler give the same SQL.
            metric = catalogue[receipt["intent"]["metric"]]
            assert (metric.version, COMPILER_VERSION) == (receipt["metric_version"], receipt["compiler_version"])
            assert compile_intent(Intent.from_dict(receipt["intent"]), metric) == receipt["compiled_sql"]
            # Data: rerunning the SQL on the same snapshot reproduces the hash.
            cursor = con.execute(receipt["compiled_sql"])
            columns = [d[0] for d in cursor.description]
            rows = [[render(v, c) for v, c in zip(row, columns)] for row in cursor.fetchall()]
            assert result_hash(columns, rows) == receipt["result"]["hash"]


def test_failed_calls_write_no_receipt(tmp_path):
    call_many(make_config(tmp_path), [("query_metric", {**LAST_QUARTER, "period": None})])
    assert read_jsonl(tmp_path / "receipts.jsonl") == []
