# Contract: trace log

- **Version:** 1.0
- **Format:** JSON Lines, one span per line, appended to `traces.jsonl`
- **Written by:** the MCP server's tool dispatcher, for every tool call including blocked and failed ones ([GR-07](../../requirements/GR-07-tracing.md))
- **Read by:** DuckDB queries for rollout metrics, guardrail reports and the promotion loop; later, an OpenTelemetry collector
- **Decision record:** [ADR-003](../adr/003-trace-log.md)

Each line is one span, shaped like an OpenTelemetry span. Attribute names follow the OpenTelemetry semantic conventions where one exists (`gen_ai.*`, `mcp.*`, `db.*`, `error.type`). Attributes specific to this kit use the `kit.*` namespace. Moving to an OpenTelemetry exporter later only changes where spans are sent, not what they contain.

The GenAI, MCP and database conventions are still marked *development* upstream. The names below are pinned as of this contract version. If the upstream names change, a new contract version renames them; spans already in the log are not rewritten.

## Span fields

| Field | Type | Meaning |
|---|---|---|
| `trace_id` | string, 32 hex | From the client's W3C `traceparent` in the MCP request `_meta` if present; otherwise one trace per MCP session. |
| `span_id` | string, 16 hex | Unique per tool call. |
| `parent_span_id` | string or `null` | Parent from `traceparent`, if any. |
| `name` | string | `execute_tool <tool name>`, following the GenAI convention. |
| `kind` | string | Always `SERVER`. |
| `start_time`, `end_time` | string | ISO 8601 UTC with milliseconds. Latency is `end_time - start_time`; it is not stored separately. |
| `status` | object | `code` is `OK` or `ERROR`; `message` explains an error. A call blocked by a guardrail is an `ERROR`. A truncated result is `OK` with a guardrail hit. |
| `resource` | object | `service.name` (`governed-analytics-mcp`) and `service.version`. |
| `attributes` | object | See below. |

### Attributes

| Attribute | Source | Meaning |
|---|---|---|
| `gen_ai.operation.name` | OTel GenAI | Always `execute_tool`. |
| `gen_ai.tool.name` | OTel GenAI | The MCP tool called, for example `query_metric` or `explore_sql`. |
| `gen_ai.tool.call.arguments` | OTel GenAI | The tool arguments as a JSON string. |
| `mcp.method.name` | OTel MCP | Always `tools/call`. |
| `db.system.name` | OTel DB | `duckdb`. Absent if no query ran. |
| `db.query.text` | OTel DB | The SQL executed. Matches the receipt's `compiled_sql`. Absent if no query ran. |
| `db.response.returned_rows` | OTel DB | Rows returned after the row cap. |
| `error.type` | OTel | Short error class when `status.code` is `ERROR`, for example `guardrail_blocked` or `timeout`. |
| `kit.persona` | kit | The role the server was configured for, for example `finance_analyst`. Never a person's name or ID ([GR-04](../../requirements/GR-04-pii-protection.md)). |
| `kit.receipt.id` | kit | The receipt written for this call, or absent if none. |
| `kit.result.classification` | kit | `certified` or `exploratory`, or absent if no result. |
| `kit.metric.name` | kit | Metric used, for `query_metric` calls. |
| `kit.metric.version` | kit | Metric version used, for `query_metric` calls. |
| `kit.result.truncated` | kit | `true` if the row cap cut the result ([GR-03](../../requirements/GR-03-result-caps.md)). |
| `kit.guardrail.hits` | kit | Requirement IDs that fired on this call, for example `["GR-02"]`. Empty if none. |

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

## Worked example: `net_revenue` for last quarter

The span for the call that produced the [example receipt](receipt.md#worked-example-net_revenue-for-last-quarter). Its IDs and SQL match that receipt.

```json
{
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "parent_span_id": null,
  "name": "execute_tool query_metric",
  "kind": "SERVER",
  "start_time": "2026-11-14T10:42:07.105Z",
  "end_time": "2026-11-14T10:42:07.318Z",
  "status": { "code": "OK", "message": null },
  "resource": {
    "service.name": "governed-analytics-mcp",
    "service.version": "0.1.0"
  },
  "attributes": {
    "gen_ai.operation.name": "execute_tool",
    "gen_ai.tool.name": "query_metric",
    "gen_ai.tool.call.arguments": "{\"metric\":\"net_revenue\",\"dimensions\":[],\"filters\":[],\"time_grain\":\"quarter\",\"time_range\":{\"relative\":\"last_quarter\"}}",
    "mcp.method.name": "tools/call",
    "db.system.name": "duckdb",
    "db.query.text": "SELECT date_trunc('quarter', order_date) AS period, sum(net_amount_eur) AS net_revenue FROM marts.fct_orders WHERE is_paid = TRUE AND order_date >= DATE '2026-07-01' AND order_date < DATE '2026-10-01' GROUP BY period ORDER BY period",
    "db.response.returned_rows": 1,
    "kit.persona": "finance_analyst",
    "kit.receipt.id": "rcpt_01JCZ8Q4V6T3M9R2K7H5N1D0WB",
    "kit.result.classification": "certified",
    "kit.metric.name": "net_revenue",
    "kit.metric.version": "1.0.0",
    "kit.result.truncated": false,
    "kit.guardrail.hits": []
  }
}
```

A blocked `explore_sql` call would instead have `status.code: "ERROR"`, `error.type: "guardrail_blocked"`, `kit.guardrail.hits: ["GR-02"]`, and no receipt or `db.*` attributes.
