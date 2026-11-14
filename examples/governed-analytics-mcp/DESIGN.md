# Design note: governed-analytics MCP server

The design note that [`mcp-tool-design`](../../skills/community/mcp-tool-design/SKILL.md) asks for. Each choice below names the skill step that shaped it.

## Tools

| Tool | Intent sentence | Arguments | Returns |
|---|---|---|---|
| `query_metric` | "What was *metric* for *period*, by *dimension*?" | `metric`, `time_grain`, `period` or `start`+`end`, `dimensions`, `filters`, optional `question` | Rows, metric definition and version, `certified`/`exploratory` label, resolved time range, receipt ID, reporting instruction |

This is the first slice, so there is only one tool. Planned next: `list_metrics` (catalogue and glossary), `explore_sql` (the guarded escape hatch, step 8) and `request_certification`. Replay stays a command for BI, not a tool for the model.

## Where the skill shaped the build

| Step | Choice in this server | Where |
|---|---|---|
| 1. Name the intents | One intent-named tool, `query_metric`; no `run_sql` on the governed path | `server.py` |
| 2. Type every argument | `metric`, `dimensions`, `time_grain`, `period` and filter `op` are enums built from the catalogue; dates are typed; relative periods are resolved on the server against a recorded as-of date | `server.py`, `periods.py` |
| 3. Compile deterministically | The model fills in the intent; `compile_intent` produces the SQL; dimensions and filters are sorted so order doesn't matter | `compiler.py` |
| 4. Provenance on every result | The response carries the metric's definition and version, the label, the time range and a receipt ID, plus an instruction to report them | `service.py` |
| 5. Errors as guidance | Compiler and service errors become `is_error` results that name the valid options; schema rejections list the allowed values | `compiler.py`, `service.py` |
| 6. Least privilege | Read-only DuckDB connection; marts schema only; row cap and timeout; PII columns can't be named because they aren't in any enum | `service.py`, `catalogue` |
| 7. Trace every call | MCP middleware wraps the dispatcher, so schema rejections are traced too; tools only annotate the span | `tracing.py` |
| 8. Guarded escape hatch | Not in this slice (see *Tools*) | |
| 9. Hand-off line | See *Hand-off* | |

## Guardrails

| ID | Control in this server | Evidence |
|---|---|---|
| GR-01 | `duckdb.connect(..., read_only=True)` for every query | `pytest -m gr01` (to write) |
| GR-02 | No raw SQL on this path; `explore_sql` will carry the allow-list | n/a until `explore_sql` |
| GR-03 | At most `row_cap + 1` rows fetched; `con.interrupt()` after `timeout_seconds`; `truncated` flag and `GR-03` span hit | `tests/test_server.py::test_row_cap_truncates_and_records_gr03` |
| GR-04 | PII columns are in no enum; `question` goes only to `kit.question` | `test_receipt_is_written_and_replays`, `test_trace_span_follows_contract` |
| GR-05 | Receipt appended before the result is returned; replay reproduces the hash | `test_receipt_is_written_and_replays` |
| GR-06 | Label set from the catalogue's `certified` flag, never by the model | `test_happy_path_returns_golden_answer_with_provenance` |
| GR-07 | One span per `tools/call`, including failures | `test_trace_span_follows_contract`, `test_schema_rejection_is_still_traced` |
| GR-08 | Catalogue validation in CI | Not yet built |

The per-requirement `pytest -m grNN` markers come with the guardrail tests. Until then this table is a design claim, not `guardrail-review` evidence.

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

- The data snapshot comes from the latest `run_results.json`, so `dbt docs generate` changes `dbt_invocation_id` without changing the data. A production version would stamp the snapshot into the warehouse during the build.
- Receipts and traces are local append-only files for one user over stdio. Shared storage is a hand-off item.

## Hand-off

| Item | Team |
|---|---|
| Read-only warehouse role and SSO instead of a local file | IT |
| Packaging as an organisation-wide connector; versioned releases | Tool enablement |
| Trace export to the monitoring stack; LLM-as-judge on golden questions | ML / data science |
| New metrics and certification decisions | BI |
