# dbt project

Turns the raw synthetic data into the marts that the metric catalogue reads from ([metric catalogue v0](../../../docs/contracts/metric-catalogue-v0.md)).

```sh
cd dbt
../data/.venv/bin/python ../data/generate.py   # raw data and FX seed
../data/.venv/bin/dbt build                    # seed, models and tests
../data/.venv/bin/dbt docs generate && ../data/.venv/bin/dbt docs serve   # lineage graph
```

`profiles.yml` lives here and points at `../data/warehouse.duckdb`; set `WAREHOUSE_PATH` to use another file.

| Layer | Schema | What it does |
|---|---|---|
| `seeds/fx_rates.csv` | `seeds` | Daily EUR-per-unit reference rates for EUR, USD, GBP and CHF |
| `models/staging/` | `staging` | One view per raw table: renames, casts, and removes duplicate listing loads |
| `models/intermediate/` | `intermediate` | Refunds and commission per order; listing status as date ranges |
| `models/marts/` | `marts` | `fct_orders`, `fct_listings`, `dim_dealers`: the only models metrics may read |

Every column and test listed in the contract is in `models/marts/_marts.yml`. Two small generic tests (`expression_is_true`, `unique_combination_of_columns`) live in `tests/generic/`, so the project needs no packages. `dbt build` reports one expected warning: the source test showing that `raw.listings` contains duplicate loads.
