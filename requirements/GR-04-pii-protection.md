# GR-04: Personal data is never returned or logged

- **ID:** GR-04
- **Requirement:** Columns flagged `meta: {pii: true}` in the dbt `schema.yml` MUST NOT be selected, grouped by, filtered on or exposed as metric dimensions. Receipts MUST NOT contain user identity, question text or personal data. Trace logs MUST NOT contain user identity, and personas are recorded as roles only. The one exception is the optional question text in `kit.question`, described below.
- **Retention:** `kit.question` MUST be deleted from spans older than the retention period, which defaults to 30 days and is set by IT (security). The rest of the span is kept. Question text MUST NOT be copied into any other field, file or dataset, except golden eval questions that a person has reviewed and rewritten without personal data.
- **Rationale:** Business teams rarely need row-level personal data to answer a business question. Flagging columns where they are already documented keeps one source of truth. Question text is useful for finding unmet demand and writing evals, but people do type names into questions, so it is kept briefly and in one place.
- **Owner:** IT (security). BI flags the columns. Until handover: kit maintainer.
- **Enforced by:** The metric catalogue validator rejects PII columns as dimensions. `explore_sql` rejects queries that reference PII columns, resolved through the dbt manifest. The server writes `question` only to `kit.question`, and a scheduled job deletes that field after the retention period.
- **How to verify:** `pytest -m gr04` checks the following:
  - a metric with a PII dimension fails validation;
  - queries touching PII columns (directly, via `SELECT *` or through a CTE) are blocked;
  - a scan of the trace log and receipts finds no flagged column values;
  - question text appears in neither receipts nor `gen_ai.tool.call.arguments`;
  - the retention job removes `kit.question` from spans older than the retention period and leaves newer spans unchanged.
