"""Run compiled SQL against the warehouse and compare with the golden answers.

The golden answers come from hand-written reference SQL (ADR-005), so this
checks the compiler against an independent reading of each definition.
Needs data/warehouse.duckdb: run the generator and `dbt build` first.
"""

from __future__ import annotations

import pytest
import yaml
from generate import DEFAULT_DB
from golden_answers import GOLDEN, answer_nodes, compute

from governed_analytics.catalogue import load_catalogue
from governed_analytics.compiler import compile_intent
from governed_analytics.evals import results_match
from governed_analytics.intent import Intent
from governed_analytics.service import connect_read_only

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DEFAULT_DB.exists(), reason="data/warehouse.duckdb not built"),
]

CATALOGUE = load_catalogue()


def _cases():
    for question in yaml.safe_load(GOLDEN.read_text())["questions"]:
        for i, node in enumerate(answer_nodes(question)):
            yield pytest.param(node, id=f"{question['id']}-{i}-{node['intent']['metric']}")


@pytest.mark.parametrize("expected", list(_cases()))
def test_matches_golden_answer(expected):
    metric = CATALOGUE[expected["intent"]["metric"]]
    sql = compile_intent(Intent.from_dict(expected["intent"]), metric)
    with connect_read_only(DEFAULT_DB) as con:
        actual = compute(con, sql)
    assert results_match(actual, expected["result"], expected["tolerance"]), (actual, expected["result"])
    assert expected["classification"] == ("certified" if metric.certified else "exploratory")
