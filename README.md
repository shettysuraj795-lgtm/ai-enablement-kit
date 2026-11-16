# AI Enablement Kit

A reusable kit for helping non-technical teams adopt AI assistants without losing trust in the results: agent skills, hard guardrails, contribution tiers, contracts and decision records. It is demonstrated on one worked example, **self-serve analytics drift**.

> **Demo video:** `[PLACEHOLDER: demo video link]`

## The problem

**Same data, same question, €8.53M to €10.30M depending on the definition.** Ask for "revenue last quarter" over the example's synthetic marketplace and reasonable readings of the same orders land anywhere in that range: gross or net, refunds by order date or refund date, failed orders in or out, order-date or payment-date FX ([ADR-004](docs/adr/004-synthetic-data-and-traps.md)). Once an assistant can query the warehouse, every team picks its own reading. Figures stop being reproducible, charts go back to BI to be double-checked, and unverified numbers reach decisions. This is a governance problem, not a prompting problem: a lower temperature doesn't make two definitions agree.

## The approach

- **The model chooses, code computes.** The assistant picks a governed metric and fills in a structured request. A deterministic compiler turns that into SQL, so the same request always gives the same number, with a receipt BI can replay.
- **Hard guardrails versus soft ones.** Skills shape behaviour, and the model follows them probabilistically. Anything that must always hold is one of eight requirements in [`requirements/`](requirements/), enforced in code, config or CI and tested by ID (`pytest -m gr04`). A skill is never the only control.
- **Certified versus exploratory, for metrics and for skills.** Certified metrics are owned by BI and change-controlled. Anything else is answered by guarded SQL, labelled *exploratory*, and can be sent to BI for certification. Skills follow the same pattern: every skill starts in `community/` and reaches `certified/` only through a promotion PR with an owner, an eval and a version ([CONTRIBUTING](CONTRIBUTING.md)).

> `[PLACEHOLDER: architecture diagram]`

## Built / Deliberately not built / Who it hands off to

**Built**
- An MCP server with five tools, a seven-metric catalogue over dbt marts, the compiler, receipts with replay, and a trace log with OpenTelemetry field names.
- Seeded synthetic data with deliberate traps, modelled in dbt.
- Six skills: one certified (`mcp-tool-design`) and five in community.
- Golden-question evals, guardrail reviews, and a hand-off pack.

**Deliberately not built**
- **Scheduled live model evals.** Model-in-the-loop checks are reported as `needs-model`, never counted as passes. Running them on a schedule is an ML / data science hand-off.
- **A production semantic layer.** A YAML catalogue shows the principle ([ADR-001](docs/adr/001-metric-catalogue.md)).
- **Hosted tracing.** JSON lines queried in DuckDB, ready for an OTLP exporter ([ADR-003](docs/adr/003-trace-log.md)).
- **Warehouse roles and SSO, a review UI, and user research.** The personas are synthetic and labelled as assumptions.

**Who it hands off to**

| Team | Takes on |
|---|---|
| BI | Metric definitions, certification queue, replaying disputed numbers |
| ML / data science | Live model evals, monitoring, LLM-as-judge |
| Tool enablement | Packaging the server as a connector, distributing certified skills |
| IT | Read-only warehouse role, PII masking, SSO, log retention |

## Evidence

- **CI on every push:** data build, dbt tests, catalogue change control, 207 tests and golden evals ([workflow](.github/workflows/governed-analytics.yml)).
- **Golden questions with independent answers:** the expected answers come from hand-written SQL, never from the compiler, so the evals test it rather than repeat it ([contract](docs/contracts/golden-questions.md)).
- **Two guardrail reviews:** the [first](examples/governed-analytics-mcp/reports/guardrail-review-2026-11-14.md) failed 7 of 8, because nothing ran question-text retention. The [second](examples/governed-analytics-mcp/reports/guardrail-review-2026-11-14-2.md) passed 8 of 8 after the server enforced it. The failing report is kept.
- **The `COPY TO` gap:** the first read-only tests showed a read-only DuckDB connection could still write files with `COPY ... TO`. External access is now off, and the tests fail without the fix ([changelog](requirements/CHANGELOG.md)).
- **The promotion PR:** [#2](https://github.com/shettysuraj795-lgtm/ai-enablement-kit/pull/2) moved `mcp-tool-design` to certified, linking the build and both reports.
- **On a small model:** the reporting behaviour (asking about "revenue", labels, the reference for BI) was demonstrated on Claude Haiku. `[PLACEHOLDER: link to the Haiku run]`

## Where to look first

1. **Discovery brief:** `[PLACEHOLDER: discovery brief link]`
2. **Architecture:** `[PLACEHOLDER: architecture.md link]`
3. [**DESIGN.md**](examples/governed-analytics-mcp/DESIGN.md): the tools, guardrails and known limits.
4. [**Hand-off pack**](examples/governed-analytics-mcp/handoff/): a runbook for Finance, an access spec for IT, and responsibilities.

## How to run it

Python 3.12, from the example's folder:

```sh
cd examples/governed-analytics-mcp
python3.12 -m venv data/.venv && data/.venv/bin/pip install -r requirements-dev.txt
data/.venv/bin/python data/generate.py
(cd dbt && ../data/.venv/bin/dbt build)
data/.venv/bin/pytest -q
PYTHONPATH=src data/.venv/bin/python -m governed_analytics.evals
```

To connect Claude Desktop, run `python -m governed_analytics.server` over stdio with `PYTHONPATH=src`. The settings are listed in [DESIGN.md](examples/governed-analytics-mcp/DESIGN.md#configuration).

---

Built with Claude Code; decisions in [`docs/adr/`](docs/adr/).
