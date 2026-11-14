# ADR-005: Golden answers from independent reference SQL

- **Status:** Accepted, 14 Nov 2026
- **Context:** Evals must show that the same question gets the same, correct number. If expected answers came from the metric compiler, the evals would only prove the compiler agrees with itself. If they were typed in by hand, they would go stale whenever the data changed.
- **Decision:** Each golden question carries hand-written reference SQL that is written without the compiler. A script runs it against the dbt marts and writes the expected result, and CI fails if a stored result is out of date ([contract](../contracts/golden-questions.md)). Answer-text checks are deterministic matches on metric names.
- **Alternatives:** Expected answers from the compiler (circular); hand-typed numbers (stale); LLM-as-judge for answer text (more flexible, but adds cost and nondeterminism to CI).
- **Consequences:** A wrong compiler and a wrong reference query would have to make the same mistake for an error to slip through. Data changes appear as reviewed diffs. The skill has to name metrics exactly, which also helps users. LLM-as-judge is a handover item for the ML team.
