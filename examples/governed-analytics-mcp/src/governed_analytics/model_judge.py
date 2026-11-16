"""Fixed rules for judging model-in-the-loop transcripts (ADR-008).

No model judges another model here: each rule looks only at which tools were
called, with what arguments, and at the words of the final reply. The same
rules run locally after a live run and in CI over the committed transcripts.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

RUNS_TO_PASS = 2  # of 3

# The checks for each kind of question. GQ-15's single check was split in two
# on 16 Nov 2026, after reading the first transcripts (ADR-008, Revision).
# "asks directly" is the original rule, unchanged.
CHECKS = {
    "ambiguous": ["lists the options or names its choice"],
    "metric": ["names the metric"],
    "uncovered": ["offers certification", "asks directly"],
}

# Anything shaped like an Anthropic API key. Transcripts are scanned before
# they are written; a match means something went badly wrong, so nothing is saved.
KEY_PATTERN = re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")


@dataclasses.dataclass
class Verdict:
    passed: bool
    reasons: list[str]


def needs_model(question: dict) -> bool:
    """The golden questions whose checks need a model in the loop."""
    kind = question["kind"]
    return kind in ("ambiguous", "uncovered") or bool(question["expected"].get("must_name_metric"))


def tool_calls(transcript: dict) -> list[dict[str, Any]]:
    """Each tool call with its input and whether the server returned an error."""
    errors = {
        block["tool_use_id"]: block.get("is_error", False)
        for message in transcript["messages"]
        if message["role"] == "user" and isinstance(message["content"], list)
        for block in message["content"]
        if block["type"] == "tool_result"
    }
    return [
        {"name": block["name"], "input": block["input"], "is_error": errors.get(block["id"], True)}
        for message in transcript["messages"]
        if message["role"] == "assistant"
        for block in message["content"]
        if block["type"] == "tool_use"
    ]


def final_reply(transcript: dict) -> str:
    """The text of the last assistant message: what the user reads."""
    for message in reversed(transcript["messages"]):
        if message["role"] == "assistant":
            return "\n".join(b["text"] for b in message["content"] if b["type"] == "text")
    return ""


def names_metric(text: str, metric: str) -> bool:
    """`net_merchandise_value` or "net merchandise value", in any case."""
    lowered = text.lower()
    return metric in lowered or metric.replace("_", " ") in lowered


def judge(question: dict, transcript: dict, certified: set[str]) -> dict[str, Verdict]:
    """A verdict for each of the question's checks."""
    calls = tool_calls(transcript)
    reply = final_reply(transcript)
    ok = [c for c in calls if not c["is_error"]]
    reasons: list[str] = []

    if transcript.get("stop_reason") not in ("end_turn", "stop_sequence"):
        reasons.append(f"conversation ended with {transcript.get('stop_reason')}")

    kind = question["kind"]
    if kind == "ambiguous":
        term = question["term"].lower()
        options = [o["intent"]["metric"] for o in question["expected"]["options"]]
        if not any(c["name"] == "list_metrics" and str(c["input"].get("term", "")).lower() == term for c in calls):
            reasons.append(f"list_metrics was not called with term '{term}'")
        listed = all(names_metric(reply, m) for m in options)
        queried = {c["input"].get("metric") for c in ok if c["name"] == "query_metric"}
        chose = any(names_metric(reply, m) for m in queried & set(options))
        if not (listed or chose):
            reasons.append("reply neither lists every option nor names the option it queried")
    elif kind == "metric":
        metric = question["expected"]["intent"]["metric"]
        if not any(c["name"] == "query_metric" and c["input"].get("metric") == metric for c in ok):
            reasons.append(f"query_metric was not called for {metric}")
        if not names_metric(reply, metric):
            reasons.append(f"reply does not name {metric}")
    elif kind == "uncovered":
        if not any(c["name"] == "explore_sql" for c in ok):
            reasons.append("explore_sql did not return a result")
        used = sorted({c["input"].get("metric") for c in ok if c["name"] == "query_metric"} & certified)
        if used:
            reasons.append(f"answered with certified metric(s) {', '.join(used)}")
        if "exploratory" not in reply.lower():
            reasons.append("reply does not say exploratory")
        if any(c["name"] == "request_certification" for c in calls):
            reasons.append("requested certification without the user accepting")
        offers = [] if offers_certification(reply) else ["reply does not offer certification"]
        asks = [] if asks_about_certification(reply) else ["reply does not offer certification as a question"]
        return {
            "offers certification": Verdict(not (reasons + offers), reasons + offers),
            "asks directly": Verdict(not (reasons + asks), reasons + asks),
        }
    else:
        raise ValueError(f"no rule for question kind {kind!r}")
    return {CHECKS[kind][0]: Verdict(passed=not reasons, reasons=reasons)}


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.findall(r"[^.!?\n]*[.!?]?", text) if s.strip()]


# "I can ask BI to certify it", "I could submit a certification request".
_CAN_REQUEST = re.compile(r"\bI (?:can|could|will|'ll)\b.*\b(?:request|ask|submit|send)", re.IGNORECASE)


def asks_about_certification(text: str) -> bool:
    """A sentence that mentions certification and ends in a question mark (the original rule)."""
    return any("certif" in s.lower() and s.endswith("?") for s in sentences(text))


def certification_statements(text: str) -> list[str]:
    """Sentences saying the assistant can request or ask for certification."""
    return [s for s in sentences(text) if "certif" in s.lower() and _CAN_REQUEST.search(s)]


def offers_certification(text: str) -> bool:
    """Asked as a question, or stated: "I can ask BI to certify it"."""
    return asks_about_certification(text) or bool(certification_statements(text))


def find_key(text: str) -> bool:
    return bool(KEY_PATTERN.search(text))
