"""query_metric end to end: MCP client -> server -> warehouse -> receipt and trace.

Uses the in-process MCP client, the real catalogue and the real warehouse.
Needs data/warehouse.duckdb and dbt/target/run_results.json from `dbt build`.
"""

from __future__ import annotations

import asyncio
import json

import pytest
import yaml
from golden_answers import GOLDEN
from mcp import Client
from support import LAST_QUARTER, call, make_config, needs_warehouse, read_jsonl

from governed_analytics.receipts import render, result_hash
from governed_analytics.server import build_server
from governed_analytics.service import Config, connect_read_only

pytestmark = [pytest.mark.integration, needs_warehouse]

RECEIPT_EXAMPLE_SQL = (
    "SELECT date_trunc('quarter', order_date) AS period, sum(net_amount_eur) AS net_merchandise_value "
    "FROM marts.fct_orders WHERE is_paid = TRUE "
    "AND order_date >= DATE '2026-07-01' AND order_date < DATE '2026-10-01' "
    "GROUP BY period ORDER BY period"
)


@pytest.fixture
def config(tmp_path) -> Config:
    return make_config(tmp_path)


def golden(question_id: str) -> dict:
    questions = yaml.safe_load(GOLDEN.read_text())["questions"]
    return next(q for q in questions if q["id"] == question_id)["expected"]


def test_lists_intent_tools_with_catalogue_enums(config):
    async def go():
        async with Client(build_server(config)) as client:
            return await client.list_tools()

    tools = {t.name: t for t in asyncio.run(go()).tools}
    assert sorted(tools) == ["describe_metric", "list_metrics", "query_metric"]
    schema = json.dumps(tools["query_metric"].input_schema)
    assert "net_merchandise_value" in schema and "last_quarter" in schema and "dealer_region" in schema


def test_revenue_surfaces_its_three_options(config):
    answer = call(config, {"term": "Revenue"}, tool="list_metrics").structured_content
    assert [o["name"] for o in answer["options"]] == [
        "gross_merchandise_value",
        "net_merchandise_value",
        "commission_revenue",
    ]
    assert all(o["meaning"] and o["certified"] for o in answer["options"])
    assert "ask which one they mean" in answer["next_step"]


def test_list_metrics_without_term_lists_catalogue_and_glossary(config):
    answer = call(config, {}, tool="list_metrics").structured_content
    assert len(answer["metrics"]) == 7
    assert answer["glossary"]["sales"] == ["gross_merchandise_value", "paid_orders"]


def test_unknown_term_falls_back_to_catalogue(config):
    answer = call(config, {"term": "turnover"}, tool="list_metrics").structured_content
    assert len(answer["metrics"]) == 7 and "No glossary entry for 'turnover'" in answer["next_step"]


def test_describe_metric(config):
    answer = call(config, {"metric": "take_rate"}, tool="describe_metric").structured_content
    assert answer["time_grains"] == ["month", "quarter", "year"]
    assert answer["always_applied"] == ["is_paid = True"]
    assert answer["glossary_terms"] == ["commission"]
    [span] = read_jsonl(config.log_dir / "traces.jsonl")  # traced, but no receipt: it returns no data
    assert span["name"] == "tools/call describe_metric"
    assert read_jsonl(config.log_dir / "receipts.jsonl") == []


def test_happy_path_returns_golden_answer_with_provenance(config):
    result = call(config, {**LAST_QUARTER, "question": "What was our revenue after refunds last quarter?"})
    assert not result.is_error
    answer = result.structured_content
    expected = golden("GQ-02")

    assert answer["columns"] == expected["result"]["columns"]
    assert answer["rows"] == expected["result"]["rows"]
    assert answer["classification"] == "certified"
    assert answer["metric"]["name"] == "net_merchandise_value" and answer["metric"]["version"] == "1.0.0"
    assert answer["time_range"] == expected["intent"]["time_range"]
    assert answer["receipt_id"] in answer["how_to_report"]


def test_receipt_is_written_and_replays(config):
    answer = call(config, LAST_QUARTER).structured_content
    [receipt] = read_jsonl(config.log_dir / "receipts.jsonl")

    assert receipt["receipt_id"] == answer["receipt_id"]
    assert receipt["compiled_sql"] == RECEIPT_EXAMPLE_SQL  # the contract's worked example
    assert receipt["intent"] == golden("GQ-02")["intent"]
    assert receipt["metric_version"] == "1.0.0" and receipt["compiler_version"] == "0.1.0"
    assert receipt["data_snapshot"]["dbt_invocation_id"]
    assert "question" not in json.dumps(receipt)  # GR-04: questions never reach receipts

    # Replay (GR-05): rerunning the stored SQL reproduces the stored hash.
    with connect_read_only(config.warehouse) as con:
        cursor = con.execute(receipt["compiled_sql"])
        columns = [d[0] for d in cursor.description]
        rows = [[render(v, c) for v, c in zip(row, columns)] for row in cursor.fetchall()]
    assert result_hash(columns, rows) == receipt["result"]["hash"]


def test_trace_span_follows_contract(config):
    question = "What was our revenue after refunds last quarter?"
    answer = call(config, {**LAST_QUARTER, "question": question}).structured_content
    [span] = read_jsonl(config.log_dir / "traces.jsonl")
    [receipt] = read_jsonl(config.log_dir / "receipts.jsonl")
    attributes = span["attributes"]

    assert span["name"] == "tools/call query_metric" and span["kind"] == "SERVER"
    assert span["status"]["code"] == "OK"
    assert (span["trace_id"], span["span_id"]) == (receipt["trace_id"], receipt["span_id"])
    assert attributes["gen_ai.operation.name"] == "execute_tool"
    assert attributes["kit.receipt.id"] == answer["receipt_id"]
    assert attributes["db.query.text"] == RECEIPT_EXAMPLE_SQL
    assert attributes["kit.result.classification"] == "certified"
    assert attributes["kit.persona"] == "finance_analyst"
    assert attributes["kit.question"] == question
    assert "question" not in attributes["gen_ai.tool.call.arguments"]
    assert attributes["kit.guardrail.hits"] == []


def test_compiler_rejection_is_guidance_with_no_receipt(config):
    # Passes the schema, fails the compiler: `in` needs a list.
    filters = [{"column": "dealer_region", "op": "in", "value": "DE"}]
    result = call(config, {**LAST_QUARTER, "filters": filters})
    assert result.is_error
    message = result.content[0].text
    assert "needs a non-empty list" in message and "use '='" in message

    assert read_jsonl(config.log_dir / "receipts.jsonl") == []
    [span] = read_jsonl(config.log_dir / "traces.jsonl")
    assert span["status"]["code"] == "ERROR"
    assert span["attributes"]["error.type"] == "tool_error"
    assert span["attributes"]["kit.error.reason"] == "invalid_intent"


def test_schema_rejection_is_still_traced(config):
    # "revenue" is not in the metric enum, so the SDK rejects it before the tool runs (GR-07).
    result = call(config, {**LAST_QUARTER, "metric": "revenue"})
    assert result.is_error
    [span] = read_jsonl(config.log_dir / "traces.jsonl")
    assert span["status"]["code"] == "ERROR"
    assert span["attributes"]["kit.error.reason"] == "invalid_intent"
    assert span["attributes"]["gen_ai.tool.call.arguments"]["metric"] == "revenue"


def test_missing_time_range_names_the_options(config):
    result = call(config, {"metric": "net_merchandise_value", "time_grain": "quarter"})
    assert result.is_error and "last_quarter" in result.content[0].text
