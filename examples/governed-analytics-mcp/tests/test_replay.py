"""The replay command: definition and data checked separately, with honest verdicts."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from support import LAST_QUARTER, call_many, make_config, needs_warehouse, read_jsonl

from governed_analytics.catalogue import METRICS_DIR
from governed_analytics.replay import find_receipt, metric_at_version, replay

pytestmark = [pytest.mark.integration, needs_warehouse]

EXPLORE = {"sql": "SELECT dealer_tier, count(*) AS orders FROM marts.fct_orders GROUP BY 1 ORDER BY 1"}


@pytest.fixture
def stored(tmp_path):
    config = make_config(tmp_path)
    call_many(config, [("query_metric", LAST_QUARTER), ("explore_sql", EXPLORE)])
    return config, read_jsonl(tmp_path / "receipts.jsonl")


def test_fresh_receipts_reproduce(stored):
    config, receipts = stored
    for receipt in receipts:
        report = replay(config, receipt)
        assert (report.definition, report.snapshot, report.result, report.verdict) == (
            "match", "same", "match", "reproduced"
        )


def test_tampered_hash_on_same_data_is_a_mismatch(stored):
    config, [receipt, _] = stored
    receipt["result"]["hash"] = "sha256:" + "0" * 64
    assert replay(config, receipt).verdict == "mismatch"


def test_rebuilt_data_with_same_result_is_unchanged(stored):
    config, [receipt, _] = stored
    receipt["data_snapshot"]["dbt_invocation_id"] = "an-earlier-build"
    report = replay(config, receipt)
    assert (report.snapshot, report.verdict) == ("newer", "unchanged_on_new_data")


def test_rebuilt_data_with_moved_result_is_data_changed(stored):
    config, [receipt, _] = stored
    receipt["data_snapshot"]["dbt_invocation_id"] = "an-earlier-build"
    receipt["result"]["hash"] = "sha256:" + "0" * 64
    assert replay(config, receipt).verdict == "data_changed"


def test_edited_sql_is_a_definition_change(stored):
    config, [receipt, _] = stored
    receipt["compiled_sql"] = receipt["compiled_sql"].replace("is_paid = TRUE", "is_paid = FALSE")
    assert replay(config, receipt).verdict == "definition_changed"


def test_unknown_metric_version_is_skipped_not_passed(stored):
    config, [receipt, _] = stored
    receipt["metric_version"] = "9.9.9"
    report = replay(config, receipt)
    assert report.definition.startswith("skipped:") and "9.9.9" in report.definition


def test_explore_sql_receipt_rechecks_the_allow_list(stored):
    config, [_, receipt] = stored
    receipt["compiled_sql"] = "SELECT buyer_id FROM marts.fct_orders"
    assert replay(config, receipt).definition.startswith("differs: the SQL is no longer allowed")


def test_metric_at_version_reads_git_history(tmp_path, monkeypatch):
    # A throwaway repository where the metric went from 1.0.0 to 2.0.0 with a new filter.
    metrics = tmp_path / "metrics"
    metrics.mkdir()
    path = metrics / "net_merchandise_value.yml"
    original = (METRICS_DIR / "net_merchandise_value.yml").read_text()
    git = lambda *args: subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "root")
    path.write_text(original)
    git("add", ".")
    git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "v1")
    path.write_text(original.replace("version: 1.0.0", "version: 2.0.0").replace(
        "filters:\n", "filters:\n  - {column: dealer_tier, op: '!=', value: trial}\n"))
    git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-am", "v2")
    monkeypatch.setattr("governed_analytics.replay.METRICS_DIR", metrics)

    assert len(metric_at_version("net_merchandise_value", "2.0.0").filters) == 2  # current file
    assert len(metric_at_version("net_merchandise_value", "1.0.0").filters) == 1  # from history
    assert metric_at_version("net_merchandise_value", "0.0.1") is None


def test_command_line(stored, tmp_path):
    config, [receipt, _] = stored
    env = {**os.environ, "KIT_LOG_DIR": str(tmp_path), "PYTHONPATH": "src"}
    cwd = config.warehouse.parents[1]
    ok = subprocess.run([sys.executable, "-m", "governed_analytics.replay", receipt["receipt_id"], "--json"],
                        capture_output=True, text=True, env=env, cwd=cwd)
    assert ok.returncode == 0 and json.loads(ok.stdout)["verdict"] == "reproduced"
    missing = subprocess.run([sys.executable, "-m", "governed_analytics.replay", "rcpt_NOPE"],
                             capture_output=True, text=True, env=env, cwd=cwd)
    assert missing.returncode == 3
    assert find_receipt(config, "rcpt_NOPE") is None
