"""Rollout success metrics and promotion candidates, from the trace log, receipts and certification requests.

    python -m governed_analytics.trace_report                # all queries, as tables
    python -m governed_analytics.trace_report --min-uses 3   # stricter promotion queue
    python -m governed_analytics.trace_report --json

The SQL lives in analytics/trace_queries.sql so it can also be run in the DuckDB CLI.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import duckdb

from governed_analytics.service import EXAMPLE_DIR, Config

QUERIES = EXAMPLE_DIR / "analytics" / "trace_queries.sql"


def split_queries(text: str) -> tuple[str, dict[str, str]]:
    """The setup statements before the first `-- name:`, and each named query after it."""
    parts = re.split(r"^-- name: (\w+)\s*$", text, flags=re.M)
    return parts[0], dict(zip(parts[1::2], (q.strip().rstrip(";") for q in parts[2::2])))


def report(log_dir: Path, min_uses: int = 2) -> dict[str, list[dict[str, Any]]]:
    setup, queries = split_queries(QUERIES.read_text())
    con = duckdb.connect()  # in memory; the warehouse is never opened here
    with tempfile.NamedTemporaryFile(suffix=".jsonl") as empty:  # keeps the views valid on a fresh install
        for name, file in (("traces", "traces"), ("receipts", "receipts"), ("requests", "certification_requests")):
            path = log_dir / f"{file}.jsonl"
            con.execute(f"SET VARIABLE {name} = ?", [str(path if path.exists() else empty.name)])
        con.execute("SET VARIABLE min_uses = ?", [min_uses])
        con.execute(setup)
        results = {}
        for name, sql in queries.items():
            cursor = con.execute(sql)
            columns = [d[0] for d in cursor.description]
            results[name] = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return results


def _table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(none)"
    columns = list(rows[0])
    cell = lambda v: "" if v is None else str(v).replace("\n", " ")[:80]  # noqa: E731
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(cell(r[c]) for c in columns) + " |" for r in rows]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--min-uses", type=int, default=2, help="uses before an exploratory query is a candidate")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = report(Config.from_env().log_dir, args.min_uses)
    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        for name, rows in results.items():
            print(f"## {name.replace('_', ' ')}\n\n{_table(rows)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
