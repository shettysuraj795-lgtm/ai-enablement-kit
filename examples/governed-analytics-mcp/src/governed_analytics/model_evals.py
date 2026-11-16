"""Model-in-the-loop evals: a local command, never run in CI (ADR-008).

`run` gives a model the five MCP tools and asks each golden question that has a
needs-model check, with and without the governed-analytics skill, three times
each. It prints an estimated cost first and writes transcripts plus a results
table under evals/model/<model>/. `check` re-judges the committed transcripts
with the same fixed rules (model_judge.py) and calls no model, so CI can run it.

    python -m governed_analytics.model_evals run [--model M] [--runs 3] [--yes]
    python -m governed_analytics.model_evals check

The API key comes from the environment through the SDK. This module never
reads it except to make sure it is not in a transcript before writing one.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from governed_analytics.catalogue import load_catalogue
from governed_analytics.model_judge import CHECKS, RUNS_TO_PASS, find_key, judge, needs_model
from governed_analytics.service import EXAMPLE_DIR, Config

GOLDEN = EXAMPLE_DIR / "evals" / "golden_questions.yml"
OUT_DIR = EXAMPLE_DIR / "evals" / "model"
SKILL = EXAMPLE_DIR.parent.parent / "skills" / "community" / "governed-analytics" / "SKILL.md"
CONDITIONS = ("without_skill", "with_skill")
DEFAULT_MODEL = "claude-haiku-5-5"  # the current Haiku, from the API docs' models overview, 16 Nov 2026

# USD per million tokens, input and output, from the API docs' pricing (16 Nov 2026).
# Haiku's rate applies to prompts up to 100K tokens; these are far smaller.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
MAX_TOKENS = 16000
MAX_TURNS = 8
# Assumptions behind the estimate: a conversation is about four requests, each
# resending the prompt plus about 1,500 tokens of history, and writing about 1,000.
EST_TURNS, EST_HISTORY, EST_OUTPUT = 4, 1500, 1000


class Stop(Exception):
    """End the run with a message and exit code; nothing partial is kept."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def is_billing_error(error: Exception) -> bool:
    """402 billing_error, or the older 400 'credit balance is too low'."""
    return (
        getattr(error, "status_code", None) == 402
        or getattr(error, "type", None) == "billing_error"
        or type(error).__name__ in ("EnforcedSpendLimitReachedError", "OrganizationOnHoldError")
        or "credit balance" in str(getattr(error, "message", "")).lower()
    )


# --- prompts and fingerprints -------------------------------------------------


def skill_text() -> tuple[str, str]:
    """The skill body without frontmatter, and its version."""
    _, frontmatter, body = SKILL.read_text().split("---", 2)
    return body.strip(), yaml.safe_load(frontmatter)["metadata"]["version"]


def system_prompt(condition: str, instructions: str) -> str:
    if condition == "without_skill":
        return instructions
    body, _ = skill_text()
    return f"{instructions}\n\nFollow this skill when answering data questions:\n\n{body}"


def fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


async def tool_definitions(config: Config) -> tuple[list[dict], str]:
    """The server's tools as Claude API tool definitions, and its instructions."""
    from mcp import Client

    from governed_analytics.server import INSTRUCTIONS, build_server

    async with Client(build_server(config)) as client:
        tools = (await client.list_tools()).tools
    return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools], INSTRUCTIONS


def current_fingerprints(config: Config) -> dict[str, str]:
    tools, instructions = asyncio.run(tool_definitions(config))
    return {"tools": fingerprint({"instructions": instructions, "tools": tools}), "skill": fingerprint(SKILL.read_text())}


# --- one conversation ---------------------------------------------------------


def _record(block: Any) -> dict:
    """A response block as stored in the transcript. Thinking is kept as a marker only."""
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return {"type": block.type}


async def converse(api, model: str, effort: str, system: str, tools: list[dict], question: str, config: Config) -> dict:
    """Ask one question; run tool calls against a fresh server until the model stops."""
    from mcp import Client

    from governed_analytics.server import build_server

    messages: list[dict] = [{"role": "user", "content": question}]
    record: list[dict] = [{"role": "user", "content": question}]
    usage = defaultdict(int)
    stop_reason = "max_turns"
    async with Client(build_server(config)) as mcp:
        for _ in range(MAX_TURNS):
            response = await api.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=system,
                tools=tools,
                messages=messages,
                output_config={"effort": effort},
            )
            for field in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
                usage[field] += getattr(response.usage, field, 0) or 0
            messages.append({"role": "assistant", "content": response.content})  # unchanged, thinking included
            record.append({"role": "assistant", "content": [_record(b) for b in response.content]})
            if response.stop_reason == "pause_turn":
                continue
            if response.stop_reason != "tool_use":
                stop_reason = response.stop_reason
                break
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = await mcp.call_tool(block.name, block.input)
                text = "\n".join(c.text for c in result.content if hasattr(c, "text"))
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": text, "is_error": bool(result.is_error)})
            messages.append({"role": "user", "content": results})
            record.append({"role": "user", "content": results})
    return {"messages": record, "stop_reason": stop_reason, "usage": dict(usage)}


def cost(usage: dict, prices: tuple[float, float]) -> float:
    """Upper bound: cache reads and writes are charged at the full input rate."""
    tokens_in = usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
    return (tokens_in * prices[0] + usage.get("output_tokens", 0) * prices[1]) / 1_000_000


# --- run ----------------------------------------------------------------------


def _git_commit() -> str:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=EXAMPLE_DIR, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=EXAMPLE_DIR, capture_output=True, text=True).stdout.strip()
        return head + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def write_transcript(path: Path, transcript: dict) -> None:
    text = json.dumps(transcript, indent=2, ensure_ascii=False) + "\n"
    key = os.environ.get("ANTHROPIC_API_KEY")
    if find_key(text) or (key and key in text):
        raise Stop(f"Refusing to write {path.name}: it contains something shaped like an API key.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


async def run(model: str, effort: str, runs: int, max_usd: float, prices: tuple[float, float], assume_yes: bool) -> Path:
    import anthropic

    golden = yaml.safe_load(GOLDEN.read_text())
    questions = [q for q in golden["questions"] if needs_model(q)]
    base = Config.from_env()
    tools, instructions = await tool_definitions(base)
    _, skill_version = skill_text()
    prints = {"tools": fingerprint({"instructions": instructions, "tools": tools}), "skill": fingerprint(SKILL.read_text())}
    api = anthropic.AsyncAnthropic()

    async def call(make):
        try:
            return await make()
        except anthropic.APIStatusError as e:
            if is_billing_error(e):
                raise Stop(f"Stopped: the API refused the call for billing reasons ({e.status_code}). Nothing was written.", 2) from None
            raise Stop(f"Stopped: the API call failed with {e.status_code} {type(e).__name__}. Nothing was written.") from None
        except anthropic.APIError as e:
            raise Stop(f"Stopped: {type(e).__name__}. Nothing was written.") from None

    # Estimate first. count_tokens is the first call, so a billing problem stops here.
    est_in = 0
    for q in questions:
        for condition in CONDITIONS:
            counted = await call(lambda: api.messages.count_tokens(
                model=model, system=system_prompt(condition, instructions), tools=tools,
                messages=[{"role": "user", "content": q["question"]}],
            ))
            est_in += runs * EST_TURNS * (counted.input_tokens + EST_HISTORY)
    est_out = runs * EST_TURNS * EST_OUTPUT * len(questions) * len(CONDITIONS)
    estimate = (est_in * prices[0] + est_out * prices[1]) / 1_000_000
    conversations = runs * len(questions) * len(CONDITIONS)
    print(f"Model {model}, effort {effort}: {len(questions)} questions x {len(CONDITIONS)} conditions x {runs} runs = {conversations} conversations.")
    print(f"Estimated ~{est_in:,} input and ~{est_out:,} output tokens: about ${estimate:.2f} (stops if spend passes ${max_usd:.2f}).")
    if estimate > max_usd:
        raise Stop(f"The estimate is above --max-usd ${max_usd:.2f}; raise it to run.")
    if not assume_yes and input("Run now? [y/N] ").strip().lower() != "y":
        raise Stop("Not run.", 0)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=OUT_DIR))
    spent = 0.0
    try:
        for q in questions:
            for condition in CONDITIONS:
                for n in range(1, runs + 1):
                    with tempfile.TemporaryDirectory() as logs:
                        config = dataclasses.replace(
                            base, log_dir=Path(logs), persona=q["persona"], as_of=dt.date.fromisoformat(golden["as_of"])
                        )
                        result = await call(lambda: converse(
                            api, model, effort, system_prompt(condition, instructions), tools, q["question"], config
                        ))
                    spent += cost(result["usage"], prices)
                    transcript = {
                        "schema_version": 1,
                        "question_id": q["id"],
                        "condition": condition,
                        "run": n,
                        "model": model,
                        "effort": effort,
                        "question": q["question"],
                        "persona": q["persona"],
                        "as_of": golden["as_of"],
                        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                        "commit": _git_commit(),
                        "skill_version": skill_version,
                        "fingerprints": prints,
                        **result,
                        "cost_usd": round(cost(result["usage"], prices), 6),
                    }
                    write_transcript(staging / "transcripts" / condition / f"{q['id']}-run{n}.json", transcript)
                    print(f"  {q['id']} {condition:13} run {n}: {result['stop_reason']}, ${spent:.4f} so far")
                    if spent > max_usd:
                        raise Stop(f"Stopped: spend ${spent:.2f} passed --max-usd ${max_usd:.2f}. Nothing was written.")
        (staging / "results.md").write_text(render_results(staging, golden, certified_metrics()))
        target = OUT_DIR / model
        if target.exists():
            shutil.rmtree(target)
        os.replace(staging, target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"Spent about ${spent:.4f}. Results: {target / 'results.md'}")
    return target


# --- results and check --------------------------------------------------------


def certified_metrics() -> set[str]:
    return {name for name, m in load_catalogue().items() if m.certified}


def load_transcripts(model_dir: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((model_dir / "transcripts").glob("*/*.json"))]


def render_results(model_dir: Path, golden: dict, certified: set[str]) -> str:
    """The results table, derived only from the transcripts, so CI can regenerate it."""
    transcripts = load_transcripts(model_dir)
    if not transcripts:
        raise Stop(f"No transcripts in {model_dir}.")
    questions = {q["id"]: q for q in golden["questions"]}
    verdicts: dict[tuple[str, str], list[tuple[int, Any]]] = defaultdict(list)
    for t in transcripts:
        verdicts[(t["question_id"], t["condition"])].append((t["run"], judge(questions[t["question_id"]], t, certified)))

    first = transcripts[0]
    commits = sorted({t["commit"] for t in transcripts})
    runs = max(t["run"] for t in transcripts)
    lines = [
        f"# Model-in-the-loop evals: {first['model']}",
        "",
        f"Run on {min(t['created_at'] for t in transcripts)[:10]} at commit `{', '.join(c[:7] + ('-dirty' if c.endswith('-dirty') else '') for c in commits)}`, "
        f"effort `{first['effort']}`, governed-analytics skill v{first['skill_version']}. "
        f"{runs} runs per question per condition; a check passes at {RUNS_TO_PASS} of {runs}. "
        f"Judged by fixed rules ([`model_judge.py`](../../../src/governed_analytics/model_judge.py)), no model. "
        f"Cost about ${sum(t['cost_usd'] for t in transcripts):.2f}.",
        "",
        "| Question | Check | Without skill | With skill |",
        "|---|---|---|---|",
    ]
    totals = dict.fromkeys(CONDITIONS, 0)
    ids = sorted({t["question_id"] for t in transcripts})
    for qid in ids:
        cells = []
        for condition in CONDITIONS:
            passed = sum(v.passed for _, v in verdicts[(qid, condition)])
            ok = passed >= RUNS_TO_PASS
            totals[condition] += ok
            cells.append(f"{passed}/{len(verdicts[(qid, condition)])} {'pass' if ok else 'fail'}")
        q = questions[qid]
        lines.append(f"| {qid} \"{q['question']}\" | {CHECKS[q['kind']]} | {cells[0]} | {cells[1]} |")
    lines.append(f"| **Checks passed** | | **{totals['without_skill']} of {len(ids)}** | **{totals['with_skill']} of {len(ids)}** |")

    failures = [
        f"- {qid}, {condition.replace('_', ' ')}, run {n}: {'; '.join(v.reasons)}"
        for qid in ids
        for condition in CONDITIONS
        for n, v in sorted(verdicts[(qid, condition)])
        if not v.passed
    ]
    lines += ["", "## Why runs failed", ""] + (failures or ["No run failed."])
    lines += [
        "",
        "Transcripts are in [`transcripts/`](transcripts/). They go stale when the tools or the skill change: "
        "`python -m governed_analytics.model_evals check` warns when their fingerprints differ from the current ones.",
        "",
    ]
    return "\n".join(lines)


def check(out_dir: Path = OUT_DIR, config: Config | None = None) -> int:
    """Re-judge committed transcripts; fail if results.md differs or a key-shaped string is present."""
    golden = yaml.safe_load(GOLDEN.read_text())
    model_dirs = sorted(p for p in out_dir.glob("*/") if (p / "transcripts").is_dir()) if out_dir.exists() else []
    if not model_dirs:
        print("No committed model-in-the-loop transcripts to check.")
        return 0
    certified = certified_metrics()
    try:
        current = current_fingerprints(config or Config.from_env())
    except FileNotFoundError as e:  # no warehouse or dbt artefacts: skip only the staleness check
        current = None
        print(f"Skipping the staleness check: {e}")
    problems = 0
    for model_dir in model_dirs:
        for path in sorted((model_dir / "transcripts").glob("*/*.json")):
            if find_key(path.read_text()):
                print(f"FAIL {path.relative_to(out_dir)}: contains something shaped like an API key")
                problems += 1
        expected = render_results(model_dir, golden, certified)
        committed = (model_dir / "results.md").read_text() if (model_dir / "results.md").exists() else ""
        if committed != expected:
            print(f"FAIL {model_dir.name}/results.md does not match the transcripts judged by today's rules:\n{expected}")
            problems += 1
        else:
            print(f"ok   {model_dir.name}/results.md matches its {len(load_transcripts(model_dir))} transcripts")
        if current:
            recorded = {json.dumps(t["fingerprints"], sort_keys=True) for t in load_transcripts(model_dir)}
            if recorded != {json.dumps(current, sort_keys=True)}:
                changed = [k for k in current if any(json.loads(r)[k] != current[k] for r in recorded)]
                print(f"warn {model_dir.name}: transcripts are stale ({' and '.join(changed)} changed since they were "
                      "recorded). Re-run `model_evals run` to refresh them.")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="call the model (local only; costs money)")
    r.add_argument("--model", default=os.environ.get("KIT_EVAL_MODEL", DEFAULT_MODEL))
    r.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    r.add_argument("--runs", type=int, default=3)
    r.add_argument("--max-usd", type=float, default=1.00)
    r.add_argument("--price-in", type=float, help="USD per million input tokens, for a model not in PRICES")
    r.add_argument("--price-out", type=float, help="USD per million output tokens, for a model not in PRICES")
    r.add_argument("--yes", action="store_true", help="skip the confirmation after the estimate")
    sub.add_parser("check", help="re-judge committed transcripts (no model; used in CI)")
    args = parser.parse_args()

    if args.command == "check":
        return check()
    prices = PRICES.get(args.model)
    if args.price_in is not None and args.price_out is not None:
        prices = (args.price_in, args.price_out)
    if prices is None:
        print(f"No price for {args.model}: pass --price-in and --price-out from the pricing page.")
        return 1
    try:
        asyncio.run(run(args.model, args.effort, args.runs, args.max_usd, prices, args.yes))
    except Stop as stop:
        print(stop)
        return stop.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
