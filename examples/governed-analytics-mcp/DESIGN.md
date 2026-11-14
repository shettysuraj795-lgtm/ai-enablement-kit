# Design note: governed-analytics MCP server

The design note that [`mcp-tool-design`](../../skills/community/mcp-tool-design/SKILL.md) asks for. Each choice below names the skill step that shaped it.

## Tools

| Tool | Intent sentence | Arguments | Returns |
|---|---|---|---|
| `list_metrics` | "What can I ask about?" / "What could *revenue* mean?" | optional `term` | The catalogue and glossary; with a known `term`, its governed options, their meanings and the next step (ask, or name the choice) |
| `describe_metric` | "What exactly does *metric* mean?" | `metric` | Definition, unit, version, certified flag, owner, grains, dimensions, filters always applied, glossary terms that lead to it |
| `query_metric` | "What was *metric* for *period*, by *dimension*?" | `metric`, `time_grain`, `period` or `start`+`end`, `dimensions`, `filters`, optional `question` | Rows, metric definition and version, `certified`/`exploratory` label, resolved time range, receipt ID, reporting instruction |
| `explore_sql` | "No metric covers this; can you look it up anyway?" | `sql` (one SELECT over the marts), optional `question` | Rows, the SQL that ran, label always `exploratory`, receipt ID, and an instruction to say it is exploratory and suggest certification if it will be reused |

| `request_certification` | "Can BI make this an official number?" | `receipt_id` (exploratory), `question_shape` (general terms, at most 300 characters) | A request ID; appends to `certification_requests.jsonl`, linked to the receipt's SQL fingerprint |

`request_certification` returns no data, so it writes no receipt; it is traced like every call. It refuses certified receipts and unknown IDs. `question_shape` is free text, so the retention command purges it with `kit.question` (GR-04).

## Replay

`python -m governed_analytics.replay <receipt_id>` is a command for BI, not a tool for the model. It reports two checks separately:

- **Definition:** recompile the intent with the metric at the receipt's version (from git history if the catalogue has moved on), or re-check an `explore_sql` receipt against today's allow-list.
- **Data:** rerun the stored SQL on the locked-down connection and compare the hash, knowing whether the dbt build is the same.

| Verdict | Meaning | Exit |
|---|---|---|
| `reproduced` | Same data, same result | 0 |
| `unchanged_on_new_data` | The data was rebuilt, the result didn't move | 0 |
| `data_changed` | The data was rebuilt and the result moved; the receipt records what was seen | 2 |
| `mismatch` | Same data, different result: investigate | 1 |
| `definition_changed` | Recompiling no longer gives the stored SQL | 1 |

A check that can't run (an unknown metric version, or a different compiler version) is reported as `skipped`, never as a match.

The glossary lives in `glossary.yml` and a test keeps it in step with the contract. Surfacing the options for "revenue" is the server's job; *acting* on them (asking the user, or naming the choice) is the assistant's, guided by the tool's `next_step` and later the `governed-analytics` skill. Only the first part is a hard control.

## Catalogue

All seven metrics from [metric catalogue v0](../../docs/contracts/metric-catalogue-v0.md) are in `metrics/`, and a test keeps the files identical to the contract. `active_listings` is uncertified, so its results are labelled exploratory (GR-06). The catalogue refuses to load a metric that divides by anything other than `nullif(…, 0)`, so a ratio over an empty group returns NULL instead of failing. That check is in code, not left to authoring convention.

## Where the skill shaped the build

| Step | Choice in this server | Where |
|---|---|---|
| 1. Name the intents | Five intent-named tools (`list_metrics`, `describe_metric`, `query_metric`, `explore_sql`, `request_certification`); no `run_sql` on the governed path | `server.py` |
| 2. Type every argument | `metric`, `dimensions`, `time_grain`, `period` and filter `op` are enums built from the catalogue; dates are typed; relative periods are resolved on the server against a recorded as-of date | `server.py`, `periods.py` |
| 3. Compile deterministically | The model fills in the intent; `compile_intent` produces the SQL; dimensions and filters are sorted so order doesn't matter | `compiler.py` |
| 4. Provenance on every result | The response carries the metric's definition and version, the label, the time range and a receipt ID, plus an instruction to report them | `service.py` |
| 5. Errors as guidance | Compiler and service errors become `is_error` results that name the valid options; schema rejections list the allowed values | `compiler.py`, `service.py` |
| 6. Least privilege | Read-only DuckDB connection; marts schema only; row cap and timeout; PII columns can't be named because they aren't in any enum | `service.py`, `catalogue` |
| 7. Trace every call | MCP middleware wraps the dispatcher, so schema rejections are traced too; tools only annotate the span | `tracing.py` |
| 8. Guarded escape hatch | `explore_sql`: a sqlglot allow-list on the parsed tree, running the regenerated SQL on the locked-down connection; always exploratory and receipted ([ADR-007](../../docs/adr/007-exploratory-sql-defence-in-depth.md)). Its description lists the marts and their non-PII columns | `allowlist.py`, `service.py` |
| 9. Hand-off line | See *Hand-off* | |

## Guardrails

Each requirement has its own test file, `tests/test_grNN_*.py`, tagged so that `pytest -m grNN` runs its evidence.

| ID | Control in this server | Evidence |
|---|---|---|
| GR-01 | `connect_read_only`: `read_only=True` and `enable_external_access=False` (read-only alone still allows `COPY ... TO`) | `pytest -m gr01` |
| GR-02 | `explore_sql` checks the parsed tree: one SELECT, `marts.*` or CTEs only, no table, file or SQL-string functions; executes the regenerated SQL | `pytest -m gr02` |
| GR-03 | At most `row_cap + 1` rows fetched; `con.interrupt()` after `timeout_seconds`; `truncated` flag and `GR-03` span hit | `pytest -m gr03` |
| GR-04 | PII columns from the dbt manifest; the server refuses to start if a metric exposes one; `explore_sql` blocks PII columns, whole-row references and `*` over PII tables; `question` only in `kit.question`; `governed_analytics.retention` purges it | `pytest -m gr04` |
| GR-05 | Receipt appended before the result is returned; `governed_analytics.replay` checks definition and data | `pytest -m gr05` |
| GR-06 | Label set from the catalogue's `certified` flag; it agrees in response, receipt and span | `pytest -m gr06` |
| GR-07 | One span per `tools/call` from the middleware, including schema rejections and unknown tools | `pytest -m gr07` |
| GR-08 | `governed_analytics.validate`: owner, semver and a golden question for certified metrics; major bump for definition changes since `--base` (CI) | `pytest -m gr08` |

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `KIT_PERSONA` | `unspecified` | Role recorded in traces (never a person) |
| `KIT_AS_OF` | today (UTC) | Pin the as-of date, for evals and demos |
| `KIT_LOG_DIR` | `logs/` | Where `receipts.jsonl` and `traces.jsonl` go (gitignored) |
| `KIT_WAREHOUSE` | `data/warehouse.duckdb` | The DuckDB file |
| `KIT_DBT_TARGET` | `dbt/target` | Where `run_results.json` gives the data snapshot |
| `KIT_ROW_CAP`, `KIT_TIMEOUT_SECONDS` | `1000`, `30` | GR-03 limits |

## Known limits

- `explore_sql` blocks aggregates over PII too (for example `count(DISTINCT buyer_id)`). A buyer count needs a governed metric.
- The function blocklist must grow when DuckDB adds file-reading functions. The connection's disabled external access is the backstop.

- The data snapshot comes from the latest `run_results.json`, so `dbt docs generate` changes `dbt_invocation_id` without changing the data. A production version would stamp the snapshot into the warehouse during the build.
- Receipts and traces are local append-only files for one user over stdio. Shared storage is a hand-off item.

## Hand-off

| Item | Team |
|---|---|
| Read-only warehouse role and SSO instead of a local file | IT |
| Packaging as an organisation-wide connector; versioned releases | Tool enablement |
| Trace export to the monitoring stack; LLM-as-judge on golden questions | ML / data science |
| New metrics and certification decisions | BI |

## Evals

`python -m governed_analytics.evals` runs every golden question through the MCP server in CI, with the as-of date pinned to the golden file's.

| Question kind | Checked without a model (every push) | Needs a model in the loop |
|---|---|---|
| `metric` | Rows within tolerance, label, and receipt intent equal to the golden intent | `must_name_metric`: the answer names the metric |
| `ambiguous` | `list_metrics(term)` offers exactly the golden options, and each option's answer is correct | The assistant lists the options or names its choice |
| `uncovered` | Nothing | An exploratory answer and an offer to request certification |

Model-in-the-loop checks are reported as `needs-model`, never counted as passes.

## Trace queries

`python -m governed_analytics.trace_report` loads `traces.jsonl` and `receipts.jsonl` into an in-memory DuckDB and runs the named queries in [`analytics/trace_queries.sql`](analytics/trace_queries.sql). The same file runs in the DuckDB CLI.

| Query | Answers | Used by |
|---|---|---|
| `overview` | Volume, certified share of data answers, error rate, p50/p95 latency | Rollout success metrics |
| `by_tool` | Calls, errors and latency per tool | ML / data science monitoring |
| `certified_share_by_persona` | How much of each team's numbers come from certified definitions | The headline adoption metric |
| `errors_by_reason`, `guardrail_hits` | Where people get stuck; which GR controls fire | Tool enablement, `guardrail-review` |
| `promotion_candidates` | Exploratory queries reused at least `--min-uses` times (default 2), grouped by SQL shape, so different dates count as one question, with who asked and an example question | BI's certification queue |
| `uncertified_metric_usage` | Governed but uncertified metrics in use | BI: certify the definition or retire it |
| `certification_requests` | Explicit requests, grouped by SQL shape, with how often that shape was used | BI's certification queue, ranked by demand |

Fields are extracted from raw JSON by path, so a new span attribute never breaks the views. Example questions disappear once retention purges `kit.question` (GR-04), but the counts stay.
