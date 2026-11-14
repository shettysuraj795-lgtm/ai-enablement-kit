"""GR-03: results are capped in rows and time. Evidence for `pytest -m gr03`."""

from __future__ import annotations

import time

import pytest
from support import LAST_QUARTER, call, make_config, needs_warehouse, read_jsonl

from governed_analytics.service import QueryError, QueryService

pytestmark = [pytest.mark.gr03, pytest.mark.integration, needs_warehouse]

SLOW_SQL = "SELECT sum(a.range * b.range) FROM range(100000) a, range(100000) b"  # 10 billion rows
SLOW_MART_SQL = (  # allowed by GR-02, but about 20 billion joined rows
    "SELECT count(*) FROM marts.fct_orders a CROSS JOIN marts.fct_orders b CROSS JOIN marts.dim_dealers c"
)


def test_row_cap_truncates_flags_and_traces(tmp_path):
    config = make_config(tmp_path, row_cap=3)
    answer = call(config, {**LAST_QUARTER, "dimensions": ["dealer_region"]}).structured_content

    assert answer["truncated"] is True and len(answer["rows"]) == 3
    assert "first 3 rows" in answer["how_to_report"]
    [span] = read_jsonl(tmp_path / "traces.jsonl")
    assert span["status"]["code"] == "OK"
    assert span["attributes"]["kit.result.truncated"] is True
    assert span["attributes"]["kit.guardrail.hits"] == ["GR-03"]
    [receipt] = read_jsonl(tmp_path / "receipts.jsonl")
    assert receipt["result"]["truncated"] is True and receipt["result"]["row_count"] == 3


def test_under_the_cap_is_not_flagged(tmp_path):
    answer = call(make_config(tmp_path), {**LAST_QUARTER, "dimensions": ["dealer_region"]}).structured_content
    assert answer["truncated"] is False and len(answer["rows"]) == 11


def test_timeout_cancels_the_query(tmp_path):
    service = QueryService(make_config(tmp_path, timeout_seconds=0.2), catalogue={})
    started = time.monotonic()
    with pytest.raises(QueryError, match="took longer than 0.2 seconds"):
        service.execute(SLOW_SQL)
    assert time.monotonic() - started < 5  # cancelled, not run to completion


def test_explore_sql_is_capped(tmp_path):
    config = make_config(tmp_path, row_cap=5)
    answer = call(config, {"sql": "SELECT order_id FROM marts.fct_orders"}, tool="explore_sql").structured_content
    assert answer["truncated"] is True and len(answer["rows"]) == 5
    [span] = read_jsonl(tmp_path / "traces.jsonl")
    assert span["attributes"]["kit.guardrail.hits"] == ["GR-03"]


def test_explore_sql_timeout_is_an_error_with_guidance(tmp_path):
    config = make_config(tmp_path, timeout_seconds=0.2)
    result = call(config, {"sql": SLOW_MART_SQL}, tool="explore_sql")
    assert result.is_error and "Narrow the time range" in result.content[0].text
    [span] = read_jsonl(tmp_path / "traces.jsonl")
    assert span["attributes"]["kit.error.reason"] == "timeout"
    assert span["attributes"]["kit.guardrail.hits"] == ["GR-03"]
    assert read_jsonl(tmp_path / "receipts.jsonl") == []
