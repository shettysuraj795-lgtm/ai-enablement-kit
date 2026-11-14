"""query_metric end to end: MCP client -> server -> warehouse -> receipt and trace.

Uses the in-process MCP client, the real catalogue and the real warehouse.
Needs data/warehouse.duckdb and dbt/target/run_results.json from `dbt build`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt
import json

import duckdb
import pytest
import yaml
from golden_answers import GOLDEN
from mcp import Client

from governed_analytics.receipts import render, result_hash
from governed_analytics.server import build_server
from governed_analytics.service import Config

CONFIG = Config.from_env()
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (CONFIG.warehouse.exists() and (CONFIG.dbt_target / "run_results.json").exists()),
        reason="warehouse not built: run the generator and `dbt build`",
    ),
]

RECEIPT_EXAMPLE_SQL = (
    "SELECT date_trunc('quarter', order_date) AS period, sum(net_amount_eur) AS net_merchandise_value "
    "FROM marts.fct_orders WHERE is_paid = TRUE "
    "AND order_date >= DATE '2026-07-01' AND order_date < DATE '2026-10-01' "
    "GROUP BY period ORDER BY period"
)
LAST_QUARTER = {"metric": "net_merchandise_value", "time_grain": "quarter", "period": "last_quarter"}


@pytest.fixture
def config(tmp_path) -> Config:
    return dataclasses.replace(
        CONFIG, log_dir=tmp_path, persona="finance_analyst", as_of=dt.date(2026, 11, 14)
    )


def call(config: Config, arguments: dict, tool: str = "query_metric"):
    async def go():
        async with Client(build_server(config)) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(go())


def read_jsonl(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def golden(question_id: str) -> dict:
    questions = yaml.safe_load(GOLDEN.read_text())["questions"]
    return next(q for q in questions if q["id"] == question_id)["expected"]


def test_lists_one_tool_with_catalogue_enums(config):
    async def go():
        async with Client(build_server(config)) as client:
            return await client.list_tools()

    tools = asyncio.run(go()).tools
    assert [t.name for t in tools] == ["query_metric"]
    schema = json.dumps(tools[0].input_schema)
    assert "net_merchandise_value" in schema and "last_quarter" in schema and "dealer_region" in schema


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
    with duckdb.connect(str(config.warehouse), read_only=True) as con:
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


def test_row_cap_truncates_and_records_gr03(config):
    capped = dataclasses.replace(config, row_cap=3)
    answer = call(capped, {**LAST_QUARTER, "dimensions": ["dealer_region"]}).structured_content
    assert answer["truncated"] is True and len(answer["rows"]) == 3
    assert "first 3 rows" in answer["how_to_report"]
    [span] = read_jsonl(capped.log_dir / "traces.jsonl")
    assert span["status"]["code"] == "OK"
    assert span["attributes"]["kit.guardrail.hits"] == ["GR-03"]
