# Contract: metric definition

- **Version:** 1.0
- **Format:** YAML, one file per metric, at `examples/governed-analytics-mcp/metrics/<name>.yml`
- **Written by:** BI (certified metrics), anyone (uncertified drafts)
- **Read by:** the metric compiler, the MCP server, the CI validator ([GR-08](../../requirements/GR-08-metric-change-control.md))
- **Decision record:** [ADR-001](../adr/001-metric-catalogue.md)

A metric definition is the only place a number's meaning is decided. The assistant picks a metric by name; the compiler turns the definition plus a request into SQL. Business logic such as refunds or currency conversion belongs in the dbt mart the metric reads from, where it is tested. The definition stays a thin, reviewable layer on top.

## Fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `name` | string, `snake_case` | yes | Unique ID. Never reused, even after a metric is retired. |
| `description` | string | yes | Plain-English definition, including the choices a reader could get wrong (what is included, which date, which currency). Shown to the user with every result. |
| `model` | string | yes | The dbt model the metric reads from, by model name (for example `fct_orders`). Must be a mart, not a staging or raw model. |
| `expression` | string | yes | One SQL expression built from aggregates over columns of `model`, for example `sum(net_amount_eur)` or `sum(refund_amount_eur) / nullif(sum(gross_amount_eur), 0)`. No subqueries, no joins. |
| `time_dimension` | string | yes | The date or timestamp column that time grains and time ranges apply to. |
| `time_grains` | list | yes | Allowed grains, chosen from `day`, `week`, `month`, `quarter`, `year`. Weeks start on Monday; quarters are calendar quarters. |
| `allowed_dimensions` | list of strings | yes (may be empty) | Columns of `model` the metric may be grouped or filtered by. Must not include columns flagged as PII ([GR-04](../../requirements/GR-04-pii-protection.md)). |
| `filters` | list of filters | yes (may be empty) | Conditions that are always applied and that the user cannot remove. See *Filter shape*. |
| `unit` | string | yes | What the number is measured in, for example `EUR`, `count` or `ratio`. |
| `version` | string, semver | yes | See *Versioning*. |
| `owner` | string | yes | The team or role accountable for the definition. |
| `certified` | boolean | yes | `true` only after the owner has approved it and a golden eval covers it. Decides the result label ([GR-06](../../requirements/GR-06-certified-vs-exploratory.md)). |

Columns are not joined in from other models. If a metric needs a dimension from another table, the dbt mart provides it as a column. This keeps the compiler simple and puts every join under dbt's tests.

### Filter shape

The same shape is used for fixed filters here and for user filters in a request ([receipt contract](receipt.md)):

```yaml
- column: dealer_region   # must be in allowed_dimensions (user filters) or on the model (fixed filters)
  op: in                  # one of: =, !=, <, <=, >, >=, in, not_in, is_null, is_not_null
  value: [DE, AT, CH]     # scalar, list for in/not_in, omitted for is_null/is_not_null
```

Filters are structured data, not SQL strings, so the compiler can validate them and render them the same way every time.

## Versioning

| Change | Bump |
|---|---|
| `model`, `expression`, `time_dimension` or `filters` (anything that can change the number for the same request) | major |
| Adding to `allowed_dimensions` or `time_grains` | minor |
| Removing from `allowed_dimensions` or `time_grains` | major |
| `description`, `owner` or `unit` wording only | patch |

CI enforces the major bump ([GR-08](../../requirements/GR-08-metric-change-control.md)). Old versions remain in git history so a receipt can be replayed against the definition it was compiled from.

## Validation rules

A definition is rejected if:

- any required field is missing or has the wrong type;
- `model` is not a mart in the dbt manifest, or any referenced column does not exist on it;
- `expression` does not parse as a single expression in which every column reference sits inside an aggregate;
- `allowed_dimensions` contains a PII column;
- `certified: true` and no golden eval question references the metric.

## Worked example: `net_revenue`

*Revenue* is ambiguous in the example data. It can be gross or net of refunds, and foreign-currency orders can be converted at the rate on the order date or on the payment date. This definition settles both choices once:

```yaml
name: net_revenue
description: >-
  Value of paid orders minus refunds, in EUR. Refunds are attributed to the
  original order's date, not the refund date, so a past quarter's figure can
  fall as late refunds arrive; the receipt's data snapshot pins the figure you
  saw. Non-EUR orders are converted at the reference rate on the order date.
model: fct_orders
expression: sum(net_amount_eur)
time_dimension: order_date
time_grains: [day, week, month, quarter, year]
allowed_dimensions: [dealer_region, dealer_tier, listing_category, order_currency]
filters:
  - column: is_paid
    op: "="
    value: true
unit: EUR
version: 1.0.0
owner: bi-finance
certified: true
```

The full set of metrics, and the mart columns they need, is in the [metric catalogue v0](metric-catalogue-v0.md). `net_amount_eur` is computed and tested in dbt.
