# Synthetic marketplace data

`generate.py` writes a synthetic watch marketplace into `warehouse.duckdb` (schema `raw`) and the daily FX reference rates into `../dbt/seeds/fx_rates.csv`. The random seed is fixed, so every run produces the same data. The warehouse file is not committed; the FX seed is.

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python generate.py
```

| Table | Grain |
|---|---|
| `raw.dealers` | One row per dealer (150), with country and subscription tier |
| `raw.watch_models` | One row per watch model (48, fictional brands) |
| `raw.listings` | One row per listing **per load**: some listings were loaded twice |
| `raw.listing_status_changes` | One row per status change: `active`, `paused`, `sold`, `withdrawn` |
| `raw.orders` | One row per order: `paid`, `failed` or `pending` |
| `raw.refunds` | One row per refund, in the order's currency; an order can have several |
| `raw.commissions` | Ledger of commission charged (`charge`) and returned on refunds (`refund`) |

Orders run from late 2024 to 13 Nov 2026, the last complete day before the example's evaluation date of 14 Nov 2026.

The data deliberately contains traps that make naive queries disagree: late refunds, four currencies with daily rates, and duplicate listing loads. See [ADR-004](../../../docs/adr/004-synthetic-data-and-traps.md).
