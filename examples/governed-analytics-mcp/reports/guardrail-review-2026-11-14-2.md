# Guardrail review (second): governed-analytics-mcp

- **Commit:** `0251a6c5240e1617dfa589a7b8a44f0f75e672b8`  **Date:** 14 Nov 2026  **Reviewer:** kit maintainer (AI-assisted), following [`guardrail-review`](../../../skills/community/guardrail-review/SKILL.md) v0.1.0
- **Verdict:** **Pass** (8 of 8 in-scope requirements met)
- **Previous review:** [first review, commit `7b9ae0a`](guardrail-review-2026-11-14.md): **Fail**, GR-04 *Not met* because nothing ran the retention purge. Fixed in `0251a6c` ([changelog](../../../requirements/CHANGELOG.md)).
- **CI for this commit:** [run 43640713589](https://github.com/shettysuraj795-lgtm/ai-enablement-kit/actions/runs/43640713589): data build, catalogue validation, 201 tests and golden evals all passed.

## Scope

All eight requirements are in scope, for the same reasons as in the first review. Every step of the skill was run again on this commit; no result was carried over from the first review. Paths are relative to `examples/governed-analytics-mcp/`.

## Results

| ID | Status | Control | Verification | Notes |
|---|---|---|---|---|
| GR-01 | Met | `src/governed_analytics/service.py:334` read-only connection with `enable_external_access` off | `pytest -m gr01`: exit 0, 10 passed | Unchanged since the first review |
| GR-02 | Met | `src/governed_analytics/allowlist.py:37` sqlglot checks on the parsed tree; `:53` executes the regenerated SQL | `pytest -m gr02`: exit 0, 30 passed | Unchanged |
| GR-03 | Met | `src/governed_analytics/service.py:309` fetches at most `cap + 1` rows; `:304` timer interrupts; `:320` truncation flag | `pytest -m gr03`: exit 0, 5 passed | Unchanged |
| GR-04 | **Met** | `allowlist.py:79` (PII in SQL); `validate.py:26` with `server.py:44` (PII dimensions refuse start-up); `tracing.py:64` (question only in `kit.question`); **`server.py:164`** retention lifespan, registered at `:51`, purging via `retention.py:26`; `retention.py:45` and `receipts.py:94` write lock | `pytest -m gr04`: exit 0, 24 passed | **Changed:** previously *Not met*. The server purges at start-up and every `purge_interval_seconds` while it runs. Three new tests: purge at start with no command run; purge on the interval mid-session; no lines lost under concurrent writes. The last one fails 3 out of 3 times with the lock removed |
| GR-05 | Met | `src/governed_analytics/service.py:274` writes the receipt before returning; `replay.py:66` replays it | `pytest -m gr05`: exit 0, 3 passed | Unchanged |
| GR-06 | Met | `src/governed_analytics/service.py:156` label from the catalogue; `:192` `explore_sql` always exploratory | `pytest -m gr06`: exit 0, 2 passed | Unchanged |
| GR-07 | Met | `src/governed_analytics/tracing.py:47` middleware, registered at `server.py:50` | `pytest -m gr07`: exit 0, 4 passed | The new write lock is on the same `append` the tracer uses, so purges cannot drop spans |
| GR-08 | Met | `src/governed_analytics/validate.py:42` and `:57`; CI at `.github/workflows/governed-analytics.yml:50` | `pytest -m gr08`: exit 0, 11 passed; `python -m governed_analytics.validate --base HEAD~1`: exit 0, 0 problems | Unchanged |

### Hard against soft (skill step 4)

Every control sits in code, configuration or CI. GR-04 retention, the soft control in the first review, now runs inside the server process itself and does not depend on a person or a skill.

### Trace cross-check (skill step 5)

| Check | Result |
|---|---|
| Spans scanned | 596, from 36 trace logs. 500 of them are synthetic old spans written by the concurrent-write test |
| Blocked calls | 26, all with GR-02 (15) or GR-04 (11) |
| Timed-out calls | 1, with GR-03 |
| Truncated results | 2, with GR-03 |
| Hits without a matching block, timeout or truncation | none |

## Not met: what would fix it

Nothing is *Not met*.

## Observations (not statuses)

- **Retention pauses while the server is stopped.** If the server isn't started for more than 30 days, old question text stays on disk until its next start-up. When the server is decommissioned or moved to shared hosting, IT should either delete the local logs or schedule `python -m governed_analytics.retention`. This is recorded as a hand-off item.
- **The write lock covers one process only.** The manual retention command shouldn't run while the server is running (DESIGN.md, *Known limits*).
- Carried over from the first review: free-text filter values and SQL can appear in receipts and tool arguments. They can only target non-PII columns, and the scan found no PII values.
- This report hasn't yet been checked by a requirement owner, which `guardrail-review`'s own promotion needs.

## Sign-off after handover

| Requirement | Owning team |
|---|---|
| GR-01 | IT |
| GR-02 | BI |
| GR-03 | Tool enablement |
| GR-04 | IT (security) |
| GR-05 | BI |
| GR-06 | BI |
| GR-07 | ML / data science |
| GR-08 | BI |

## Rerunning this review

```sh
git checkout 0251a6c5240e1617dfa589a7b8a44f0f75e672b8
cd examples/governed-analytics-mcp
data/.venv/bin/python data/generate.py && (cd dbt && ../data/.venv/bin/dbt build)
for m in gr01 gr02 gr03 gr04 gr05 gr06 gr07 gr08; do data/.venv/bin/pytest -m $m -q --basetemp=/tmp/gr-review/$m; echo "$m exit $?"; done
PYTHONPATH=src data/.venv/bin/python -m governed_analytics.validate --base HEAD~1
```
