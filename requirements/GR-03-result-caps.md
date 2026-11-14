# GR-03: Results are capped in rows and time

- **ID:** GR-03
- **Requirement:** Every query MUST return at most the configured row cap (default 1,000) and MUST be cancelled after the configured timeout (default 30 seconds). A truncated result MUST say so in the tool response and in the trace log.
- **Rationale:** Large result sets overflow the assistant's context and invite it to summarise silently. Long queries tie up shared compute. Silent truncation is worse than either.
- **Owner:** Tool enablement. Until handover: kit maintainer.
- **Enforced by:** The server fetches at most `cap + 1` rows from the cursor (keeping the compiled `ORDER BY` exact), interrupts the query after the timeout, and sets `truncated: true` when more rows exist.
- **How to verify:** `pytest -m gr03` runs a query that would return more rows than the cap and one that exceeds the timeout, and asserts the cap, the cancellation, the `truncated` flag and a trace span with `kit.guardrail.hits` containing `GR-03`.
