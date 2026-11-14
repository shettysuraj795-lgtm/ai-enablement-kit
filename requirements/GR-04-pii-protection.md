# GR-04: Personal data is never returned or logged

- **ID:** GR-04
- **Requirement:** Columns flagged `meta: {pii: true}` in the dbt `schema.yml` MUST NOT be selected, grouped by, filtered on or exposed as metric dimensions. Receipts and trace logs MUST NOT contain user identity or personal data; personas are recorded as roles only.
- **Rationale:** Business teams rarely need row-level personal data to answer a business question. Flagging columns where they are already documented keeps one source of truth.
- **Owner:** IT (security). BI flags the columns. Until handover: kit maintainer.
- **Enforced by:** The metric catalogue validator rejects PII columns as dimensions; `explore_sql` rejects queries that reference PII columns, resolved through the dbt manifest.
- **How to verify:** `pytest -m gr04` asserts that a metric with a PII dimension fails validation, that queries touching PII columns (directly, via `SELECT *` or through a CTE) are blocked, and that a scan of the trace log and receipts finds no flagged column values.
