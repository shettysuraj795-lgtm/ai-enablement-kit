# Requirements changelog

Every change to a requirement's wording is recorded here, newest first. A change that alters what *Met* means, such as a new limit or a different control, also notes which `guardrail-review` reports it makes stale.

## 14 Nov 2026

- **GR-04 (Personal data is never returned or logged), *Enforced by* and *How to verify*.** Retention is now enforced by the server: it purges at start-up and every day while it runs. A write lock stops a purge from dropping lines written during it.
  - **Why:** the [first guardrail review](../examples/governed-analytics-mcp/reports/guardrail-review-2026-11-14.md) found GR-04 *Not met*. The purge existed but nothing ran it, so deleting question text depended on someone remembering.
  - **Reports made stale:** that review's GR-04 row. See the [second review](../examples/governed-analytics-mcp/reports/guardrail-review-2026-11-14-2.md).
- **GR-04 (Personal data is never returned or logged), *Retention* and *How to verify*.** Retention now also covers `question_shape` in certification requests.
  - **Why:** `request_certification` stores the user's question in general terms. Even when it's asked for without personal details, it's free text derived from a question, so it gets the same retention as `kit.question` instead of becoming a second, unpurged copy.
  - **Reports made stale:** none.
- **GR-02 (Exploratory SQL is limited to an allow-list), *Enforced by*.** It now says the server executes the SQL regenerated from the checked tree.
  - **Why:** if the server checks one string and runs another, any difference between how sqlglot and DuckDB parse it becomes a bypass. Running the regenerated SQL removes that gap.
  - **Reports made stale:** none.
- **GR-01 (Data access is read-only), *Enforced by*.** It now says the connection also has external file and network access switched off.
  - **Why:** the first GR-01 tests showed that a read-only DuckDB connection still allows `COPY ... TO` a file, `read_csv` and `INSTALL`. That breaks "no tool can create files" as soon as raw SQL is accepted. The requirement is unchanged; the control is stronger.
  - **Reports made stale:** none.
- **GR-04 (Personal data is never returned or logged), *Enforced by*.** It now names the start-up catalogue check and the retention command.
  - **Why:** the earlier wording said "a scheduled job" without naming one. Scheduling the command is a hand-off item for IT.
  - **Reports made stale:** none.
- **GR-03 (Results are capped in rows and time), *Enforced by*.** It used to say the server wraps every query in an outer `LIMIT cap + 1`. It now says the server fetches at most `cap + 1` rows from the cursor and interrupts the query after the timeout.
  - **Why:** an outer `LIMIT` around a subquery doesn't guarantee that the subquery's `ORDER BY` survives. Fetching from the cursor keeps the compiled order exact, which the result hash depends on ([ADR-002](../docs/adr/002-query-receipts.md)). The requirement itself is unchanged: the same cap, timeout and `truncated` flag.
  - **Reports made stale:** none. No guardrail review has been run yet.
