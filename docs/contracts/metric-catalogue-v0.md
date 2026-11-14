# Contract: metric catalogue v0

- **Version:** 0 (the first set of metrics for the worked example)
- **Format:** each metric below becomes one file in `examples/governed-analytics-mcp/metrics/`, following the [metric definition contract](metric-definition.md)
- **Read by:** the dbt models (which must provide the columns listed under *Mart columns*), the compiler, the golden eval questions

This catalogue fixes which metrics exist and what the marts must provide for them. The metrics come first and the columns are derived from them, so nothing appears in a mart unless a metric or a guardrail needs it.

## Metrics

| Metric | Question it answers | Finance analyst | Sales/Ops lead | Model | Certified |
|---|---|---|---|---|---|
| `gross_merchandise_value` | How much was sold? | ✓ | ✓ | `fct_orders` | yes |
| `net_merchandise_value` | How much was sold, after refunds? | ✓ | | `fct_orders` | yes |
| `refund_rate` | What share of sales was refunded? | ✓ | | `fct_orders` | yes |
| `commission_revenue` | How much commission did the marketplace earn, after refunds? | ✓ | | `fct_orders` | yes |
| `take_rate` | What share of sales did the marketplace charge as commission? | ✓ | | `fct_orders` | yes |
| `paid_orders` | How many orders were paid? | | ✓ | `fct_orders` | yes |
| `active_listings` | How many listings were live? | | ✓ | `fct_listings` | no |

Ratios are always a ratio of sums over the period, never an average of per-order ratios.

`active_listings` is uncertified on purpose. Whether it should count listings active on *any* day of the period or on the *last* day has not been signed off. Until it is, its results are labelled exploratory ([GR-06](../../requirements/GR-06-certified-vs-exploratory.md)), which also gives the demo a governed but uncertified metric.

### Definitions

```yaml
name: gross_merchandise_value
description: >-
  Value of paid orders before refunds, in EUR. Non-EUR orders are converted at
  the reference rate on the order date.
model: fct_orders
expression: sum(gross_amount_eur)
time_dimension: order_date
time_grains: [day, week, month, quarter, year]
allowed_dimensions: [dealer_id, dealer_region, dealer_tier, listing_category, order_currency]
filters:
  - {column: is_paid, op: "=", value: true}
unit: EUR
version: 1.0.0
owner: bi-finance
certified: true
```

```yaml
name: net_merchandise_value
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
  - {column: is_paid, op: "=", value: true}
unit: EUR
version: 1.0.0
owner: bi-finance
certified: true
```

```yaml
name: refund_rate
description: >-
  Refunded value as a share of gross merchandise value, for paid orders.
  Refunds are attributed to the original order's date, so recent periods
  rise as refunds arrive.
model: fct_orders
expression: sum(refund_amount_eur) / nullif(sum(gross_amount_eur), 0)
time_dimension: order_date
time_grains: [week, month, quarter, year]
allowed_dimensions: [dealer_region, dealer_tier, listing_category, order_currency]
filters:
  - {column: is_paid, op: "=", value: true}
unit: ratio
version: 1.0.0
owner: bi-finance
certified: true
```

```yaml
name: take_rate
description: >-
  Commission charged to dealers as a share of gross merchandise value, for
  paid orders, before any commission is refunded. For commission earned after
  refunds, use commission_revenue.
model: fct_orders
expression: sum(commission_eur) / nullif(sum(gross_amount_eur), 0)
time_dimension: order_date
time_grains: [month, quarter, year]
allowed_dimensions: [dealer_region, dealer_tier, listing_category]
filters:
  - {column: is_paid, op: "=", value: true}
unit: ratio
version: 1.0.0
owner: bi-finance
certified: true
```

```yaml
name: commission_revenue
description: >-
  Commission charged to dealers on paid orders, minus commission refunded to
  dealers when orders are refunded, in EUR. This is the marketplace's own
  revenue. Refunded commission is attributed to the original order's date, so
  a past period's figure can fall as late refunds arrive. Non-EUR orders are
  converted at the reference rate on the order date.
model: fct_orders
expression: sum(net_commission_eur)
time_dimension: order_date
time_grains: [day, week, month, quarter, year]
allowed_dimensions: [dealer_region, dealer_tier, listing_category, order_currency]
filters:
  - {column: is_paid, op: "=", value: true}
unit: EUR
version: 1.0.0
owner: bi-finance
certified: true
```

```yaml
name: paid_orders
description: >-
  Number of paid orders, counted on the order date. Refunded orders still
  count; use refund_rate for refunds.
model: fct_orders
expression: count(order_id)
time_dimension: order_date
time_grains: [day, week, month, quarter, year]
allowed_dimensions: [dealer_id, dealer_region, dealer_tier, listing_category, order_currency]
filters:
  - {column: is_paid, op: "=", value: true}
unit: count
version: 1.0.0
owner: bi-sales
certified: true
```

```yaml
name: active_listings
description: >-
  Number of distinct listings that were active on at least one day in the
  period. Not certified: "active on the last day of the period" is the
  alternative under review.
model: fct_listings
expression: count(DISTINCT listing_id)
time_dimension: snapshot_date
time_grains: [day, week, month]
allowed_dimensions: [dealer_id, dealer_region, dealer_tier, listing_category]
filters:
  - {column: is_active, op: "=", value: true}
unit: count
version: 0.1.0
owner: bi-sales
certified: false
```

## Mart columns

Both marts live in the `marts` schema. Dealer columns are denormalised from `dim_dealers` so that no metric needs a join ([ADR-001](../adr/001-metric-catalogue.md)). Dealers are businesses, so `dealer_id` is not treated as personal data; this is an assumption for the example.

### `fct_orders`: one row per order

| Column | Type | Meaning | dbt tests |
|---|---|---|---|
| `order_id` | varchar | Primary key | `unique`, `not_null` |
| `order_date` | date | Date the order was placed. The time dimension for every order metric. | `not_null` |
| `paid_at` | timestamp | When payment cleared; `null` if unpaid. No metric uses it. It is the alternative date that makes revenue ambiguous. | |
| `is_paid` | boolean | Payment cleared | `not_null` |
| `buyer_id` | varchar | Buyer. `meta: {pii: true}` ([GR-04](../../requirements/GR-04-pii-protection.md)). | `not_null` |
| `dealer_id` | varchar | Selling dealer | `not_null`, `relationships` to `dim_dealers` |
| `dealer_region` | varchar | Dealer's region | `accepted_values` |
| `dealer_tier` | varchar | Dealer's subscription tier | `accepted_values` |
| `listing_id` | varchar | Listing the order came from | `relationships` to `fct_listings` |
| `listing_category` | varchar | Category of the listed item | `accepted_values` |
| `order_currency` | varchar(3) | Currency the buyer paid in | `accepted_values`: EUR, USD, GBP, CHF |
| `original_amount` | decimal(18,2) | Order value in `order_currency` | `not_null`, ≥ 0 |
| `fx_rate` | decimal(18,6) | EUR per unit of `order_currency`, from the FX seed | `not_null`; `= 1` when currency is EUR |
| `fx_rate_date` | date | Date of the rate used | `= order_date` |
| `gross_amount_eur` | decimal(18,2) | `round(original_amount * fx_rate, 2)` | expression test |
| `refund_amount_eur` | decimal(18,2) | All refunds on the order, converted at the same `fx_rate`; 0 if none | between 0 and `gross_amount_eur` |
| `net_amount_eur` | decimal(18,2) | `gross_amount_eur - refund_amount_eur` | expression test |
| `commission_eur` | decimal(18,2) | Commission charged to the dealer, converted at `fx_rate` | between 0 and `gross_amount_eur` |
| `commission_refunded_eur` | decimal(18,2) | Commission returned to the dealer on refunds, converted at the same `fx_rate`; 0 if none | between 0 and `commission_eur` |
| `net_commission_eur` | decimal(18,2) | `commission_eur - commission_refunded_eur` | expression test |

Refunds and refunded commission are converted at the order's rate, not the refund date's rate, so `net_amount_eur` and `net_commission_eur` never move with exchange rates after the order ([ADR-001](../adr/001-metric-catalogue.md)). The raw data deliberately includes refunds in a different month from their order, and rates that move between `order_date` and `paid_at`, so both choices are visible in the numbers.

### `fct_listings`: one row per listing per day

| Column | Type | Meaning | dbt tests |
|---|---|---|---|
| `listing_id` | varchar | Listing | `not_null` |
| `snapshot_date` | date | Day the row describes | `not_null`; unique together with `listing_id` |
| `is_active` | boolean | Listing was live and purchasable on that day | `not_null` |
| `dealer_id` | varchar | Listing dealer | `relationships` to `dim_dealers` |
| `dealer_region` | varchar | Dealer's region | `accepted_values` |
| `dealer_tier` | varchar | Dealer's subscription tier | `accepted_values` |
| `listing_category` | varchar | Category of the listed item | `accepted_values` |
