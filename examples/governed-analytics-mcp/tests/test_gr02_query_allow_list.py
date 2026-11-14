"""GR-02: exploratory SQL is limited to an allow-list. Evidence for `pytest -m gr02`."""

from __future__ import annotations

import pytest
from support import CONFIG, call_many, make_config, needs_warehouse, read_jsonl

from governed_analytics.allowlist import SqlRejected, check
from governed_analytics.manifest import load_manifest

pytestmark = [pytest.mark.gr02, pytest.mark.integration, needs_warehouse]

ALLOWED = {
    "aggregate": "SELECT dealer_region, count(*) AS orders FROM marts.fct_orders GROUP BY dealer_region",
    "cte": "WITH paid AS (SELECT dealer_id, gross_amount_eur FROM marts.fct_orders WHERE is_paid) SELECT count(*) FROM paid",
    "join": "SELECT o.dealer_region, count(*) FROM marts.fct_orders o JOIN marts.fct_listings l USING (listing_id) GROUP BY 1",
    "subquery": "SELECT max(n) FROM (SELECT dealer_id, count(*) AS n FROM marts.fct_orders GROUP BY dealer_id)",
    "union": "SELECT dealer_region FROM marts.fct_orders UNION SELECT dealer_region FROM marts.fct_listings",
    "star_without_pii": "SELECT * FROM marts.dim_dealers",
}

BLOCKED = {
    "insert": "INSERT INTO marts.dim_dealers SELECT * FROM marts.dim_dealers",
    "copy": "COPY marts.fct_orders TO 'leak.csv'",
    "create_as": "CREATE TABLE marts.x AS SELECT 1",
    "select_into": "SELECT dealer_id INTO marts.x FROM marts.fct_orders",
    "stacked": "SELECT 1; DROP TABLE marts.fct_orders",
    "stacked_in_comment_trick": "SELECT 1 /* harmless */; ATTACH 'x.db' AS x",
    "raw_table": "SELECT * FROM raw.orders",
    "staging_table": "SELECT * FROM staging.stg_orders",
    "unqualified": "SELECT count(*) FROM fct_orders",
    "information_schema": "SELECT * FROM information_schema.columns",
    "raw_in_cte": "WITH t AS (SELECT order_id FROM raw.orders) SELECT count(*) FROM t",
    "raw_in_subquery": "SELECT count(*) FROM (SELECT order_id FROM raw.refunds)",
    "read_csv": "SELECT * FROM read_csv('/etc/hosts')",
    "read_parquet": "SELECT * FROM read_parquet('data/*.parquet')",
    "file_path_as_table": "SELECT * FROM 'data/warehouse.duckdb'",
    "query_function": "SELECT * FROM query('SELECT * FROM raw.orders')",
    "getenv": "SELECT getenv('HOME')",
    "duckdb_metadata": "SELECT * FROM duckdb_tables()",
    "pragma": "PRAGMA show_tables",
    "set": "SET threads = 1",
    "not_sql": "please show me revenue",
}


@pytest.fixture(scope="module")
def manifest():
    return load_manifest(CONFIG.dbt_target)


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_allowed(manifest, name):
    assert check(ALLOWED[name], manifest).sql


@pytest.mark.parametrize("name", sorted(BLOCKED))
def test_blocked(manifest, name):
    with pytest.raises(SqlRejected):
        check(BLOCKED[name], manifest)


def test_executes_the_checked_sql_not_the_text(manifest):
    checked = check("select  dealer_region , count(*) from MARTS.FCT_ORDERS group by 1 -- trailing", manifest)
    assert checked.sql == "SELECT dealer_region, COUNT(*) FROM MARTS.FCT_ORDERS GROUP BY 1 /* trailing */"


def test_blocked_query_is_traced_with_gr02_and_no_receipt(tmp_path):
    [result] = call_many(make_config(tmp_path), [("explore_sql", {"sql": BLOCKED["raw_table"]})])
    assert result.is_error and "Only the marts can be queried" in result.content[0].text
    [span] = read_jsonl(tmp_path / "traces.jsonl")
    assert span["attributes"]["kit.guardrail.hits"] == ["GR-02"]
    assert span["attributes"]["kit.error.reason"] == "guardrail_blocked"
    assert read_jsonl(tmp_path / "receipts.jsonl") == []


def test_allowed_query_runs_through_the_tool(tmp_path):
    [result] = call_many(make_config(tmp_path), [("explore_sql", {"sql": ALLOWED["aggregate"]})])
    answer = result.structured_content
    assert answer["columns"] == ["dealer_region", "orders"] and len(answer["rows"]) == 11
