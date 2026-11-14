# Requirements changelog

Every change to a requirement's wording is recorded here, newest first. A change that alters what *Met* means, such as a new limit or a different control, also notes which `guardrail-review` reports it makes stale.

## 14 Nov 2026

- **GR-03 (Results are capped in rows and time), *Enforced by*.** It used to say the server wraps every query in an outer `LIMIT cap + 1`. It now says the server fetches at most `cap + 1` rows from the cursor and interrupts the query after the timeout.
  - **Why:** an outer `LIMIT` around a subquery doesn't guarantee that the subquery's `ORDER BY` survives. Fetching from the cursor keeps the compiled order exact, which the result hash depends on ([ADR-002](../docs/adr/002-query-receipts.md)). The requirement itself is unchanged: the same cap, timeout and `truncated` flag.
  - **Reports made stale:** none. No guardrail review has been run yet.
