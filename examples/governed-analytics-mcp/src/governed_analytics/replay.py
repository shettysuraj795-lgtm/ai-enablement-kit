"""Replay a receipt: check its definition and its data separately (ADR-002, GR-05).

    python -m governed_analytics.replay rcpt_01...            # human-readable report
    python -m governed_analytics.replay rcpt_01... --json

Exit codes: 0 reproduced (or unchanged on newer data), 2 the data has changed
since the receipt, 1 a real mismatch (the definition or same-snapshot result
differs), 3 receipt not found.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass

import yaml

from governed_analytics import allowlist, receipts
from governed_analytics.catalogue import METRICS_DIR, Metric, parse_metric
from governed_analytics.compiler import COMPILER_VERSION, compile_intent
from governed_analytics.intent import Intent
from governed_analytics.manifest import load_manifest
from governed_analytics.service import Config, QueryError, QueryService

EXIT = {"reproduced": 0, "unchanged_on_new_data": 0, "data_changed": 2, "mismatch": 1, "definition_changed": 1}


@dataclass
class Replay:
    receipt_id: str
    definition: str  # match | differs | skipped: <why>
    snapshot: str  # same | newer
    result: str  # match | differs
    verdict: str  # a key of EXIT
    detail: str
    stored_hash: str
    replayed_hash: str


def find_receipt(config: Config, receipt_id: str) -> dict | None:
    return receipts.find(config.log_dir / "receipts.jsonl", receipt_id)


def metric_at_version(name: str, version: str) -> Metric | None:
    """The metric as it was at `version`: the current file, or the git history behind it."""
    path = METRICS_DIR / f"{name}.yml"
    if path.exists():
        current = yaml.safe_load(path.read_text())
        if current["version"] == version:
            return parse_metric(current)
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, cwd=METRICS_DIR)
    if root.returncode != 0:
        return None
    relative = path.relative_to(root.stdout.strip())
    log = subprocess.run(["git", "log", "--format=%H", "--", str(path)], capture_output=True, text=True, cwd=METRICS_DIR)
    for commit in log.stdout.split():
        shown = subprocess.run(["git", "show", f"{commit}:{relative}"], capture_output=True, text=True, cwd=METRICS_DIR)
        if shown.returncode == 0 and (old := yaml.safe_load(shown.stdout))["version"] == version:
            return parse_metric(old)
    return None


def replay(config: Config, receipt: dict) -> Replay:
    definition = _check_definition(config, receipt)

    snapshot = receipts.data_snapshot(config.dbt_target)
    same_snapshot = snapshot["dbt_invocation_id"] == receipt["data_snapshot"]["dbt_invocation_id"]
    # Replay under the receipt's own row count, so a truncated result hashes the same rows.
    service = QueryService(config, catalogue={})
    columns, rows, _ = service.execute(receipt["compiled_sql"])
    rows = rows[: receipt["result"]["row_count"]]
    replayed_hash = receipts.result_hash(columns, rows)
    result_matches = replayed_hash == receipt["result"]["hash"]

    if definition == "differs":
        verdict, detail = "definition_changed", "Recompiling the intent no longer gives the stored SQL."
    elif result_matches:
        verdict = "reproduced" if same_snapshot else "unchanged_on_new_data"
        detail = (
            "Same data, same result."
            if same_snapshot
            else f"The data was rebuilt since ({receipt['data_snapshot']['snapshot_at']} -> {snapshot['snapshot_at']}), but the result is unchanged."
        )
    elif same_snapshot:
        verdict, detail = "mismatch", "Same data snapshot but a different result. Investigate."
    else:
        verdict = "data_changed"
        detail = (
            f"The data was rebuilt since ({receipt['data_snapshot']['snapshot_at']} -> {snapshot['snapshot_at']}) "
            "and the result moved. The receipt still records what was seen at the time."
        )
    return Replay(
        receipt_id=receipt["receipt_id"],
        definition=definition,
        snapshot="same" if same_snapshot else "newer",
        result="match" if result_matches else "differs",
        verdict=verdict,
        detail=detail,
        stored_hash=receipt["result"]["hash"],
        replayed_hash=replayed_hash,
    )


def _check_definition(config: Config, receipt: dict) -> str:
    if receipt["source"] == "explore_sql":
        try:
            allowlist.check(receipt["compiled_sql"], load_manifest(config.dbt_target))
        except allowlist.SqlRejected as e:
            return f"differs: the SQL is no longer allowed ({e})"
        return "match"
    if receipt["compiler_version"] != COMPILER_VERSION:
        return f"skipped: compiled by {receipt['compiler_version']}, this is {COMPILER_VERSION}"
    metric = metric_at_version(receipt["intent"]["metric"], receipt["metric_version"])
    if metric is None:
        return f"skipped: {receipt['intent']['metric']} v{receipt['metric_version']} not found in the catalogue or its git history"
    recompiled = compile_intent(Intent.from_dict(receipt["intent"]), metric)
    return "match" if recompiled == receipt["compiled_sql"] else "differs"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("receipt_id")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args()

    config = Config.from_env()
    receipt = find_receipt(config, args.receipt_id)
    if receipt is None:
        print(f"Receipt {args.receipt_id} not found in {config.log_dir / 'receipts.jsonl'}", file=sys.stderr)
        return 3
    try:
        report = replay(config, receipt)
    except QueryError as e:
        print(f"Replay failed: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(f"Receipt     {report.receipt_id} ({receipt['classification']}, {receipt['source']})")
        print(f"Definition  {report.definition}")
        print(f"Data        {report.snapshot} snapshot, result {report.result}")
        print(f"Verdict     {report.verdict}: {report.detail}")
    return EXIT[report.verdict]


if __name__ == "__main__":
    sys.exit(main())
