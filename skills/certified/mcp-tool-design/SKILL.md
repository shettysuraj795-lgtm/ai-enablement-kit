---
name: mcp-tool-design
description: >-
  Design MCP servers and agent tools that business teams can trust. Use when
  designing, building or reviewing an MCP server, choosing its tools and
  arguments, adding a raw-query escape hatch, or deciding when a prototype
  should be handed off.
metadata:
  version: 0.1.0
  owner: ai-enablement
  requirements: [GR-01, GR-02, GR-03, GR-04, GR-05, GR-06, GR-07, GR-08]
---

# MCP tool design

A tool is an **intent**: something a business user wants done, named in their words. The model chooses the intent and fills in typed arguments. Code then does the rest, deterministically. Every design choice below follows from that split.

## When to use

- Designing a new MCP server or agent for a business team.
- Adding, renaming or widening a tool on an existing server.
- Reviewing a server before a pilot (pair with `guardrail-review`).

## When not to use

- Writing the end-user behaviour for data questions: use `governed-analytics`.
- Finding which problem to solve first: use `use-case-discovery`.
- Writing the runbook and handover documents: use `handoff-pack`.

## Inputs

- The questions users actually ask, in their words. If you have none, run `use-case-discovery` first.
- The governed definitions the tools will serve, such as the [metric catalogue](../../../docs/contracts/metric-catalogue-v0.md).
- The access you have been granted, and who granted it.

## Steps

1. **Name the intents.** Group the users' questions into the smallest set of tools that covers them, each named for what the user wants: `query_metric`, not `run_sql`. Add a `list_…` tool that shows the model what it can ask for, including any glossary of ambiguous terms.
   *Done when:* every tool maps to a sentence a user would say, and the set fits in one table (around five tools).

2. **Type every argument.** Use enums drawn from the catalogue (metric names, allowed dimensions, grains), typed dates and bounded numbers. Resolve relative periods such as "last quarter" on the server, against a recorded as-of date ([receipt contract](../../../docs/contracts/receipt.md)). Accept an optional `question` argument for the trace log only.
   *Done when:* the only free-text arguments are `question` and the escape hatch's SQL.

3. **Compile deterministically.** Code turns the typed arguments into SQL, and the model never writes the SQL on the governed path. Pin the compiler version and order every result.
   *Done when:* a test shows that the same arguments, metric version and compiler version produce byte-identical SQL.

4. **Attach provenance to every result.** Return the metric name, version and description, the resolved time range, the receipt ID and the `certified` or `exploratory` label alongside the rows ([GR-05](../../../requirements/GR-05-receipts.md), [GR-06](../../../requirements/GR-06-certified-vs-exploratory.md)). The server sets the label; the model reports it.
   *Done when:* no data-returning code path skips the receipt.

5. **Write errors as guidance.** An error tells the model what to do next: the valid options, the closest match, and the tool to call instead. Return it as a tool result with `isError: true` so the model can recover.
   *Done when:* every error message names a next step. For example: *"`dealer_name` is not a dimension of `net_merchandise_value`. Allowed: `dealer_region`, `dealer_tier`, `listing_category`, `order_currency`. Call `list_metrics` for details, or `explore_sql` for an exploratory answer."*

6. **Grant least privilege.** Use a read-only connection ([GR-01](../../../requirements/GR-01-read-only-access.md)), curated tables only ([GR-02](../../../requirements/GR-02-query-allow-list.md)), row and time caps ([GR-03](../../../requirements/GR-03-result-caps.md)), and no personal data ([GR-04](../../../requirements/GR-04-pii-protection.md)). Record each choice against its GR ID in the design note.
   *Done when:* every privilege the server holds is justified by a tool, and every applicable GR ID has a named control.

7. **Trace every call.** Wrap the dispatcher, not each tool, so blocked and failed calls are traced too ([GR-07](../../../requirements/GR-07-tracing.md), [trace log contract](../../../docs/contracts/trace-log.md)).
   *Done when:* a test shows one span per call for success, guardrail block and error.

8. **Add a guarded escape hatch.** Users will ask questions no governed definition covers. Offer one raw-query tool (`explore_sql`) so those questions get answered in the open:
   - parse and allow-list the SQL;
   - always label the result `exploratory`;
   - issue a receipt as usual;
   - offer `request_certification` when the result is worth keeping.
   *Done when:* the escape hatch passes the same guardrail tests as the governed path, and its results can never be labelled certified.

9. **Decide the hand-off line.** Write down when this stops being yours (see *Hand-off* below), before anyone depends on it.
   *Done when:* the design note names a receiving team for each item outside the POC.

## Hand-off

A server built with this skill is a proof of concept that a team can run. Hand it off when it needs any of the following:

| Signal | Hand to |
|---|---|
| New credentials, write access, SSO or warehouse roles | IT |
| Use by more than the pilot team, packaging as an organisation-wide connector, versioned releases | Tool enablement |
| Monitoring, alerting, regression evals at scale, LLM-as-judge | ML / data science |
| A new or changed metric definition | BI |

## Output

A short design note next to the server, containing:
- a table of tools, each with its intent sentence, arguments and result shape;
- the GR mapping from step 6;
- the hand-off decisions from step 9.

The server itself follows that note.

## Guardrails

This skill guides design; it enforces nothing. The controls live in the server and its tests, as listed in [`requirements/`](../../../requirements/README.md). When a guardrail blocks something a user needs, change the requirement through its owner, not the server.

## Evals

Planned in `evals/`. The cases will give a design brief to an agent with and without this skill, and check the resulting tool list for:
- intent-named tools;
- typed arguments;
- server-side date resolution;
- provenance on results;
- a labelled escape hatch;
- guidance-style errors.

## Checklist

- [ ] Each tool is an intent a user would say; the set is small
- [ ] Arguments are typed and constrained; relative dates resolved on the server
- [ ] The model chooses, code compiles; same input gives the same SQL
- [ ] Every result has metric, definition, receipt ID and label
- [ ] Every error names the next step
- [ ] Read-only, allow-listed, capped, no PII; each mapped to a GR ID
- [ ] Every call traced, including failures
- [ ] Escape hatch guarded, labelled exploratory, receipted
- [ ] Hand-off owners named
