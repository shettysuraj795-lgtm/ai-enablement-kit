-- Rollout success metrics and promotion candidates from the trace log and receipts.
--
-- Run with `python -m governed_analytics.trace_report`, or in the DuckDB CLI after
-- setting the two paths:
--   SET VARIABLE traces = 'logs/traces.jsonl';
--   SET VARIABLE receipts = 'logs/receipts.jsonl';
--   SET VARIABLE min_uses = 2;
--   .read analytics/trace_queries.sql
--
-- Lines are read as raw JSON and fields extracted by path, so a new attribute in
-- the trace contract never breaks these views. Each `-- name:` starts a query.

CREATE OR REPLACE VIEW spans AS
SELECT
    json_extract_string(j, '$.trace_id') AS trace_id,
    json_extract_string(j, '$.span_id') AS span_id,
    json_extract_string(j, '$.attributes."gen_ai.tool.name"') AS tool,
    json_extract_string(j, '$.status.code') AS status,
    json_extract_string(j, '$.attributes."kit.error.reason"') AS error_reason,
    json_extract_string(j, '$.attributes."kit.persona"') AS persona,
    json_extract_string(j, '$.attributes."kit.result.classification"') AS classification,
    json_extract_string(j, '$.attributes."kit.receipt.id"') AS receipt_id,
    json_extract_string(j, '$.attributes."kit.metric.name"') AS metric,
    json_extract_string(j, '$.attributes."kit.question"') AS question,
    coalesce(json_extract(j, '$.attributes."kit.guardrail.hits"')::VARCHAR[], []) AS guardrail_hits,
    json_extract_string(j, '$.start_time')::TIMESTAMP AS started_at,
    epoch_ms(json_extract_string(j, '$.end_time')::TIMESTAMP)
        - epoch_ms(json_extract_string(j, '$.start_time')::TIMESTAMP) AS latency_ms
FROM read_ndjson_objects(getvariable('traces')) AS t(j);

CREATE OR REPLACE VIEW receipts AS
SELECT
    json_extract_string(j, '$.receipt_id') AS receipt_id,
    json_extract_string(j, '$.created_at')::TIMESTAMP AS created_at,
    json_extract_string(j, '$.classification') AS classification,
    json_extract_string(j, '$.source') AS source,
    json_extract_string(j, '$.intent.metric') AS metric,
    json_extract_string(j, '$.sql_fingerprint') AS sql_fingerprint,
    json_extract_string(j, '$.compiled_sql') AS compiled_sql
FROM read_ndjson_objects(getvariable('receipts')) AS t(j);

-- name: overview
-- One row: volume, certified share of data answers, error rate, latency.
SELECT
    count(*) AS calls,
    count(classification) AS data_answers,
    round(avg((classification = 'certified')::INT) FILTER (WHERE classification IS NOT NULL), 3) AS certified_share,
    round(avg((status = 'ERROR')::INT), 3) AS error_rate,
    round(quantile_cont(latency_ms, 0.5), 1) AS p50_ms,
    round(quantile_cont(latency_ms, 0.95), 1) AS p95_ms
FROM spans;

-- name: by_tool
SELECT
    tool,
    count(*) AS calls,
    count(*) FILTER (WHERE status = 'ERROR') AS errors,
    round(avg((status = 'ERROR')::INT), 3) AS error_rate,
    round(quantile_cont(latency_ms, 0.5), 1) AS p50_ms,
    round(quantile_cont(latency_ms, 0.95), 1) AS p95_ms
FROM spans
GROUP BY tool
ORDER BY calls DESC, tool;

-- name: certified_share_by_persona
-- The headline rollout metric: how much of each team's numbers come from certified definitions.
SELECT
    persona,
    count(*) AS data_answers,
    count(*) FILTER (WHERE classification = 'certified') AS certified,
    round(avg((classification = 'certified')::INT), 3) AS certified_share
FROM spans
WHERE classification IS NOT NULL
GROUP BY persona
ORDER BY data_answers DESC, persona;

-- name: errors_by_reason
SELECT error_reason, tool, count(*) AS calls
FROM spans
WHERE status = 'ERROR'
GROUP BY error_reason, tool
ORDER BY calls DESC, error_reason, tool;

-- name: guardrail_hits
SELECT hit AS requirement, count(*) AS calls
FROM spans, unnest(guardrail_hits) AS h(hit)
GROUP BY hit
ORDER BY calls DESC, hit;

-- name: promotion_candidates
-- Exploratory questions people keep asking, grouped by query shape (literals ignored):
-- the queue BI reviews for new certified metrics.
SELECT
    r.sql_fingerprint,
    count(*) AS uses,
    count(DISTINCT s.persona) AS personas,
    string_agg(DISTINCT s.persona, ', ' ORDER BY s.persona) AS who,
    min(r.created_at) AS first_seen,
    max(r.created_at) AS last_seen,
    any_value(r.compiled_sql) AS example_sql,
    any_value(s.question) FILTER (WHERE s.question IS NOT NULL) AS example_question
FROM receipts AS r
LEFT JOIN spans AS s USING (receipt_id)
WHERE r.source = 'explore_sql'
GROUP BY r.sql_fingerprint
HAVING count(*) >= getvariable('min_uses')
ORDER BY uses DESC, personas DESC, last_seen DESC;

-- name: uncertified_metric_usage
-- Governed but uncertified metrics in use: certify the definition, or retire it.
SELECT
    metric,
    count(*) AS uses,
    count(DISTINCT persona) AS personas,
    max(started_at) AS last_used
FROM spans
WHERE tool = 'query_metric' AND classification = 'exploratory'
GROUP BY metric
ORDER BY uses DESC, metric;
