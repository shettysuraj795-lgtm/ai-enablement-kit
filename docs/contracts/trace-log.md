# Contract: trace log

- **Version:** 1.0
- **Format:** JSON Lines, one span per line, appended to `traces.jsonl`
- **Written by:** the MCP server's tool dispatcher, for every tool call including blocked and failed ones ([GR-07](../../requirements/GR-07-tracing.md))
- **Read by:** DuckDB queries for rollout metrics, guardrail reports and the promotion loop; later, an OpenTelemetry collector
- **Decision record:** [ADR-003](../adr/003-trace-log.md)

Each line is one span, shaped like an OpenTelemetry span. Attribute names follow the OpenTelemetry semantic conventions where one exists (`gen_ai.*`, `mcp.*`, `db.*`, `error.type`). Attributes specific to this kit use the `kit.*` namespace. Moving to an OpenTelemetry exporter later only changes where spans are sent, not what they contain.

### Pinned conventions

| Conventions | Source | Pinned at |
|---|---|---|
| GenAI and MCP (`gen_ai.*`, `mcp.*`, span name) | [open-telemetry/semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai), MCP server span in `docs/gen-ai/mcp.md` | commit [`e6658f1`](https://github.com/open-telemetry/semantic-conventions-genai/tree/e6658f14c9d9ea0760825f029cb82e7673f48fab) (6 Nov 2026) |
| Database, error, JSON-RPC, network (`db.*`, `error.type`, `jsonrpc.*`, `network.*`) | [open-telemetry/semantic-conventions](https://github.com/open-telemetry/semantic-conventions) | `v1.45.0`, the version the GenAI commit above builds on |

The GenAI repository has no tagged releases yet, so the pin is a commit. Most of these names are still marked *development* upstream. When the pin moves and a name changes, a new contract version renames it; spans already in the log are not rewritten. `duckdb` is not a registered value of `db.system.name`, which accepts custom values.

## Span fields

| Field | Type | Meaning |
|---|---|---|
| `trace_id` | string, 32 hex | From the client's W3C `traceparent` in the MCP request `_meta` if present; otherwise one trace per MCP session (server process, for stdio). |
| `span_id` | string, 16 hex | Unique per tool call. |
| `parent_span_id` | string or `null` | Parent from `traceparent`, if any. |
| `name` | string | `tools/call {tool}`, for example `tools/call query_metric`: the MCP server span format `{mcp.method.name} {target}` with the tool name as target. |
| `kind` | string | Always `SERVER`, as the MCP server span convention requires. |
| `start_time`, `end_time` | string | ISO 8601 UTC with milliseconds. Latency is `end_time - start_time`; it is not stored separately. |
| `status` | object | `code` is `OK` or `ERROR`; `message` explains an error. A call blocked by a guardrail is an `ERROR`. A truncated result is `OK` with a guardrail hit. |
| `resource` | object | `service.name` (`governed-analytics-mcp`) and `service.version`. |
| `attributes` | object | See below. |

### Attributes

| Attribute | Source | Meaning |
|---|---|---|
| `mcp.method.name` | OTel MCP | Always `tools/call`. |
| `gen_ai.operation.name` | OTel GenAI | Always `execute_tool`, so tool-call spans can be analysed alongside non-MCP tool calls. |
| `gen_ai.tool.name` | OTel GenAI | The MCP tool called, for example `query_metric` or `explore_sql`. |
| `gen_ai.tool.call.arguments` | OTel GenAI | The tool arguments as an object, without `question` (see *Question capture*). |
| `jsonrpc.request.id` | OTel JSON-RPC | The JSON-RPC request ID, as a string. |
| `mcp.protocol.version` | OTel MCP | MCP protocol version negotiated with the client, for example `2025-06-18`. |
| `network.transport` | OTel network | `pipe` for stdio, as used from a desktop client. |
| `db.system.name` | OTel DB | `duckdb`. Absent if no query ran. |
| `db.query.text` | OTel DB | The SQL executed. Matches the receipt's `compiled_sql`. Absent if no query ran. |
| `db.response.returned_rows` | OTel DB | Rows returned after the row cap. |
| `error.type` | OTel | Set only when `status.code` is `ERROR`. `tool_error` when the tool returns a result with `isError: true` (all kit errors do); otherwise the JSON-RPC error code. |
| `kit.error.reason` | kit | Why a tool error happened: `guardrail_blocked`, `timeout`, `invalid_intent` or `internal`. |
| `kit.persona` | kit | The role the server was configured for, for example `finance_analyst`. Never a person's name or ID ([GR-04](../../requirements/GR-04-pii-protection.md)). |
| `kit.receipt.id` | kit | The receipt written for this call, or absent if none. |
| `kit.result.classification` | kit | `certified` or `exploratory`, or absent if no result. |
| `kit.metric.name` | kit | Metric used, for `query_metric` calls. |
| `kit.metric.version` | kit | Metric version used, for `query_metric` calls. |
| `kit.result.truncated` | kit | `true` if the row cap cut the result ([GR-03](../../requirements/GR-03-result-caps.md)). |
| `kit.guardrail.hits` | kit | Requirement IDs that fired on this call, for example `["GR-02"]`. Empty if none. |
| `kit.question` | kit | The optional `question` tool argument (see *Question capture*). Absent if not given or already deleted under retention. |

### Question capture

Every data tool accepts an optional `question` argument: the user's question in the assistant's words. It is not guaranteed to be verbatim. It is used to find unmet demand, to draft golden eval questions and to explain promotion candidates, and it has no effect on the result.

The server removes `question` from the arguments before writing `gen_ai.tool.call.arguments` and stores it only in `kit.question`. It is never written to a receipt. Because it is free text and may contain personal data, it is deleted after the retention period set in [GR-04](../../requirements/GR-04-pii-protection.md); the rest of the span is kept.

## Querying the log

The log is loaded straight into DuckDB:

```sql
-- p95 latency and certified share per tool
SELECT attributes."gen_ai.tool.name" AS tool,
       quantile_cont(epoch_ms(end_time::TIMESTAMP) - epoch_ms(start_time::TIMESTAMP), 0.95) AS p95_ms,
       avg((attributes."kit.result.classification" = 'certified')::INT) AS certified_share
FROM read_json_auto('traces.jsonl')
GROUP BY tool;

-- guardrail hits by requirement
SELECT hit, count(*) AS calls
FROM read_json_auto('traces.jsonl'), unnest(attributes."kit.guardrail.hits") AS t(hit)
GROUP BY hit;
```

## Worked example: `net_merchandise_value` for last quarter

The span for the call that produced the [example receipt](receipt.md#worked-example-net_merchandise_value-for-last-quarter). Its IDs and SQL match that receipt.

```json
{
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "parent_span_id": null,
  "name": "tools/call query_metric",
  "kind": "SERVER",
  "start_time": "2026-11-14T10:42:07.105Z",
  "end_time": "2026-11-14T10:42:07.318Z",
  "status": { "code": "OK", "message": null },
  "resource": {
    "service.name": "governed-analytics-mcp",
    "service.version": "0.1.0"
  },
  "attributes": {
    "mcp.method.name": "tools/call",
    "gen_ai.operation.name": "execute_tool",
    "gen_ai.tool.name": "query_metric",
    "gen_ai.tool.call.arguments": {
      "metric": "net_merchandise_value",
      "dimensions": [],
      "filters": [],
      "time_grain": "quarter",
      "time_range": { "relative": "last_quarter" }
    },
    "jsonrpc.request.id": "7",
    "mcp.protocol.version": "2025-06-18",
    "network.transport": "pipe",
    "db.system.name": "duckdb",
    "db.query.text": "SELECT date_trunc('quarter', order_date) AS period, sum(net_amount_eur) AS net_merchandise_value FROM marts.fct_orders WHERE is_paid = TRUE AND order_date >= DATE '2026-07-01' AND order_date < DATE '2026-10-01' GROUP BY period ORDER BY period",
    "db.response.returned_rows": 1,
    "kit.persona": "finance_analyst",
    "kit.receipt.id": "rcpt_01JCZ8Q4V6T3M9R2K7H5N1D0WB",
    "kit.result.classification": "certified",
    "kit.metric.name": "net_merchandise_value",
    "kit.metric.version": "1.0.0",
    "kit.result.truncated": false,
    "kit.guardrail.hits": [],
    "kit.question": "What was our revenue after refunds last quarter?"
  }
}
```

A blocked `explore_sql` call would instead have the name `tools/call explore_sql`, `status.code: "ERROR"`, `error.type: "tool_error"`, `kit.error.reason: "guardrail_blocked"`, `kit.guardrail.hits: ["GR-02"]`, and no receipt or `db.*` attributes.
