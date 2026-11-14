"""Run compiled SQL against the warehouse and compare with the golden answers.

The golden answers come from hand-written reference SQL (ADR-005), so this
checks the compiler against an independent reading of the definition.
Needs data/warehouse.duckdb: run the generator and `dbt build` first.
"""

from __future__ import annotations

import duckdb
import pytest
import yaml
from generate import DEFAULT_DB
from golden_answers import GOLDEN, answer_nodes, compute

from governed_analytics.compiler import compile_intent
from governed_analytics.intent import Intent

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DEFAULT_DB.exists(), reason="data/warehouse.duckdb not built"),
]

METRIC = "net_merchandise_value"


def _cases():
    for question in yaml.safe_load(GOLDEN.read_text())["questions"]:
        for i, node in enumerate(answer_nodes(question)):
            if node["intent"]["metric"] == METRIC:
                yield pytest.param(node, id=f"{question['id']}-{i}")


@pytest.mark.parametrize("expected", list(_cases()))
def test_matches_golden_answer(nmv, expected):
    sql = compile_intent(Intent.from_dict(expected["intent"]), nmv)
    with duckdb.connect(str(DEFAULT_DB), read_only=True) as con:
        assert compute(con, sql) == expected["result"]
