# Contract: golden questions

- **Version:** 0.1 (matches `format_version` in the file)
- **Format:** YAML, one file at `examples/governed-analytics-mcp/evals/golden_questions.yml`
- **Written by:** people (questions, intents, reference SQL); `data/golden_answers.py` (every `result`)
- **Read by:** the eval harness in CI, the with/without-skill comparison
- **Decision record:** [ADR-005](../adr/005-golden-questions.md)

A golden question is a question a persona would really ask, together with what a correct answer looks like. Expected results are never typed in by hand. People write a reference SQL query for each answer independently of the metric compiler, and a script runs it against the dbt marts. The eval then checks the compiler against an independent reading of the definition, not against itself.

## File fields

| Field | Meaning |
|---|---|
| `format_version` | Version of this contract, `'0.1'`. |
| `as_of` | The date every relative period is resolved against. Evals run with the server's as-of date pinned to it. |
| `data` | `generator_seed` and `snapshot_end_date` of the synthetic data the results were computed from. A different seed means different results. |
| `questions` | The list of questions below. |

## Question fields

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | `GQ-nn`. Never reused, even after a question is removed. |
| `persona` | yes | A role, for example `finance_analyst` or `sales_ops_lead`. Matches `kit.persona` in the [trace log](trace-log.md). |
| `question` | yes | The question as the persona would type it. Free of personal data ([GR-04](../../requirements/GR-04-pii-protection.md)). |
| `kind` | yes | `metric`, `ambiguous` or `uncovered`. See *Pass rules*. |
| `term` | for `ambiguous` | The [glossary](metric-catalogue-v0.md#glossary) term the question uses. Optional on `metric` questions that use a term but settle it. |
| `expected` | yes | Shape depends on `kind`; see below. |

### Expected answer

An expected answer is used directly by `metric` questions and as each item in an `ambiguous` question's `options`.

| Field | Meaning |
|---|---|
| `classification` | `certified` or `exploratory`, as [GR-06](../../requirements/GR-06-certified-vs-exploratory.md) would label it. |
| `intent` | The structured intent the tool call must carry, in the [receipt intent](receipt.md#intent) shape, including `time_range.as_of` and `relative`. |
| `reference_sql` | Hand-written SQL over the marts that answers the question. It is never produced by the compiler. |
| `tolerance` | Absolute tolerance for numeric comparison. `0` for amounts and counts; `1.0e-06` for ratios. |
| `result` | `columns` and `rows`, written by the script. Rendered as in the receipt's [canonical result](receipt.md#result-hash): decimals at their scale, ratios to 6 places, dates in ISO 8601, `period` as the date the period starts. Rows are ordered by period, then dimensions. |

`metric` questions may add `must_name_metric: true`. `ambiguous` questions use `pass_if: lists_options_or_names_choice` and a list of `options`. `uncovered` questions use `{classification: exploratory, offers_certification_request: true}`.

## Pass rules

| Kind | Passes when |
|---|---|
| `metric` | The tool call's `intent` equals `expected.intent` (dimension and filter order ignored), the result matches `expected.result` within `tolerance`, and the label equals `classification`. With `must_name_metric`, the answer text also contains the metric's name. |
| `ambiguous` | Either the answer text names every option's metric and asks the user to choose, or the answer names one option's metric and its tool call and result pass that option as a `metric` question would. |
| `uncovered` | The result is labelled `exploratory` and the answer offers to request certification, or the assistant calls `request_certification`. |

Text checks are deterministic: they look for metric names in the answer, so the `governed-analytics` skill has the assistant name metrics exactly. Grading with an LLM-as-judge is a handover item for the ML team.

## Keeping results current

- `python data/golden_answers.py` recomputes every `result` from the marts.
- `python data/golden_answers.py --check` runs in CI and fails if a stored result no longer matches the data. A data change that moves an answer then shows up as a reviewed diff, not a silent eval failure.
- The `relative` period names (`last_quarter`, `last_month`, `last_4_weeks`, `year_to_date`) are drafts until the compiler fixes its vocabulary. When it does, this contract moves to 1.0.

## Worked example: `net_merchandise_value`

```yaml
- id: GQ-02
  persona: finance_analyst
  question: What was net merchandise value last quarter?
  kind: metric
  expected:
    classification: certified
    intent:
      metric: net_merchandise_value
      dimensions: []
      filters: []
      time_grain: quarter
      time_range: {start: '2026-07-01', end: '2026-10-01', as_of: '2026-11-14', relative: last_quarter}
    reference_sql: |-
      SELECT date_trunc('quarter', order_date) AS period, sum(net_amount_eur) AS net_merchandise_value
      FROM marts.fct_orders
      WHERE is_paid = TRUE AND order_date >= DATE '2026-07-01' AND order_date < DATE '2026-10-01'
      GROUP BY period ORDER BY period
    tolerance: 0
    result:
      columns: [period, net_merchandise_value]
      rows:
      - ['2026-07-01', '8743316.38']
```

The ambiguous counterpart, GQ-03 ("What was revenue last quarter?"), lists `gross_merchandise_value`, `net_merchandise_value` and `commission_revenue` as `options`, each in this same shape.
