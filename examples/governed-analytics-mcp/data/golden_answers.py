"""Compute the expected answers for the golden eval questions.

Runs each question's hand-written `reference_sql` against the dbt marts and
writes the result into `evals/golden_questions.yml`. The reference SQL is
written independently of the metric compiler, so the evals test the compiler
rather than repeat it.

Usage:
    python golden_answers.py           # update expected results in place
    python golden_answers.py --check   # fail if any stored result is out of date
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

import duckdb
import yaml

from generate import DEFAULT_DB, SEED

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden_questions.yml"

HEADER = """\
# Golden eval questions for the governed analytics example (draft format 0.1).
#
# Generated results: edit questions, intents and reference_sql by hand, then
# run `python data/golden_answers.py` to recompute every `result` from the
# dbt marts. `--check` fails if a stored result no longer matches the data.
#
# kind:
#   metric     one governed metric answers it. Passes if the tool call's intent
#              and result match `expected` and the label is `classification`.
#              With `must_name_metric`, the answer must also say which metric
#              it used (the question contains an ambiguous `term`).
#   ambiguous  the question uses a glossary `term` that it does not settle.
#              Passes if the answer lists the `options` and asks the user to
#              choose, or names the option it chose and returns that option's
#              result.
#   uncovered  no metric answers it. Passes if the result is labelled
#              `exploratory` and the answer offers to request certification.
#
# intent follows the receipt contract (docs/contracts/receipt.md); the
# `relative` names are drafts until the compiler fixes its vocabulary.
# result.rows are rendered like the receipt's canonical result: decimals at
# their scale, dates in ISO 8601, ratios to 6 places, and `period` as the ISO
# date the period starts on. Rows are ordered by
# period, then dimensions. Compare numbers within `tolerance` (absolute).
"""


def render(value, column: str) -> str | None:
    if value is None:
        return None
    if column == "period" and isinstance(value, dt.datetime):
        # DuckDB's date_trunc returns a timestamp; a period is a date.
        return value.date().isoformat()
    if isinstance(value, float):
        return f"{value:.6f}"
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def answer_nodes(question: dict):
    expected = question.get("expected", {})
    if "reference_sql" in expected:
        yield expected
    for option in expected.get("options", []):
        yield option


def compute(con: duckdb.DuckDBPyConnection, sql: str) -> dict:
    cursor = con.execute(sql)
    columns = [d[0] for d in cursor.description]
    rows = [[render(v, c) for v, c in zip(row, columns)] for row in cursor.fetchall()]
    return {"columns": columns, "rows": rows}


class Dumper(yaml.SafeDumper):
    pass


def _represent_str(dumper, value):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


def _is_scalar(value) -> bool:
    return not isinstance(value, (dict, list))


def _represent_list(dumper, value):
    return dumper.represent_sequence("tag:yaml.org,2002:seq", value, flow_style=all(map(_is_scalar, value)))


def _represent_dict(dumper, value):
    flow = len(value) > 1 and all(map(_is_scalar, value.values()))
    return dumper.represent_mapping("tag:yaml.org,2002:map", value.items(), flow_style=flow)


Dumper.add_representer(str, _represent_str)
Dumper.add_representer(list, _represent_list)
Dumper.add_representer(dict, _represent_dict)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    golden = yaml.safe_load(GOLDEN.read_text())
    if golden["data"]["generator_seed"] != SEED:
        print(f"Golden file expects seed {golden['data']['generator_seed']}, generator uses {SEED}", file=sys.stderr)
        return 1

    con = duckdb.connect(str(args.db), read_only=True)
    stale = []
    for question in golden["questions"]:
        for node in answer_nodes(question):
            result = compute(con, node["reference_sql"])
            if node.get("result") != result:
                stale.append(question["id"])
                node["result"] = result

    if args.check:
        if stale:
            print(f"Out of date: {', '.join(dict.fromkeys(stale))}", file=sys.stderr)
            return 1
        print(f"All {len(golden['questions'])} golden questions match the marts.")
        return 0

    GOLDEN.write_text(HEADER + "\n" + yaml.dump(golden, Dumper=Dumper, sort_keys=False, width=120, allow_unicode=True))
    print(f"Updated {len(dict.fromkeys(stale))} of {len(golden['questions'])} questions in {GOLDEN.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
