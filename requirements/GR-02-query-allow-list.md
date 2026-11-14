# GR-02: Exploratory SQL is limited to an allow-list

- **ID:** GR-02
- **Requirement:** Exploratory SQL MUST be a single `SELECT` statement that reads only from approved mart tables. It MUST NOT read raw or staging tables, call functions that read files or the network, or contain more than one statement.
- **Rationale:** Marts are tested and documented; raw tables are where the traps live. Limiting exploration to marts keeps exploratory answers close to the certified ones.
- **Owner:** BI (the approved table list). Until handover: kit maintainer.
- **Enforced by:** The `explore_sql` tool parses every query into a syntax tree with sqlglot and checks it against the allow-list before execution. Regular expressions are not used.
- **How to verify:** `pytest -m gr02` runs a table of allowed and blocked queries, including CTE and subquery tricks, `read_csv`, `read_parquet`, stacked statements and comments that hide keywords, and asserts each outcome. Blocked queries must appear in the trace log with `kit.guardrail.hits` containing `GR-02`.
