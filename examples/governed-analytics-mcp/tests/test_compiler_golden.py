"""Run compiled SQL against the warehouse and compare with the golden answers.

The golden answers come from hand-written reference SQL (ADR-005), so this
checks the compiler against an independent reading of each definition.
Needs data/warehouse.duckdb: run the generator and `dbt build` first.
"""

from __future__ import annotations

import duckdb
import pytest
import yaml
from generate import DEFAULT_DB
from golden_answers import GOLDEN, answer_nodes, compute

from governed_analytics.catalogue import load_catalogue
from governed_analytics.compiler import compile_intent
from governed_analytics.intent import Intent

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DEFAULT_DB.exists(), reason="data/warehouse.duckdb not built"),
]

CATALOGUE = load_catalogue()


def _cases():
    for question in yaml.safe_load(GOLDEN.read_text())["questions"]:
        for i, node in enumerate(answer_nodes(question)):
            yield pytest.param(node, id=f"{question['id']}-{i}-{node['intent']['metric']}")


def results_match(actual: dict, expected: dict, tolerance: float) -> bool:
    if actual["columns"] != expected["columns"] or len(actual["rows"]) != len(expected["rows"]):
        return False
    for got_row, want_row in zip(actual["rows"], expected["rows"]):
        for got, want in zip(got_row, want_row):
            if got == want:
                continue
            try:
                if abs(float(got) - float(want)) > tolerance:
                    return False
            except (TypeError, ValueError):
                return False
    return True


@pytest.mark.parametrize("expected", list(_cases()))
def test_matches_golden_answer(expected):
    metric = CATALOGUE[expected["intent"]["metric"]]
    sql = compile_intent(Intent.from_dict(expected["intent"]), metric)
    with duckdb.connect(str(DEFAULT_DB), read_only=True) as con:
        actual = compute(con, sql)
    assert results_match(actual, expected["result"], expected["tolerance"]), (actual, expected["result"])
    assert expected["classification"] == ("certified" if metric.certified else "exploratory")
