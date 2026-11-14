"""GR-04: personal data is never returned or logged. Evidence for `pytest -m gr04`."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json

import pytest
from support import CONFIG, LAST_QUARTER, call_many, make_config, needs_warehouse, read_jsonl

from governed_analytics.catalogue import CatalogueError, load_catalogue
from governed_analytics.manifest import load_manifest
from governed_analytics.retention import purge_questions, purge_request_shapes
from governed_analytics.server import build_server
from governed_analytics.service import connect_read_only
from governed_analytics.validate import against_manifest

pytestmark = [pytest.mark.gr04, pytest.mark.integration, needs_warehouse]

QUESTION = "Revenue after refunds last quarter, for buyer B-00042?"


def _with_pii_dimension():
    catalogue = load_catalogue()
    nmv = catalogue["net_merchandise_value"]
    catalogue["net_merchandise_value"] = dataclasses.replace(
        nmv, allowed_dimensions=(*nmv.allowed_dimensions, "buyer_id")
    )
    return catalogue


def test_pii_columns_come_from_dbt():
    assert load_manifest(CONFIG.dbt_target).pii["fct_orders"] == {"buyer_id"}


def test_pii_dimension_fails_validation():
    problems = against_manifest(_with_pii_dimension(), load_manifest(CONFIG.dbt_target))
    assert problems == ["net_merchandise_value: dimension 'buyer_id' is personal data (GR-04)"]


def test_server_refuses_to_start_with_a_pii_dimension(tmp_path):
    with pytest.raises(CatalogueError, match="buyer_id"):
        build_server(make_config(tmp_path), catalogue=_with_pii_dimension())


def test_pii_column_cannot_be_requested(tmp_path):
    [result] = call_many(make_config(tmp_path), [("query_metric", {**LAST_QUARTER, "dimensions": ["buyer_id"]})])
    assert result.is_error  # not in the dimension enum at all


def test_no_pii_values_in_receipts_or_traces(tmp_path):
    config = make_config(tmp_path)
    call_many(
        config,
        [
            ("query_metric", {**LAST_QUARTER, "question": QUESTION}),
            ("query_metric", {**LAST_QUARTER, "dimensions": ["dealer_region", "order_currency"]}),
            ("query_metric", {"metric": "paid_orders", "time_grain": "month", "period": "last_month"}),
        ],
    )
    with connect_read_only(config.warehouse) as con:
        buyer_ids = {row[0] for row in con.execute("SELECT DISTINCT buyer_id FROM marts.fct_orders").fetchall()}
    receipts = (tmp_path / "receipts.jsonl").read_text()
    traces_without_questions = json.dumps(
        [{**s, "attributes": {k: v for k, v in s["attributes"].items() if k != "kit.question"}}
         for s in read_jsonl(tmp_path / "traces.jsonl")]
    )
    leaked = {b for b in buyer_ids if b in receipts or b in traces_without_questions}
    assert leaked == set()


def test_question_only_in_kit_question(tmp_path):
    call_many(make_config(tmp_path), [("query_metric", {**LAST_QUARTER, "question": QUESTION})])
    [receipt] = read_jsonl(tmp_path / "receipts.jsonl")
    [span] = read_jsonl(tmp_path / "traces.jsonl")
    assert QUESTION not in json.dumps(receipt)
    assert "question" not in span["attributes"]["gen_ai.tool.call.arguments"]
    assert span["attributes"]["kit.question"] == QUESTION


def test_retention_removes_old_questions_only(tmp_path):
    config = make_config(tmp_path)
    call_many(config, [("query_metric", {**LAST_QUARTER, "question": "old"}),
                       ("query_metric", {**LAST_QUARTER, "question": "new"})])
    traces = tmp_path / "traces.jsonl"
    spans = read_jsonl(traces)
    spans[0]["start_time"] = "2026-09-01T09:00:00.000Z"  # 74 days before `now` below
    traces.write_text("".join(json.dumps(s) + "\n" for s in spans))

    purged = purge_questions(traces, now=dt.datetime(2026, 11, 14, tzinfo=dt.UTC), days=30)

    old, new = read_jsonl(traces)
    assert purged == 1
    assert "kit.question" not in old["attributes"] and new["attributes"]["kit.question"] == "new"
    assert old["attributes"]["kit.receipt.id"] == spans[0]["attributes"]["kit.receipt.id"]  # rest kept


PII_QUERIES = {
    "direct": "SELECT buyer_id FROM marts.fct_orders",
    "quoted_upper_case": 'SELECT "BUYER_ID" FROM marts.fct_orders',
    "aggregate": "SELECT count(DISTINCT buyer_id) FROM marts.fct_orders",
    "filter": "SELECT count(*) FROM marts.fct_orders WHERE buyer_id = 'B-00042'",
    "star": "SELECT * FROM marts.fct_orders",
    "qualified_star": "SELECT o.* FROM marts.fct_orders o",
    "star_exclude": "SELECT * EXCLUDE (buyer_id) FROM marts.fct_orders",
    "star_in_cte": "WITH t AS (SELECT * FROM marts.fct_orders) SELECT count(*) FROM t",
    "renamed_in_cte": "WITH t AS (SELECT buyer_id AS b FROM marts.fct_orders) SELECT b FROM t",
    "whole_row": "SELECT o FROM marts.fct_orders o",
    "whole_row_to_json": "SELECT to_json(fct_orders) FROM marts.fct_orders",
    "columns_regex": "SELECT COLUMNS('buy.*') FROM marts.fct_orders",
}


@pytest.mark.parametrize("name", sorted(PII_QUERIES))
def test_explore_sql_never_touches_pii(tmp_path, name):
    [result] = call_many(make_config(tmp_path), [("explore_sql", {"sql": PII_QUERIES[name]})])
    assert result.is_error
    [span] = read_jsonl(tmp_path / "traces.jsonl")
    assert span["attributes"]["kit.guardrail.hits"] in (["GR-04"], ["GR-02"])
    assert read_jsonl(tmp_path / "receipts.jsonl") == []


def test_explore_sql_description_hides_pii_columns(tmp_path):
    from mcp import Client
    import asyncio

    async def go():
        async with Client(build_server(make_config(tmp_path))) as client:
            return {t.name: t for t in (await client.list_tools()).tools}

    description = asyncio.run(go())["explore_sql"].description
    assert "marts.fct_orders" in description and "buyer_id" not in description


def test_retention_removes_old_request_shapes_only(tmp_path):
    config = make_config(tmp_path)
    explored = call_many(config, [("explore_sql", {"sql": "SELECT count(*) AS n FROM marts.fct_listings"})])
    receipt_id = explored[0].structured_content["receipt_id"]
    call_many(config, [("request_certification", {"receipt_id": receipt_id, "question_shape": "old shape"}),
                       ("request_certification", {"receipt_id": receipt_id, "question_shape": "new shape"})])
    path = tmp_path / "certification_requests.jsonl"
    requests = read_jsonl(path)
    requests[0]["created_at"] = "2026-09-01T09:00:00.000Z"
    path.write_text("".join(json.dumps(r) + "\n" for r in requests))

    assert purge_request_shapes(path, now=dt.datetime(2026, 11, 14, tzinfo=dt.UTC), days=30) == 1
    old, new = read_jsonl(path)
    assert "question_shape" not in old and new["question_shape"] == "new shape"
    assert old["sql_fingerprint"] == new["sql_fingerprint"]  # the queue keeps its counts
