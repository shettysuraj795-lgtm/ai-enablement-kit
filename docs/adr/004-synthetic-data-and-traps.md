# ADR-004: Synthetic data with deliberate traps, modelled in dbt

- **Status:** Accepted, 14 Nov 2026
- **Context:** The case is that two reasonable prompts about "revenue" return different numbers. Clean demo data would hide that, and real data is not available. The data has to make naive queries disagree in ways a BI analyst would recognise, and must be identical on every run so expected answers can be pinned.
- **Decision:** A seeded Python generator (`data/generate.py`, seed `20261114`) writes raw tables to DuckDB and daily FX rates to a dbt seed. dbt then builds staging (one view per raw table), intermediate (refunds and commission per order, listing status as date ranges) and marts. Only `fct_orders` (one row per order), `fct_listings` (one row per listing per day) and `dim_dealers` may be read by metrics, with dealer and category columns denormalised so no metric joins ([ADR-001](001-metric-catalogue.md)).
- **Traps:** Each trap is a choice that the marts settle once and that the data makes visible. On Q3 2026 the same orders give seven readings of revenue (`dbt/analyses/revenue_variants.sql`):

  | Reading | EUR |
  |---|---|
  | Gross merchandise value (governed) | 9,356,569.82 |
  | Net merchandise value (governed) | 8,743,316.38 |
  | Commission revenue (governed) | 436,367.44 |
  | Gross, including failed and pending orders | 10,304,251.48 |
  | Gross, by payment date and payment-date rate | 9,322,587.59 |
  | Net, refunds deducted in the quarter they were made | 8,530,057.77 |
  | Net, as known on 1 Oct 2026, before late refunds | 8,946,655.30 |

  Late refunds (for 30% of refunded orders, the first refund comes 35–120 days after payment) drive the last two rows. Four currencies with daily rates, and FX jumps around the Q3/Q4 boundary, drive the payment-date row. A replayed export loaded 544 listing rows twice, so joining orders to `raw.listings` counts 226 orders twice. `stg_listings` deduplicates, and a source test warns to document it. Commission is capped per order, so take rate differs from the tier rates and has to be a ratio of sums.
- **Expected answers:** Golden eval answers come from hand-written SQL against the marts (`data/golden_answers.py`), never from the compiler, so the evals test the compiler rather than repeat it. A dbt test recomputes monthly order totals from the raw tables and FX seed alone and must match `fct_orders`, so a mart bug cannot become an expected answer.
- **Alternatives:** A public dataset (no currency or refund traps, licence questions); hand-written fixtures (too small to show drift); random data without a fixed seed (answers could not be pinned).
- **Consequences:** Changing the generator changes the golden answers. `golden_answers.py --check` fails until they are regenerated and reviewed. The traps are invented, and real warehouse data will have others. The pattern carries over, the specific traps do not.
