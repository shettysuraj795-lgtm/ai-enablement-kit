"""GR-07: every tool call is traced. Evidence for `pytest -m gr07`."""

from __future__ import annotations

import pytest
from support import LAST_QUARTER, call_many, make_config, needs_warehouse, read_jsonl

pytestmark = [pytest.mark.gr07, pytest.mark.integration, needs_warehouse]

CALLS = [
    ("list_metrics", {"term": "revenue"}),  # success, no data
    ("describe_metric", {"metric": "take_rate"}),  # success, no data
    ("query_metric", LAST_QUARTER),  # success with receipt
    ("query_metric", {**LAST_QUARTER, "metric": "revenue"}),  # rejected by the schema
    ("query_metric", {**LAST_QUARTER, "filters": [{"column": "dealer_region", "op": "in", "value": "DE"}]}),  # compiler error
    ("drop_tables", {}),  # unknown tool
    ("explore_sql", {"sql": "SELECT count(*) AS orders FROM marts.fct_orders"}),  # success with receipt
    ("explore_sql", {"sql": "SELECT * FROM raw.orders"}),  # blocked by GR-02
]


@pytest.fixture
def traced(tmp_path):
    results = call_many(make_config(tmp_path), CALLS)
    return results, read_jsonl(tmp_path / "traces.jsonl"), read_jsonl(tmp_path / "receipts.jsonl")


def test_one_span_per_call_including_failures(traced):
    results, spans, _ = traced
    assert [s["name"] for s in spans] == [f"tools/call {tool}" for tool, _ in CALLS]
    assert [s["status"]["code"] for s in spans] == ["ERROR" if r.is_error else "OK" for r in results]
    assert [r.is_error for r in results] == [False, False, False, True, True, True, False, True]


def test_spans_follow_the_contract(traced):
    _, spans, _ = traced
    for span in spans:
        assert len(span["trace_id"]) == 32 and len(span["span_id"]) == 16
        assert span["kind"] == "SERVER"
        assert span["attributes"]["gen_ai.operation.name"] == "execute_tool"
        assert span["attributes"]["mcp.method.name"] == "tools/call"
        assert span["start_time"] <= span["end_time"]
    assert len({s["span_id"] for s in spans}) == len(spans)
    assert len({s["trace_id"] for s in spans}) == 1  # one session, one trace


def test_errors_carry_type_and_reason(traced):
    _, spans, _ = traced
    reasons = [s["attributes"].get("kit.error.reason") for s in spans if s["status"]["code"] == "ERROR"]
    assert reasons == ["invalid_intent", "invalid_intent", "invalid_intent", "guardrail_blocked"]
    assert all(s["attributes"]["error.type"] == "tool_error" for s in spans if s["status"]["code"] == "ERROR")
    assert spans[-1]["attributes"]["kit.guardrail.hits"] == ["GR-02"]


def test_receipt_and_span_point_at_each_other(traced):
    _, spans, receipts = traced
    for span, receipt in zip([spans[2], spans[6]], receipts, strict=True):
        assert span["attributes"]["kit.receipt.id"] == receipt["receipt_id"]
        assert (span["trace_id"], span["span_id"]) == (receipt["trace_id"], receipt["span_id"])
