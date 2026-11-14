# Requirements: hard guardrails

These are the rules the kit enforces in code, not in prompts. Skills may help people follow them, but a requirement only counts when something other than a skill enforces it: the MCP server, the database connection, CI or a test.

Each requirement has an ID, the rule, a rationale, an owner and a way to verify it. The `guardrail-review` skill checks a build against this list and produces an evidence report.

| ID | Requirement | Owner after handover |
|---|---|---|
| [GR-01](GR-01-read-only-access.md) | Data access is read-only | IT |
| [GR-02](GR-02-query-allow-list.md) | Exploratory SQL is limited to an allow-list | BI |
| [GR-03](GR-03-result-caps.md) | Results are capped in rows and time | Tool enablement |
| [GR-04](GR-04-pii-protection.md) | Personal data is never returned or logged | IT (security) |
| [GR-05](GR-05-receipts.md) | Every result has a replayable receipt | BI |
| [GR-06](GR-06-certified-vs-exploratory.md) | Every result is labelled certified or exploratory | BI |
| [GR-07](GR-07-tracing.md) | Every tool call is traced | ML / data science |
| [GR-08](GR-08-metric-change-control.md) | Certified metric definitions are change-controlled | BI |

## Conventions

- **Rule wording.** *MUST* and *MUST NOT* are used as in RFC 2119.
- **Owner.** The team accountable after handover. Until then, the kit maintainer owns every requirement.
- **Tests.** Each guardrail test carries a pytest marker with its ID, so `pytest -m gr03` runs the evidence for GR-03.
- **Changes.** IDs are never reused. A retired requirement keeps its file and is marked *Retired*.
