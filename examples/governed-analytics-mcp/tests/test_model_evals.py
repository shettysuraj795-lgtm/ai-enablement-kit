"""Model-in-the-loop evals: the fixed judging rules, the results table, the CI check
and the run's safety stops. No test calls a model."""

import asyncio
import json

import pytest
import yaml

from governed_analytics import model_evals
from governed_analytics.model_evals import GOLDEN, Stop, check, cost, is_billing_error, render_results, write_transcript
from governed_analytics.model_judge import judge, needs_model, offers_certification
from support import needs_warehouse

QUESTIONS = {q["id"]: q for q in yaml.safe_load(GOLDEN.read_text())["questions"]}
CERTIFIED = {"gross_merchandise_value", "net_merchandise_value", "commission_revenue", "paid_orders", "refund_rate", "take_rate"}


def transcript(calls: list[tuple[str, dict]], reply: str, stop_reason: str = "end_turn", errors=()) -> dict:
    """A conversation with these tool calls, then `reply` as the final message."""
    messages = [{"role": "user", "content": "question"}]
    for i, (name, arguments) in enumerate(calls):
        messages.append({"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": name, "input": arguments}]})
        messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": "{}", "is_error": i in errors}]})
    messages.append({"role": "assistant", "content": [{"type": "thinking"}, {"type": "text", "text": reply}]})
    return {"messages": messages, "stop_reason": stop_reason}


def verdict(qid: str, t: dict):
    return judge(QUESTIONS[qid], t, CERTIFIED)


def test_selects_the_four_needs_model_questions():
    assert sorted(q for q, v in QUESTIONS.items() if needs_model(v)) == ["GQ-03", "GQ-04", "GQ-10", "GQ-15"]


# --- ambiguous: GQ-03 "revenue" -----------------------------------------------

REVENUE = ("list_metrics", {"term": "revenue"})


def test_ambiguous_passes_when_every_option_is_listed():
    reply = "Revenue could mean gross merchandise value, net_merchandise_value or commission revenue. Which one?"
    assert verdict("GQ-03", transcript([REVENUE], reply)).passed


def test_ambiguous_passes_when_the_queried_choice_is_named():
    calls = [REVENUE, ("query_metric", {"metric": "net_merchandise_value"})]
    assert verdict("GQ-03", transcript(calls, "I used net merchandise value, after refunds: €8.74M.")).passed


def test_ambiguous_fails_without_asking_list_metrics_about_the_term():
    reply = "Gross merchandise value, net merchandise value or commission revenue?"
    v = verdict("GQ-03", transcript([("list_metrics", {})], reply))
    assert not v.passed and v.reasons == ["list_metrics was not called with term 'revenue'"]


def test_ambiguous_fails_when_the_named_metric_was_not_queried():
    calls = [REVENUE, ("query_metric", {"metric": "gross_merchandise_value"})]
    v = verdict("GQ-03", transcript(calls, "Net merchandise value was €8.74M."))
    assert not v.passed and "neither lists" in v.reasons[0]


# --- metric: GQ-04 "revenue after refunds" ------------------------------------


def test_metric_passes_when_queried_and_named():
    calls = [("query_metric", {"metric": "net_merchandise_value"})]
    assert verdict("GQ-04", transcript(calls, "Net merchandise value (v1.0.0, certified): €8,743,316.38.")).passed


def test_metric_fails_when_the_reply_does_not_name_it():
    calls = [("query_metric", {"metric": "net_merchandise_value"})]
    v = verdict("GQ-04", transcript(calls, "Revenue after refunds was €8,743,316.38."))
    assert v.reasons == ["reply does not name net_merchandise_value"]


def test_metric_fails_when_the_query_errored():
    calls = [("query_metric", {"metric": "net_merchandise_value"})]
    v = verdict("GQ-04", transcript(calls, "Net merchandise value is unavailable.", errors={0}))
    assert v.reasons == ["query_metric was not called for net_merchandise_value"]


# --- uncovered: GQ-15 "days to sell" ------------------------------------------

EXPLORE = ("explore_sql", {"sql": "SELECT 1"})
OFFER = "This is an exploratory result: about 23 days. Shall I ask BI to certify a metric for it?"


def test_uncovered_passes_with_exploratory_answer_and_offer():
    assert verdict("GQ-15", transcript([("list_metrics", {}), EXPLORE], OFFER)).passed


def test_uncovered_fails_when_the_offer_is_not_a_question():
    reply = "This is an exploratory result: about 23 days. BI can certify a metric for it."
    assert verdict("GQ-15", transcript([EXPLORE], reply)).reasons == ["reply does not offer certification as a question"]


def test_uncovered_fails_when_it_requests_certification_unasked():
    calls = [EXPLORE, ("request_certification", {"receipt_id": "rcpt_x", "question_shape": "days to sell"})]
    assert verdict("GQ-15", transcript(calls, OFFER)).reasons == ["requested certification without the user accepting"]


def test_uncovered_fails_when_a_certified_metric_answers_it():
    calls = [("query_metric", {"metric": "paid_orders"}), EXPLORE]
    assert verdict("GQ-15", transcript(calls, OFFER)).reasons == ["answered with certified metric(s) paid_orders"]


def test_a_conversation_that_ran_out_of_turns_fails():
    v = verdict("GQ-15", transcript([EXPLORE], OFFER, stop_reason="max_turns"))
    assert v.reasons == ["conversation ended with max_turns"]


@pytest.mark.parametrize(
    ("text", "offered"),
    [
        ("Would you like me to request certification?", True),
        ("Shall I ask BI to certify it? It takes a minute.", True),
        ("I can request certification if you like.", False),
        ("Is this right? BI certifies metrics.", False),
    ],
)
def test_offers_certification(text, offered):
    assert offers_certification(text) is offered


# --- results table and CI check -----------------------------------------------


def write_run(model_dir, replies_by_condition: dict[str, list[str]], fingerprints=None) -> None:
    """Three GQ-15 transcripts per condition, with the given replies."""
    for condition, replies in replies_by_condition.items():
        for n, reply in enumerate(replies, 1):
            t = transcript([EXPLORE], reply) | {
                "question_id": "GQ-15", "condition": condition, "run": n, "model": "test-model", "effort": "medium",
                "created_at": "2026-11-16T10:00:00Z", "commit": "abcdef0123", "skill_version": "0.2.0",
                "fingerprints": fingerprints or {"tools": "sha256:t", "skill": "sha256:s"}, "cost_usd": 0.001,
            }
            write_transcript(model_dir / "transcripts" / condition / f"GQ-15-run{n}.json", t)


def test_results_table_compares_conditions_at_two_of_three(tmp_path):
    plain = "About 23 days."
    write_run(tmp_path, {"without_skill": [plain, OFFER, plain], "with_skill": [OFFER, OFFER, plain]})
    table = render_results(tmp_path, yaml.safe_load(GOLDEN.read_text()), CERTIFIED)
    assert '| GQ-15 "How many days does a listing take to sell, on average?" | says exploratory and offers certification | 1/3 fail | 2/3 pass |' in table
    assert "| **Checks passed** | | **0 of 1** | **1 of 1** |" in table
    assert "- GQ-15, with skill, run 3: reply does not say exploratory; reply does not offer certification as a question" in table


@needs_warehouse
def test_check_accepts_matching_results_and_rejects_edited_ones(tmp_path, capsys):
    model_dir = tmp_path / "test-model"
    write_run(model_dir, {"without_skill": [OFFER] * 3, "with_skill": [OFFER] * 3})
    (model_dir / "results.md").write_text(render_results(model_dir, yaml.safe_load(GOLDEN.read_text()), model_evals.certified_metrics()))
    assert check(tmp_path) == 0
    assert "transcripts are stale (tools and skill changed" in capsys.readouterr().out

    (model_dir / "results.md").write_text((model_dir / "results.md").read_text().replace("3/3 pass", "0/3 fail", 1))
    assert check(tmp_path) == 1


@needs_warehouse
def test_check_rejects_a_key_shaped_string(tmp_path, capsys):
    model_dir = tmp_path / "test-model"
    write_run(model_dir, {"without_skill": [OFFER] * 3, "with_skill": [OFFER] * 3})
    (model_dir / "results.md").write_text(render_results(model_dir, yaml.safe_load(GOLDEN.read_text()), model_evals.certified_metrics()))
    path = model_dir / "transcripts" / "with_skill" / "GQ-15-run1.json"
    data = json.loads(path.read_text())
    data["messages"][0]["content"] = "sk-ant-" + "x" * 20  # written around write_transcript's own guard
    path.write_text(json.dumps(data))
    assert check(tmp_path) == 1
    assert "shaped like an API key" in capsys.readouterr().out


def test_check_with_no_transcripts_passes(tmp_path):
    assert check(tmp_path / "missing") == 0


# --- safety stops --------------------------------------------------------------


def test_write_transcript_refuses_key_shaped_text(tmp_path):
    with pytest.raises(Stop, match="shaped like an API key"):
        write_transcript(tmp_path / "t.json", {"text": "sk-ant-" + "a" * 30})
    assert not (tmp_path / "t.json").exists()


def test_write_transcript_refuses_the_environment_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key-but-secret")
    with pytest.raises(Stop):
        write_transcript(tmp_path / "t.json", {"text": "echo not-a-real-key-but-secret"})
    assert not (tmp_path / "t.json").exists()


def test_cost_charges_cache_tokens_at_the_input_rate():
    usage = {"input_tokens": 600_000, "cache_read_input_tokens": 400_000, "output_tokens": 100_000}
    assert cost(usage, (0.10, 0.50)) == pytest.approx(0.10 + 0.05)


class FakeStatusError(Exception):
    def __init__(self, status_code, type_, message):
        super().__init__(message)
        self.status_code, self.type, self.message = status_code, type_, message


@pytest.mark.parametrize(
    ("error", "billing"),
    [
        (FakeStatusError(402, "billing_error", "Payment required"), True),
        (FakeStatusError(400, "invalid_request_error", "Your credit balance is too low to access the API."), True),
        (FakeStatusError(429, "rate_limit_error", "Too many requests"), False),
        (FakeStatusError(401, "authentication_error", "invalid x-api-key"), False),
    ],
)
def test_is_billing_error(error, billing):
    assert is_billing_error(error) is billing


@needs_warehouse
def test_billing_failure_on_the_first_call_stops_and_writes_nothing(tmp_path, monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    httpx = pytest.importorskip("httpx2")
    response = httpx.Response(402, request=httpx.Request("POST", "https://api.example/v1/messages/count_tokens"))
    error = anthropic.APIStatusError(
        "billing", response=response, body={"type": "error", "error": {"type": "billing_error", "message": "billing"}}
    )
    calls = []

    class FakeMessages:
        async def count_tokens(self, **kwargs):
            calls.append("count_tokens")
            raise error

        async def create(self, **kwargs):
            calls.append("create")

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeClient)
    monkeypatch.setattr(model_evals, "OUT_DIR", tmp_path / "model")
    with pytest.raises(Stop) as stopped:
        asyncio.run(model_evals.run("claude-haiku-5-5", "medium", 3, 1.0, (0.10, 0.50), assume_yes=True))
    assert stopped.value.code == 2 and "billing" in str(stopped.value)
    assert calls == ["count_tokens"]
    assert not (tmp_path / "model").exists()


def test_skill_condition_adds_the_skill_body_only():
    without = model_evals.system_prompt("without_skill", "INSTRUCTIONS")
    with_skill = model_evals.system_prompt("with_skill", "INSTRUCTIONS")
    assert without == "INSTRUCTIONS"
    assert with_skill.startswith("INSTRUCTIONS\n\n") and "Reference for BI" in with_skill and "metadata:" not in with_skill


@needs_warehouse
def test_run_end_to_end_with_a_scripted_model(tmp_path, monkeypatch, capsys):
    """The whole loop against the real server, with a fake client in place of the API."""
    pytest.importorskip("anthropic")
    import anthropic
    from types import SimpleNamespace as NS

    usage = NS(input_tokens=1000, output_tokens=100, cache_creation_input_tokens=0, cache_read_input_tokens=0)
    requests = []

    class FakeMessages:
        async def count_tokens(self, **kwargs):
            return NS(input_tokens=3000)

        async def create(self, **kwargs):
            requests.append(kwargs)
            if kwargs["messages"][-1]["role"] == "user" and isinstance(kwargs["messages"][-1]["content"], str):
                call = NS(type="tool_use", id="tu_1", name="list_metrics", input={"term": "revenue"})
                return NS(content=[NS(type="thinking"), call], stop_reason="tool_use", usage=usage)
            return NS(content=[NS(type="text", text=OFFER)], stop_reason="end_turn", usage=usage)

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeClient)
    monkeypatch.setattr(model_evals, "OUT_DIR", tmp_path)
    target = asyncio.run(model_evals.run("claude-haiku-5-5", "medium", 3, 1.0, (0.10, 0.50), assume_yes=True))

    assert target == tmp_path / "claude-haiku-5-5"
    assert len(list(target.glob("transcripts/*/*.json"))) == 24 and len(requests) == 48
    assert requests[0]["output_config"] == {"effort": "medium"} and requests[0]["model"] == "claude-haiku-5-5"
    t = json.loads((target / "transcripts" / "with_skill" / "GQ-03-run1.json").read_text())
    tool_result = t["messages"][2]["content"][0]
    assert tool_result["type"] == "tool_result" and not tool_result["is_error"] and "3 options" in tool_result["content"]
    assert t["messages"][1]["content"][0] == {"type": "thinking"}
    assert not list(tmp_path.glob(".staging-*"))
    assert check(tmp_path) == 0
    out = capsys.readouterr().out
    assert "about $0.0" in out and "stale" not in out
