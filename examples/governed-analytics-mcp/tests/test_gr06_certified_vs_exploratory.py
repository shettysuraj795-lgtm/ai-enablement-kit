"""GR-06: every result is labelled certified or exploratory. Evidence for `pytest -m gr06`."""

from __future__ import annotations

import pytest
from support import LAST_QUARTER, call_many, make_config, needs_warehouse, read_jsonl

pytestmark = [pytest.mark.gr06, pytest.mark.integration, needs_warehouse]

CALLS = [
    ("query_metric", LAST_QUARTER),  # certified: true
    ("query_metric", {"metric": "active_listings", "time_grain": "month", "period": "last_month"}),  # certified: false
]


def test_label_follows_the_catalogue_and_agrees_everywhere(tmp_path):
    results = call_many(make_config(tmp_path), CALLS)
    receipts = read_jsonl(tmp_path / "receipts.jsonl")
    spans = read_jsonl(tmp_path / "traces.jsonl")

    labels = [r.structured_content["classification"] for r in results]
    assert labels == ["certified", "exploratory"]
    assert [r["classification"] for r in receipts] == labels
    assert [s["attributes"]["kit.result.classification"] for s in spans] == labels


def test_the_model_cannot_set_the_label(tmp_path):
    [result] = call_many(make_config(tmp_path), [("query_metric", {**CALLS[1][1], "classification": "certified"})])
    # Unknown arguments are ignored, never passed through: the label still comes from the catalogue.
    assert result.is_error or result.structured_content["classification"] == "exploratory"
