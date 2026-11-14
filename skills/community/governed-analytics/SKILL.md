---
name: governed-analytics
description: >-
  Answer business data questions (revenue, sales, orders, refunds, commission,
  listings) with governed metrics, so the same question always gets the same
  number. Use whenever someone asks for a figure, a trend or a breakdown from
  company data and the governed-analytics tools are connected.
metadata:
  version: 0.1.0
  owner: ai-enablement
  requirements: [GR-02, GR-04, GR-05, GR-06]
---

# Governed analytics

Every number you give comes with its **receipt**: the metric it came from, whether that metric is certified, and the receipt ID that lets BI reproduce it. A number without a receipt is an opinion.

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

1. **Find the metric.** Call `list_metrics`. If the question uses an everyday word that could mean several things ("revenue", "sales", "commission"), call `list_metrics` with that `term`.
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

5. **Report with the receipt.** Every answer states:
   - the figure and the resolved time range;
   - the metric name and version, for example "net_merchandise_value v1.0.0", or "exploratory query";
   - the label, **certified** or **exploratory**, exactly as the tool returned it;
   - the receipt ID.

   For an exploratory result, add that it isn't a certified figure, and offer to request certification. If the user accepts, call `request_certification` with the receipt ID and the question in general terms, with no names or personal details.
   *Done when:* the answer contains all four items, and an exploratory answer contains the offer.

## Output

> **Net merchandise value, Q3 2026 (1 Jul – 30 Sep): €8,743,316.38.**
> Metric: `net_merchandise_value` v1.0.0, *certified*: paid orders minus refunds, in EUR at the order-date rate.
> Receipt: `rcpt_01M7DP8P3J9WFN3CY9B8B0EJ6R`. BI can replay this exact figure.

> I couldn't find a governed metric for time-to-sell, so this is an **exploratory** result: listings sold in about 23 days on average (receipt `rcpt_…`). It isn't certified. Shall I ask BI to certify a metric for it?

## Guardrails

The server enforces these whether or not this skill is followed:
- the certified or exploratory label ([GR-06](../../../requirements/GR-06-certified-vs-exploratory.md));
- the receipt ([GR-05](../../../requirements/GR-05-receipts.md));
- the SQL allow-list ([GR-02](../../../requirements/GR-02-query-allow-list.md));
- personal data ([GR-04](../../../requirements/GR-04-pii-protection.md)).

This skill covers what the server can't enforce: asking about ambiguous terms, naming the metric, quoting the label and receipt, and offering certification. Never relabel a result, and never round a figure into a different one.

## Evals

This is a behaviour skill. Its cases are the golden questions' `needs-model` checks (GQ-03, GQ-04, GQ-10, GQ-15) plus a run without this skill for comparison. They're planned once model-in-the-loop evals are enabled; until then the skill can't be promoted.
