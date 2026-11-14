# Guardrail review: governed-analytics-mcp

- **Commit:** `7b9ae0a7f6b034db16a99cdb9c0713ff83b33d50`  **Date:** 14 Nov 2026  **Reviewer:** kit maintainer (AI-assisted), following [`guardrail-review`](../../../skills/community/guardrail-review/SKILL.md) v0.1.0
- **Verdict:** **Fail** (7 of 8 in-scope requirements met)
- **CI for this commit:** [run 43635623025](https://github.com/shettysuraj795-lgtm/ai-enablement-kit/actions/runs/43635623025): data build, catalogue validation, 198 tests and golden evals all passed.

## Scope

All eight requirements in [`requirements/`](../../../requirements/README.md) are in scope. The server serves data (GR-01, GR-03, GR-05, GR-06), accepts raw SQL (GR-02), logs questions (GR-04), traces every call (GR-07) and has a certified catalogue (GR-08). None is marked *Not applicable*.

Verification was run locally on a clean checkout of the commit above, with the warehouse built by `generate.py` and `dbt build`. Paths are relative to `examples/governed-analytics-mcp/`.

## Results

| ID | Status | Control | Verification | Notes |
|---|---|---|---|---|
| GR-01 | Met | `src/governed_analytics/service.py:330` read-only connection with `enable_external_access` off | `pytest -m gr01`: exit 0, 10 passed | Includes `COPY ... TO`, `ATTACH`, `INSTALL` and SQL that tries to switch external access back on, both directly and through every SQL-accepting tool; warehouse checksum unchanged |
| GR-02 | Met | `src/governed_analytics/allowlist.py:37` sqlglot checks on the parsed tree; `:53` executes the regenerated SQL | `pytest -m gr02`: exit 0, 30 passed | 6 allowed and 21 blocked cases, including CTE and subquery tricks, `read_csv`, `read_parquet`, `query()`, stacked statements and comment tricks |
| GR-03 | Met | `src/governed_analytics/service.py:305` fetches at most `cap + 1` rows; `:300` timer interrupts the query; `:316` sets the truncation flag | `pytest -m gr03`: exit 0, 5 passed | Defaults are 1,000 rows and 30 s (`service.py`, `Config`). Cap and timeout are tested on both `query_metric` and `explore_sql` |
| GR-04 | **Not met** | `allowlist.py:79` (PII in SQL); `validate.py:26` with `server.py:41` (PII dimensions refuse start-up); `tracing.py:64` (question only in `kit.question`); `retention.py:23` and `:28` (purge functions) | `pytest -m gr04`: exit 0, 21 passed | Every tested behaviour holds, but **retention is not enforced**: nothing runs the purge. See below |
| GR-05 | Met | `src/governed_analytics/service.py:270` writes the receipt before returning; `replay.py:66` replays it | `pytest -m gr05`: exit 0, 3 passed | Receipts from both data tools replay as `reproduced` on definition and data |
| GR-06 | Met | `src/governed_analytics/service.py:152` sets the label from the catalogue; `:188` makes `explore_sql` always exploratory | `pytest -m gr06`: exit 0, 2 passed | The certified metric's own SQL sent through `explore_sql` gets the same number labelled exploratory. The model can't set the label |
| GR-07 | Met | `src/governed_analytics/tracing.py:47` middleware, registered at `server.py:47` | `pytest -m gr07`: exit 0, 4 passed | One span per call for all five tools, including schema rejections, an unknown tool, a guardrail block and an unknown receipt |
| GR-08 | Met | `src/governed_analytics/validate.py:42` (owner, semver, golden question) and `:57` (major bump); CI at `.github/workflows/governed-analytics.yml:50` | `pytest -m gr08`: exit 0, 11 passed; `python -m governed_analytics.validate --base HEAD~1`: exit 0, 0 problems | CI compares with the PR base, or with the previous commit on a push |

### Hard against soft (skill step 4)

Each control above sits in code, configuration or CI, and holds even if the assistant ignores every skill and prompt. The exception is GR-04 retention: the purge exists as code, but deletion only happens if a person remembers to run it, so it is a soft control.

### Trace cross-check (skill step 5)

I kept the logs from the verification runs (`pytest -m grNN --basetemp=<dir>`) and scanned every span.

| Check | Result |
|---|---|
| Spans scanned | 91, from 33 trace logs |
| Blocked calls (`kit.error.reason: guardrail_blocked`) | 26, all with GR-02 (15) or GR-04 (11) in `kit.guardrail.hits` |
| Timed-out calls | 1, with GR-03 |
| Truncated results | 2, with GR-03 |
| Hits without a matching block, timeout or truncation | none |

## Not met: what would fix it

**GR-04 retention.** The requirement says `kit.question` and `question_shape` MUST be deleted after the retention period. `python -m governed_analytics.retention` does the deletion and is tested, but no scheduler, CI job or server code runs it. Any of these would make it *Met*:

1. **In code (recommended for this proof of concept):** purge on server start-up and once a day while the server runs, plus a test showing a stale question disappears without anyone running a command.
2. **In configuration:** a committed scheduled job (for example a launchd or cron entry, or a CI schedule against shared logs), with the evidence that it ran.

After the fix, re-run `pytest -m gr04` on the new commit and update this report. Per the requirement's owner line, the retention period itself is IT's to set.

## Observations (not statuses)

- Filter values in `query_metric` and SQL text in `explore_sql` are free text and appear in receipts and in `gen_ai.tool.call.arguments`. They can only filter non-PII columns, and the scan found no PII values, but a person could still type a name as a value. IT (security) should decide whether that needs its own rule.
- `guardrail-review` is itself a community skill. Its own promotion needs this report checked by hand by at least one requirement owner. That has not happened yet.

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
git checkout 7b9ae0a7f6b034db16a99cdb9c0713ff83b33d50
cd examples/governed-analytics-mcp
data/.venv/bin/python data/generate.py && (cd dbt && ../data/.venv/bin/dbt build)
for m in gr01 gr02 gr03 gr04 gr05 gr06 gr07 gr08; do data/.venv/bin/pytest -m $m -q --basetemp=/tmp/gr-review/$m; echo "$m exit $?"; done
PYTHONPATH=src data/.venv/bin/python -m governed_analytics.validate --base HEAD~1
```
