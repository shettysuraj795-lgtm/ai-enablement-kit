# AI Enablement Kit

A reusable kit for helping non-technical teams adopt AI assistants without losing trust in the results: agent skills, hard guardrails, contribution rules and architecture decision records. It is demonstrated on one worked example, **self-serve analytics drift**.

> **Status:** work in progress. Phase 0: repository structure, guardrails and data contracts.

## The problem the example tackles

Once an assistant can query the data warehouse directly, business teams stop waiting for BI and build their own analysis. That is much faster, but the numbers start to drift:

- two similar questions return different figures, so nothing is reproducible;
- charts are sent back to BI to be double-checked, which adds load without adding trust;
- unverified numbers reach decisions.

The kit treats this as a governance and enablement problem, not a prompting problem.

## Principles

- **Same question, same number.** The assistant selects from governed metric definitions, and code compiles them into SQL deterministically. Lowering the temperature does not give you reproducibility.
- **Soft guardrails are not hard guardrails.** Skills describe how people and the assistant should work, and are followed probabilistically. The server and the tests enforce the rules in [`requirements/`](requirements/).
- **One governance pattern, used twice.** Metrics are certified or exploratory. Skills are certified or community. An open skills library drifts the same way self-serve analytics does unless it is governed the same way.
- **BI as partner, not gatekeeper.** BI owns the metric definitions rather than every dashboard, and the system suggests candidates for them to certify.

## Repository layout

| Path | What lives there |
|---|---|
| [`skills/`](skills/) | Agent skills, split into certified and community tiers |
| [`requirements/`](requirements/) | Hard guardrails (`GR-xx`), each with an owner and a way to verify it |
| [`docs/contracts/`](docs/contracts/) | Data formats every component codes against |
| [`docs/adr/`](docs/adr/) | Short architecture decision records |
| [`templates/`](templates/) | Starting points, such as the skill template |
| [`examples/governed-analytics-mcp/`](examples/governed-analytics-mcp/) | The worked example: governed metrics served over MCP |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How skills are contributed and promoted |

## Built / Deliberately not built / Who it hands off to

### Built

- Repository structure, contribution tiers and skill template
- Hard guardrails GR-01 to GR-08
- Contracts: metric definition, query receipt, trace log
- *Planned:* skills library, synthetic data with dbt models and tests, metric compiler, MCP server, receipts with replay, evals in CI, guardrail evidence report, handover plan

### Deliberately not built

- **A production semantic layer.** A small YAML metric catalogue shows the principle with less overhead ([ADR-001](docs/adr/001-metric-catalogue.md)).
- **Hosted tracing.** A JSON trace log with OpenTelemetry field names, queried in DuckDB ([ADR-003](docs/adr/003-trace-log.md)).
- **A review UI.** A replay command proves the point; a UI would only polish it.
- **Warehouse-level access control and SSO.** The example uses a read-only connection and server-side checks.
- **User research.** Personas are synthetic and labelled as assumptions.

### Who it hands off to

| Team | Takes on |
|---|---|
| BI | Metric definitions, certification and the promotion queue |
| ML / data science | Evals as regression tests, monitoring, LLM-as-judge |
| Tool enablement | Packaging the MCP server as an organisation-wide connector; distributing certified skills |
| IT | Warehouse roles, SSO, network and security controls |

## Assumptions

Synthetic data, an assumed stack (DuckDB, dbt, an MCP server used from Claude Desktop) and invented personas. Each assumption is stated where it matters.
