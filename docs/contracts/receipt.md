# Contract: query receipt

- **Version:** 1.0
- **Format:** JSON. Each receipt is appended as one line to `receipts.jsonl` and its `receipt_id` is returned with the result.
- **Written by:** the MCP server, for every response that returns data ([GR-05](../../requirements/GR-05-receipts.md))
- **Read by:** the replay command, BI reviewers, the promotion loop, evals
- **Decision record:** [ADR-002](../adr/002-query-receipts.md)

A receipt records everything needed to explain a number and reproduce it: what was asked for in structured form, which definition answered it, the exact SQL, which data it ran on, and a fingerprint of the result.

## Fields

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | Version of this contract, `"1.0"`. |
| `receipt_id` | string | `rcpt_` followed by a ULID, so IDs sort by creation time. |
| `created_at` | string | ISO 8601 timestamp in UTC. |
| `classification` | `certified` \| `exploratory` | Set by the server, never by the assistant ([GR-06](../../requirements/GR-06-certified-vs-exploratory.md)). |
| `source` | `metric` \| `explore_sql` | Which path produced the result. |
| `intent` | object or `null` | The structured request (see below). `null` when `source` is `explore_sql`. |
| `metric_version` | string or `null` | Semver of the metric definition used. `null` for `explore_sql`. |
| `compiler_version` | string | Version of the compiler that produced the SQL. Same intent, metric version and compiler version always give the same SQL. |
| `compiled_sql` | string | The exact SQL executed, after guardrail checks and before the row cap is applied. |
| `sql_fingerprint` | string | SHA-256 of the SQL after sqlglot normalisation with literals replaced by placeholders. Identical query shapes share a fingerprint; the promotion loop counts these. |
| `data_snapshot` | object | `snapshot_at` (ISO 8601 UTC, when the dbt build that produced the data finished) and `dbt_invocation_id` (from dbt's `run_results.json`). |
| `result` | object | `columns` (names in order), `row_count`, `truncated` (boolean, [GR-03](../../requirements/GR-03-result-caps.md)) and `hash` (see *Result hash*). |
| `trace_id`, `span_id` | string | Link to the span in the [trace log](trace-log.md) for this call. |

The user's natural-language question is never stored in a receipt. Receipts are kept long-term and shared with reviewers, a question can contain personal data, and the structured intent is what determines the number. If the assistant passes the optional `question` argument, it goes to the trace log only, under the retention rule in [GR-04](../../requirements/GR-04-pii-protection.md). See [question capture](trace-log.md#question-capture).

### Intent

| Field | Type | Meaning |
|---|---|---|
| `metric` | string | Metric `name` from the catalogue. |
| `dimensions` | list of strings | Group-by columns; each must be in the metric's `allowed_dimensions`. Empty for a single total. |
| `filters` | list | User filters, in the [filter shape](metric-definition.md#filter-shape). Fixed metric filters are not repeated here; they are in the metric version. |
| `time_grain` | string | One of the metric's `time_grains`. |
| `time_range` | object | Always contains `start`, `end` and `as_of`. `start` and `end` are the resolved absolute range as ISO dates, half-open (`start` inclusive, `end` exclusive). `as_of` is the date, in UTC, that the request was evaluated on. `relative` is added when the request used a relative period, for example `last_quarter`. |

Relative periods are resolved to absolute dates by the server before compiling, so the SQL never contains `current_date`. `as_of` is recorded even when the request gave absolute dates, so every receipt answers "asked on which day, about which days". It is a different thing from `data_snapshot.snapshot_at`, which says how fresh the data was.

### Result hash

`result.hash` is `sha256:` followed by the hex SHA-256 of the canonical result:

1. Rows in the order given by the compiled SQL, which always ends in `ORDER BY` over every non-aggregate column.
2. Each value rendered as a string: decimals at their column's fixed scale, dates and timestamps in ISO 8601 UTC, `NULL` as `null`.
3. Serialised as a JSON array whose first element is the column names and the rest are rows, with no whitespace, encoded as UTF-8.

## Replay

`replay <receipt_id>` performs two checks and reports each one separately:

1. **Definition:** it recompiles `intent` against `metric_version` with the same `compiler_version` and checks that the SQL matches `compiled_sql`. If it doesn't match, the compiler or catalogue changed something it shouldn't have.
2. **Data:** it runs `compiled_sql` and compares the result hash. If the current `dbt_invocation_id` matches, the hashes must match. If it doesn't match, replay reports *data has changed since this receipt* and shows both results; it does not claim the number was reproduced.

The proof of concept keeps only the current data snapshot. Keeping older snapshots is a handover item for the warehouse owner.

## Worked example: `net_merchandise_value` for last quarter

Asked on 14 Nov 2026 for last quarter's net merchandise value. Identifiers, timestamps, the figure and the hashes are illustrative.

```json
{
  "schema_version": "1.0",
  "receipt_id": "rcpt_01JCZ8Q4V6T3M9R2K7H5N1D0WB",
  "created_at": "2026-11-14T10:42:07.318Z",
  "classification": "certified",
  "source": "metric",
  "intent": {
    "metric": "net_merchandise_value",
    "dimensions": [],
    "filters": [],
    "time_grain": "quarter",
    "time_range": {
      "start": "2026-07-01",
      "end": "2026-10-01",
      "as_of": "2026-11-14",
      "relative": "last_quarter"
    }
  },
  "metric_version": "1.0.0",
  "compiler_version": "0.1.0",
  "compiled_sql": "SELECT date_trunc('quarter', order_date) AS period, sum(net_amount_eur) AS net_merchandise_value FROM marts.fct_orders WHERE is_paid = TRUE AND order_date >= DATE '2026-07-01' AND order_date < DATE '2026-10-01' GROUP BY period ORDER BY period",
  "sql_fingerprint": "sha256:5d1f0c7a9e2b4c86f3a1d0e9b7c5a3f1e8d6c4b2a0f9e7d5c3b1a9f8e6d4c2b0",
  "data_snapshot": {
    "snapshot_at": "2026-11-14T06:00:12Z",
    "dbt_invocation_id": "3f6c2a1e-8b7d-4e5f-9a0b-1c2d3e4f5a6b"
  },
  "result": {
    "columns": ["period", "net_merchandise_value"],
    "row_count": 1,
    "truncated": false,
    "hash": "sha256:9a4e2c7b1f0d8e6a5c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d"
  },
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7"
}
```

The canonical result behind that hash would be `[["period","net_merchandise_value"],["2026-07-01","4812337.50"]]`.

An `explore_sql` receipt has the same shape with `classification: "exploratory"`, `source: "explore_sql"`, `intent: null` and `metric_version: null`. Its `compiled_sql` is the assistant's SQL after the [GR-02](../../requirements/GR-02-query-allow-list.md) checks.
