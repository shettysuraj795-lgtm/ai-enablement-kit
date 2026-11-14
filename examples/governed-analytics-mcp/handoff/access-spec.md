# Access spec: governed-analytics MCP server

*For:* IT (warehouse access, identity, security). *Build:* `examples/governed-analytics-mcp`, reviewed at commit `0251a6c` ([guardrail review: Pass, 8 of 8](../reports/guardrail-review-2026-11-14-2.md)). *Design note:* [DESIGN.md](../DESIGN.md).

The server answers business questions from governed metrics and, when no metric fits, from guarded read-only SQL. In the proof of concept everything is local: a DuckDB file, dbt artefacts on disk, and logs in a folder. Production needs the same limits enforced by IT-owned controls rather than by a local file.

## Systems and access

| System | Access the server needs | Scope | Why (tool, requirement) | Proof of concept today | Production ask |
|---|---|---|---|---|---|
| Warehouse, `marts` schema | Read (`SELECT`) only | `marts.fct_orders`, `marts.fct_listings`, `marts.dim_dealers` | `query_metric`, `explore_sql` (GR-01, GR-02) | DuckDB file opened `read_only=True` with external access off (`service.py`) | A dedicated read-only role with `SELECT` on these three tables only. No `CREATE`, `INSERT`, `UPDATE`, `DELETE`, stage or file access |
| Warehouse, other schemas | **None** | `raw`, `staging`, `intermediate`, `seeds`, `information_schema` | Raw tables hold the data traps; exploration is limited to tested marts (GR-02) | Blocked by the server's SQL allow-list | Deny at the role. The allow-list stays as a second layer |
| Warehouse, PII columns | **None** | `fct_orders.buyer_id` (flagged `meta: {pii: true}` in dbt) | No tool needs row-level personal data (GR-04) | Blocked by the allow-list and catalogue validation; the server won't start if a metric exposes one | Column masking or a view without `buyer_id` for this role. New PII columns are flagged in dbt by BI |
| Warehouse, limits | Statement timeout, row limit | 30 s per query; 1,000 rows per result | GR-03 | Enforced by the server (`KIT_TIMEOUT_SECONDS`, `KIT_ROW_CAP`) | A warehouse-side timeout and resource group for the role, at or below these values |
| dbt artefacts | Read | `manifest.json` (columns and PII flags) and `run_results.json` (data snapshot) | Catalogue validation (GR-04, GR-08); receipts (GR-05) | Read from `dbt/target/` | Read access to wherever BI's dbt runs publish artefacts |
| Log storage | Append and rewrite | `receipts.jsonl`, `traces.jsonl`, `certification_requests.jsonl` | GR-05, GR-07; retention rewrites (GR-04) | Local folder `logs/` (`KIT_LOG_DIR`) | Shared storage with access as below |
| Outbound network | **None** | | | stdio on the user's machine | Decided with Tool enablement when packaged as a connector (HTTP transport) |
| Secrets | Warehouse credentials only | | | None: local file | From the secret manager; never in config files or logs |

## Data held in logs

| File | Contains | Personal data | Retention | Who reads it |
|---|---|---|---|---|
| `receipts.jsonl` | Structured intent, SQL, result hash, label, data snapshot | None by design; checked by a scan in `pytest -m gr04` | Long-term: needed to replay figures | BI |
| `traces.jsonl` | One entry per tool call: tool, arguments, latency, errors, persona (a role, never a person) | `kit.question` may contain whatever a user typed | Question text deleted after 30 days (`KIT_QUESTION_RETENTION_DAYS`); the rest is kept | ML / data science |
| `certification_requests.jsonl` | The receipt link, query shape, persona, and the question restated in general terms | The restated question, despite instructions not to include personal details | Restated question deleted after 30 days; the rest is kept | BI |

The server purges question text at start-up and every day while it runs (`KIT_PURGE_INTERVAL_SECONDS`). Two limits apply:
- retention pauses while the server is stopped;
- the purge's write lock covers one process only.

## Configuration at install

Set by Tool enablement when packaging; defaults are in [DESIGN.md](../DESIGN.md#configuration).

| Setting | Production value |
|---|---|
| `KIT_PERSONA` | The team's role, for example `finance_analyst`. Never a person |
| `KIT_WAREHOUSE`, `KIT_DBT_TARGET`, `KIT_LOG_DIR` | The production warehouse connection, dbt artefact location and log storage above |
| `KIT_ROW_CAP`, `KIT_TIMEOUT_SECONDS` | 1,000 and 30, or lower; never higher without the GR-03 owner |
| `KIT_QUESTION_RETENTION_DAYS`, `KIT_PURGE_INTERVAL_SECONDS` | As IT decides for GR-04; default 30 days and daily |
| `KIT_AS_OF` | **Unset.** It pins "today" for evals and demos only |

## Identity

The proof of concept records a *persona*, a role such as `finance_analyst` set per installation, and deliberately no user identity. In production, IT decides whether the server connects as one service role or on behalf of each user (SSO). If per-user, user identity must still stay out of receipts and traces (GR-04).

## Controls that stay in the server

These keep working whatever IT grants, and each has a test tagged with its requirement ID (`pytest -m grNN`):
- the SQL allow-list, which runs the regenerated SQL (GR-02);
- certified or exploratory labelling (GR-06);
- receipts and replay (GR-05);
- tracing middleware (GR-07);
- catalogue change control in CI (GR-08).

## Decisions for IT

1. A service role or per-user delegation for warehouse access?
2. Column masking or a restricted view for `buyer_id`?
3. Where the three log files live, who can read each, and whether 30 days is the right retention for question text.
4. Decommissioning: delete the logs, or schedule `python -m governed_analytics.retention`, so retention doesn't pause when the server stops for good.
5. Whether free-text filter values and SQL in receipts need their own rule (an observation in both guardrail reviews).
