---
name: governed-analytics
description: >-
  Answer business data questions (revenue, sales, orders, refunds, commission,
  listings) with governed metrics, so the same question always gets the same
  number. Use whenever someone asks for a figure, a trend or a breakdown from
  company data and the governed-analytics tools are connected.
metadata:
  version: 0.2.0
  owner: ai-enablement
  requirements: [GR-02, GR-04, GR-05, GR-06]
---

# Governed analytics

Every number you give comes with its **provenance**: the metric it came from, whether that metric is certified, and a reference that lets BI reproduce it. A number without a reference is an opinion.

## When to use

- Someone asks for a business figure, a comparison over time or a breakdown, such as "What was revenue last quarter?" or "Orders by region last month".
- Someone asks what a metric means, or which metric to use.

## When not to use

- The question is about building or changing the tools: use `mcp-tool-design`.
- The governed-analytics tools are not connected. Say so; don't estimate figures from memory.

## Inputs

- The question, in the user's words.
- The tools `list_metrics`, `describe_metric`, `query_metric`, `explore_sql` and `request_certification`.

## Steps

1. **Find the metric.** Call `list_metrics`. If the question uses an everyday word that could mean several things ("revenue", "sales", "commission"), call `list_metrics` with that `term`. Its `summary` line counts the certified and uncertified metrics; describe a metric as certified only if its own `certified` field says so.
   *Done when:* you have exactly one candidate metric, several, or none.

2. **Settle ambiguity in the open.** With several candidates, check whether the question already settles it ("revenue *after refunds*" means `net_merchandise_value`).
   - If it does, choose that metric and plan to say why.
   - If it doesn't, list the options with their one-line meanings and ask the user which one they mean. Don't pick silently, and don't answer all of them unasked.
   *Done when:* one metric is chosen and you can say why, or the user has been asked.

3. **Query the governed metric.** Call `query_metric`. Use `period` for relative dates ("last quarter"); the server resolves it. Pass the user's question as `question`.
   If the call returns an error, follow its guidance (it names the valid options) and try again once. If it still fails, tell the user what is not available.
   *Done when:* you have a result with a `receipt_id`.

4. **Explore only when nothing fits.** If no governed metric answers the question, say so first, then use `explore_sql` with a single `SELECT` over the marts listed in its description.
   *Done when:* you have an exploratory result with a `receipt_id`, or a clear statement that the data isn't available.

5. **Report with provenance.** Every answer states:
   - the figure and the resolved time range;
   - the metric name and version, for example "net_merchandise_value v1.0.0", or "exploratory query";
   - the label, **certified** or **exploratory**, exactly as the tool returned it;
   - the reference, once, as the answer's last line: `Reference for BI: <receipt_id>`.

   With several results in one answer, number them and list the references in a footnote. Never put references in a table column.

   For a relative period, say it was worked out as of `period_worked_out_as_of`. That date is when "last quarter" was calculated, not the date of the data; don't call it the data date. Mention `data_snapshot` only if the user asks how current the data is.

   For an exploratory result, add that it isn't a certified figure, and offer to request certification. If the user accepts, call `request_certification` with the receipt ID and the question in general terms, with no names or personal details.
   *Done when:* the answer contains all four items with the reference last and only once, and an exploratory answer contains the offer.

## Output

> **Net merchandise value, Q3 2026 (1 Jul – 30 Sep): €8,743,316.38.**
> Metric: `net_merchandise_value` v1.0.0, *certified*: paid orders minus refunds, in EUR at the order-date rate. "Last quarter" was worked out as of 14 Nov 2026.
>
> Reference for BI: `rcpt_01M7DP8P3J9WFN3CY9B8B0EJ6R`

> | Metric (all *certified*, Q3 2026) | Value |
> |---|---|
> | Gross merchandise value¹ | €9,356,569.82 |
> | Net merchandise value² | €8,743,316.38 |
>
> ¹ Reference for BI: `rcpt_…`  ² Reference for BI: `rcpt_…`

> I couldn't find a governed metric for time-to-sell, so this is an **exploratory** result: listings sold in about 23 days on average. It isn't certified. Shall I ask BI to certify a metric for it?
>
> Reference for BI: `rcpt_…`

## Guardrails

The server enforces these whether or not this skill is followed:
- the certified or exploratory label ([GR-06](../../../requirements/GR-06-certified-vs-exploratory.md));
- the receipt ([GR-05](../../../requirements/GR-05-receipts.md));
- the SQL allow-list ([GR-02](../../../requirements/GR-02-query-allow-list.md));
- personal data ([GR-04](../../../requirements/GR-04-pii-protection.md)).

This skill covers what the server can't enforce: asking about ambiguous terms, naming the metric, quoting the label and reference, and offering certification. Never relabel a result, and never round a figure into a different one.

## Evals

This is a behaviour skill. Its cases are the golden questions' `needs-model` checks (GQ-03, GQ-04, GQ-10, GQ-15) plus a run without this skill for comparison. They're planned once model-in-the-loop evals are enabled; until then the skill can't be promoted.
