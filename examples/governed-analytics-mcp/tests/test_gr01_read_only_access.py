"""GR-01: data access is read-only. Evidence for `pytest -m gr01`."""

from __future__ import annotations

import hashlib

import duckdb
import pytest
from support import LAST_QUARTER, call_many, make_config, needs_warehouse

from governed_analytics.service import connect_read_only

pytestmark = [pytest.mark.gr01, pytest.mark.integration, needs_warehouse]

WRITES = {
    "insert": "INSERT INTO marts.dim_dealers SELECT * FROM marts.dim_dealers LIMIT 1",
    "update": "UPDATE marts.fct_orders SET is_paid = FALSE",
    "delete": "DELETE FROM marts.fct_orders",
    "create": "CREATE TABLE marts.injected AS SELECT 1 AS x",
    "drop": "DROP TABLE marts.fct_orders",
    "attach": "ATTACH '{tmp}/other.duckdb' AS other",
    "copy_to": "COPY (SELECT * FROM marts.fct_orders) TO '{tmp}/leak.csv'",
    "install": "INSTALL httpfs",
    "reenable_files": "SET enable_external_access = true",
}


def checksum(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name", sorted(WRITES))
def test_connection_refuses_writes(tmp_path, name):
    with connect_read_only(make_config(tmp_path).warehouse) as con:
        with pytest.raises(duckdb.Error):
            con.execute(WRITES[name].format(tmp=tmp_path))
    assert list(tmp_path.iterdir()) == []  # no file was created


def test_injection_through_tools_changes_nothing(tmp_path):
    config = make_config(tmp_path)
    before = checksum(config.warehouse)
    payloads = [WRITES[name].format(tmp=tmp_path) for name in ("drop", "copy_to")]
    calls = [
        ("query_metric", {**LAST_QUARTER, "filters": [{"column": "dealer_region", "op": "=", "value": f"x'; {p}; --"}]})
        for p in payloads
    ]
    calls.append(("describe_metric", {"metric": "net_merchandise_value; DROP TABLE marts.fct_orders"}))
    calls += [("explore_sql", {"sql": WRITES[name].format(tmp=tmp_path)}) for name in sorted(WRITES)]
    results = call_many(config, calls)

    assert all(r.is_error or r.structured_content["rows"] == [] for r in results)
    assert all(r.is_error for r in results[-len(WRITES):])  # every raw write refused
    assert checksum(config.warehouse) == before
    assert not (tmp_path / "leak.csv").exists()
