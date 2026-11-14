"""Golden-question evals through the MCP server (docs/contracts/golden-questions.md).

Checks the tool layer, with no model involved: every expected intent is sent
to the server as tool arguments, and the result, label and receipt are
compared with the golden answer. Behaviour that needs a model in the loop
(asking about an ambiguous term, offering certification) is reported as
`needs-model`, never as a pass.

    python -m governed_analytics.evals            # exit 1 if any check fails
    python -m governed_analytics.evals --json out.json
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from mcp import Client

from governed_analytics.service import EXAMPLE_DIR, Config

GOLDEN = EXAMPLE_DIR / "evals" / "golden_questions.yml"


@dataclasses.dataclass
class Outcome:
    question_id: str
    kind: str
    status: str  # pass | fail | needs-model
    detail: str = ""


def results_match(actual: dict, expected: dict, tolerance: float) -> bool:
    """Same columns and rows; numbers may differ by up to `tolerance` (absolute)."""
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


def tool_arguments(intent: dict) -> dict[str, Any]:
    time_range = intent["time_range"]
    arguments: dict[str, Any] = {
        "metric": intent["metric"],
        "time_grain": intent["time_grain"],
        "dimensions": intent["dimensions"],
        "filters": intent["filters"],
    }
    if "relative" in time_range:
        arguments["period"] = time_range["relative"]
    else:
        arguments["start"], arguments["end"] = time_range["start"], time_range["end"]
    return arguments


async def _check_answer(client: Client, expected: dict, log_dir: Path) -> str | None:
    """None if the server's answer matches `expected`, else what differed."""
    result = await client.call_tool("query_metric", tool_arguments(expected["intent"]))
    if result.is_error:
        return f"tool error: {result.content[0].text}"
    answer = result.structured_content
    if answer["classification"] != expected["classification"]:
        return f"label {answer['classification']}, expected {expected['classification']}"
    if not results_match(answer, expected["result"], expected["tolerance"]):
        return f"result {answer['rows'][:3]}..., expected {expected['result']['rows'][:3]}..."
    receipts = [json.loads(line) for line in (log_dir / "receipts.jsonl").read_text().splitlines()]
    receipt = next(r for r in receipts if r["receipt_id"] == answer["receipt_id"])
    if receipt["intent"] != expected["intent"]:
        return f"receipt intent {receipt['intent']}, expected {expected['intent']}"
    return None


async def run(golden_path: Path = GOLDEN, config: Config | None = None) -> list[Outcome]:
    from governed_analytics.server import build_server  # after config is known

    golden = yaml.safe_load(golden_path.read_text())
    with tempfile.TemporaryDirectory() as tmp:
        config = dataclasses.replace(
            config or Config.from_env(),
            log_dir=Path(tmp),
            persona="eval",
            as_of=dt.date.fromisoformat(golden["as_of"]),
        )
        outcomes = []
        async with Client(build_server(config)) as client:
            for q in golden["questions"]:
                outcomes.extend(await _check_question(client, q, config.log_dir))
    return outcomes


async def _check_question(client: Client, q: dict, log_dir: Path) -> list[Outcome]:
    qid, kind, expected = q["id"], q["kind"], q["expected"]
    if kind == "metric":
        problem = await _check_answer(client, expected, log_dir)
        outcomes = [Outcome(qid, kind, "fail" if problem else "pass", problem or "answer, label and intent")]
        if expected.get("must_name_metric"):
            outcomes.append(Outcome(qid, kind, "needs-model", "answer must name the metric"))
        return outcomes
    if kind == "ambiguous":
        listed = (await client.call_tool("list_metrics", {"term": q["term"]})).structured_content
        offered = [o["name"] for o in listed.get("options", [])]
        wanted = [o["intent"]["metric"] for o in expected["options"]]
        outcomes = [
            Outcome(qid, kind, "pass" if sorted(offered) == sorted(wanted) else "fail",
                    f"list_metrics('{q['term']}') offers {offered}")
        ]
        for option in expected["options"]:
            problem = await _check_answer(client, option, log_dir)
            outcomes.append(Outcome(qid, kind, "fail" if problem else "pass",
                                    problem or f"option {option['intent']['metric']}"))
        outcomes.append(Outcome(qid, kind, "needs-model", "assistant lists options or names its choice"))
        return outcomes
    return [Outcome(qid, kind, "needs-model", "exploratory answer and certification offer")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, help="also write outcomes to this file")
    args = parser.parse_args()

    outcomes = asyncio.run(run())
    for o in outcomes:
        print(f"{o.question_id:6} {o.kind:10} {o.status:12} {o.detail}")
    counts = {s: sum(o.status == s for o in outcomes) for s in ("pass", "fail", "needs-model")}
    print(f"\n{counts['pass']} passed, {counts['fail']} failed, {counts['needs-model']} need a model in the loop")
    if args.json:
        args.json.write_text(json.dumps([dataclasses.asdict(o) for o in outcomes], indent=2))
    return 1 if counts["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
