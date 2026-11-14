# ADR-007: Exploratory SQL with a parser allow-list on a locked-down connection

- **Status:** Accepted, 14 Nov 2026
- **Context:** Some questions have no governed metric. If the assistant can't answer them, people go back to querying the warehouse with no controls at all. Raw SQL from a model has to be contained without relying on the prompt.
- **Decision:** `explore_sql` has two independent layers.
  1. A sqlglot allow-list on the parsed tree (GR-02, GR-04): one `SELECT` over `marts.*` or its own CTEs, no table functions or file, environment or SQL-string functions, no personal-data columns, no whole-row references, and no `*` over a table that has PII. The server then executes **the SQL regenerated from the checked tree**, so what runs is exactly what was checked.
  2. A connection that is read-only with external access switched off (GR-01). The tests found that read-only alone still allows `COPY ... TO`.

  Results are always labelled exploratory and receipted, so they can be found and promoted later.
- **Alternatives:** Regex or keyword filters (easy to bypass with comments and casing); connection limits alone (would let the assistant query raw tables and PII); an allow-list of functions (safer, but blocks ordinary analysis, so we used a blocklist of dangerous families instead); no escape hatch (pushes people to ungoverned tools).
- **Consequences:** Each layer holds if the other has a gap, and both have GR-tagged tests. The function blocklist must grow when DuckDB adds file-reading functions; the connection layer backstops that. Aggregates over PII, such as a distinct buyer count, are blocked too, so they need a governed metric.
