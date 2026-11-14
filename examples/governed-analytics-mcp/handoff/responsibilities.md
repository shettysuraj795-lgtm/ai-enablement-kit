# Responsibilities: governed-analytics MCP server

*For:* Finance, BI, ML / data science, Tool enablement and IT. *Build:* reviewed at commit `0251a6c` ([guardrail review: Pass](../reports/guardrail-review-2026-11-14-2.md)). *Assumption:* team names are roles until each team confirms an owner.

**R** responsible (does the work) · **A** accountable (one per row, decides) · **C** consulted · **I** informed. *Kit* is the kit maintainer, who stays involved only until hand-off is confirmed.

| Activity | Finance | BI | ML / DS | Tool enablement | IT | Kit |
|---|---|---|---|---|---|---|
| Metric definitions and catalogue changes (version bumps, GR-08) | C | **A** R | I | I | | C |
| Certifying metrics: promotion candidates and certification requests; what counts as certified (GR-06) | C | **A** R | I | | | |
| Answering disputed numbers by replaying receipts (GR-05) | C | **A** R | | | | |
| Golden questions: what a correct answer is | C | **A** R | C | | | |
| Eval suite in CI, model-in-the-loop evals, LLM-as-judge | | C | **A** R | I | | C |
| Monitoring: trace export, success metrics, alerting (GR-07) | I | I | **A** R | C | | |
| Packaging the server as an organisation-wide connector; versioned releases | I | | C | **A** R | C | C |
| Installing the connector and skills for Finance users | C | | | **A** R | | |
| Distributing certified skills; keeping community skills labelled | | | | **A** R | | C |
| Read-only warehouse role and object scope (GR-01, GR-02) | | C | | C | **A** R | |
| PII masking at the warehouse; flagging PII columns in dbt (GR-04) | | R | | | **A** R | |
| Identity and SSO | | | | C | **A** R | |
| Log storage, access and question-text retention (GR-04) | | I | C | C | **A** R | |
| Query limits: row cap and timeout (GR-03) | | | C | **A** R | C | |
| Keeping the SQL allow-list's function blocklist current when the database engine is upgraded (GR-02) | | **A** | | R | C | C |
| Stamping the data snapshot into the warehouse during dbt builds, instead of reading `run_results.json` | | **A** R | C | | | |
| Re-running `guardrail-review` on every release | | C | C | **A** R | C | C |
| Security incident or suspected guardrail breach | I | C | C | C | **A** R | C |
| Onboarding Finance users with the [runbook](runbook-finance.md) | **A** R | C | | C | | C |
| Decommissioning: deleting logs, revoking the role | I | C | C | R | **A** R | |

## Requirement owners after hand-off

Taken from [`requirements/README.md`](../../../requirements/README.md). Each owner is accountable for any change to their requirement's wording (recorded in the [changelog](../../../requirements/CHANGELOG.md)), and signs off their row of the next guardrail review.

| Requirement | Owner |
|---|---|
| GR-01 Data access is read-only | IT |
| GR-02 Exploratory SQL is limited to an allow-list | BI |
| GR-03 Results are capped in rows and time | Tool enablement |
| GR-04 Personal data is never returned or logged | IT (security) |
| GR-05 Every result has a replayable receipt | BI |
| GR-06 Every result is labelled certified or exploratory | BI |
| GR-07 Every tool call is traced | ML / data science |
| GR-08 Certified metric definitions are change-controlled | BI |

## Open questions

- **BI:** who triages the certification queue, and how often? What is the target turnaround for a request? Questions about unique buyers can only be answered by a governed metric (exploratory SQL can't touch `buyer_id`, even in a count). Is one needed?
- **ML / data science:** which monitoring stack receives the traces? It only needs an OTLP exporter added (ADR-003).
- **Tool enablement:** the release cadence, and which version of the connector Finance pilots on.
- **IT:** the five decisions in the [access spec](access-spec.md).
- **Finance:** a champion for onboarding, and which reports must use certified figures only.
