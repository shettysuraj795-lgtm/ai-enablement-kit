# ADR-001: Own YAML metric catalogue on top of dbt marts

- **Status:** Accepted, 14 Nov 2026
- **Context:** Reproducible numbers need one governed definition per metric that code, not the assistant, turns into SQL. dbt's semantic layer (MetricFlow) does this, but brings its own modelling concepts and setup cost.
- **Decision:** Keep a small YAML catalogue, one file per metric ([contract](../contracts/metric-definition.md)), where each metric is an aggregate over a single dbt mart with structured filters, a semantic version, an owner and a certified flag. Business logic and joins stay in dbt, where they are tested.
- **Alternatives:** MetricFlow (the production path, deferred); metric definitions in a prompt or skill (not enforceable, so it drifts).
- **Consequences:** The compiler stays small enough to test exhaustively. Every new dimension needs a mart column, which pushes modelling work to dbt. Moving to MetricFlow or BI's semantic layer later maps one-to-one: `model` becomes a semantic model and `expression` a measure.
