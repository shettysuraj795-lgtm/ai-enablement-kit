# ADR-003: JSON trace log with OpenTelemetry field names

- **Status:** Accepted, 14 Nov 2026
- **Context:** Rollout metrics, guardrail evidence and promotion candidates all need a record of every tool call. In a desktop assistant the model runs on the client, so the MCP server only ever sees tool calls, not prompts or completions.
- **Decision:** Write one OpenTelemetry-shaped span per tool call to a JSON Lines file ([contract](../contracts/trace-log.md)), using standard semantic-convention names where they exist and a `kit.*` namespace otherwise. Query it with DuckDB.
- **Alternatives:** Hosted LLM tracing such as Phoenix or Langfuse (built for prompt and completion traces the server cannot see, and more to run); plain unstructured logs (cannot be queried or exported).
- **Consequences:** No extra infrastructure, and the analysis is ordinary SQL. Handing over to the ML team's monitoring stack means adding an OTLP exporter, not reshaping data. Upstream GenAI and MCP conventions are still in development, so names are pinned per contract version.
