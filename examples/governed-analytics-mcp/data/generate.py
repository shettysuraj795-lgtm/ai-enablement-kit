"""Generate synthetic marketplace data for the governed analytics example.

Writes raw tables (dealers, watch models, listings, listing status changes,
orders, refunds, commissions) into the `raw` schema of a DuckDB file, and the
daily FX reference rates as a dbt seed CSV. Everything is driven by one fixed
seed, so every run produces identical data.

The data contains the traps described in docs/adr/004-synthetic-data-and-traps.md:
late refunds, orders in four currencies with rates that move day to day, and
listings ingested twice.

Usage:
    python generate.py [--db PATH] [--fx-seed PATH]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import random
import re
import tempfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import duckdb

SEED = 20261114

HERE = Path(__file__).resolve().parent
DEFAULT_DB = HERE / "warehouse.duckdb"
DEFAULT_FX_SEED = HERE.parent / "dbt" / "seeds" / "fx_rates.csv"

FX_START = dt.date(2024, 9, 1)
LISTINGS_START = dt.date(2024, 10, 1)
# Last complete day of data. The example is evaluated as of 14 Nov 2026.
DATA_END = dt.date(2026, 11, 13)
LOADED_AT = dt.datetime(2026, 11, 14, 6, 0, 0)

# country code -> (weight, currency the dealer sells in)
DEALER_COUNTRIES = {
    "DE": (30, "EUR"),
    "IT": (10, "EUR"),
    "FR": (7, "EUR"),
    "NL": (5, "EUR"),
    "AT": (5, "EUR"),
    "ES": (4, "EUR"),
    "CH": (12, "CHF"),
    "GB": (10, "GBP"),
    "US": (10, "USD"),
    "JP": (4, "USD"),
    "HK": (3, "USD"),
}
# tier -> (share of dealers, relative listing volume, commission rate)
TIERS = {
    "standard": (55, 1, Decimal("0.065")),
    "premium": (30, 2, Decimal("0.055")),
    "platinum": (15, 4, Decimal("0.045")),
}
# Commission per order is capped, in the order's currency, so take rate falls
# for expensive watches and differs from the headline tier rate.
COMMISSION_CAP = Decimal("900")
N_DEALERS = 150
N_BUYERS = 6000

BRANDS = ["Aldenmark", "Bressac", "Corvell", "Duvant", "Halvorsen", "Lindqvist", "Marchetti", "Ostrava"]
CATEGORIES = ["dress", "diver", "chronograph", "pilot", "sports"]
MODEL_WORDS = ["Meridian", "Abyss", "Tempo", "Altura", "Regatta", "Classic", "Horizon", "Vector", "Sentinel", "Aero"]

CONDITIONS = {"new": 1.10, "unworn": 1.05, "very_good": 0.90, "good": 0.80, "fair": 0.65}

# EUR per unit of currency at FX_START, and daily volatility
FX_START_RATES = {"USD": 0.9050, "GBP": 1.1830, "CHF": 1.0620}
FX_DAILY_VOL = {"USD": 0.0045, "GBP": 0.0035, "CHF": 0.0030}
# One-off moves, so that converting at the payment date instead of the order
# date visibly changes figures around the Q3/Q4 2026 boundary.
FX_JUMPS = {(dt.date(2026, 9, 29), "USD"): -0.035, (dt.date(2026, 10, 1), "GBP"): 0.020}

LISTINGS_PER_DAY = 30
FAILED_ORDER_PROBABILITY = 0.05
REFUND_SHARE = 0.09
DUPLICATE_LISTING_SHARE = 0.03

CENT = Decimal("0.01")


def money(x: Decimal | float) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def days(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def at_time(rng: random.Random, day: dt.date, earliest_hour: int = 7, latest_hour: int = 22) -> dt.datetime:
    seconds = rng.randint(earliest_hour * 3600, latest_hour * 3600 - 1)
    return dt.datetime.combine(day, dt.time()) + dt.timedelta(seconds=seconds)


def weighted(rng: random.Random, options: dict[str, tuple]) -> str:
    """Pick a key, weighted by the first element of its value."""
    keys = list(options)
    return rng.choices(keys, weights=[options[k][0] for k in keys])[0]


def gen_fx(rng: random.Random) -> dict[tuple[dt.date, str], float]:
    """Daily EUR-per-unit rates for every calendar day, rounded to 6 places."""
    rates = {}
    level = dict(FX_START_RATES)
    for day in days(FX_START, DATA_END):
        for ccy in ("USD", "GBP", "CHF"):
            if day != FX_START:
                level[ccy] *= math.exp(rng.gauss(0, FX_DAILY_VOL[ccy]))
                level[ccy] *= 1 + FX_JUMPS.get((day, ccy), 0)
            rates[(day, ccy)] = round(level[ccy], 6)
        rates[(day, "EUR")] = 1.0
    return rates


def gen_dealers(rng: random.Random) -> list[dict]:
    prefixes = ["Atelier", "Maison", "Uhren", "Orologi", "Horloges", "Time", "Vintage", "Heritage"]
    suffixes = ["Berg", "Rossi", "Laurent", "Keller", "Novak", "Hart", "Sato", "Chen", "Weiss", "Moreau"]
    dealers = []
    for i in range(1, N_DEALERS + 1):
        country = weighted(rng, DEALER_COUNTRIES)
        tier = weighted(rng, TIERS)
        dealers.append(
            {
                "dealer_id": f"D{i:04d}",
                "dealer_name": f"{rng.choice(prefixes)} {rng.choice(suffixes)} {i}",
                "country_code": country,
                "subscription_tier": tier,
                "currency": DEALER_COUNTRIES[country][1],
                "joined_on": dt.date(2019, 1, 1) + dt.timedelta(days=rng.randint(0, 5 * 365)),
            }
        )
    return dealers


def gen_models(rng: random.Random) -> list[dict]:
    models = []
    n = 0
    for brand in BRANDS:
        for _ in range(6):
            n += 1
            models.append(
                {
                    "model_id": f"M{n:03d}",
                    "brand": brand,
                    "model_name": f"{rng.choice(MODEL_WORDS)} {rng.choice(['II', 'GMT', 'Auto', '38', '41', 'Heritage'])}",
                    "reference": f"{rng.randint(1000, 9999)}.{rng.randint(10, 99)}",
                    "category": rng.choice(CATEGORIES),
                    "launch_year": rng.randint(1995, 2025),
                    "base_price_eur": round(math.exp(rng.gauss(math.log(6000), 0.7)), -1),
                }
            )
    return models


def daily_listing_volume(day: dt.date) -> float:
    """Mild growth over the period, plus a pre-Christmas peak."""
    growth = 1 + 0.25 * (day - LISTINGS_START).days / (DATA_END - LISTINGS_START).days
    season = 1.15 if day.month in (11, 12) else 0.92 if day.month in (7, 8) else 1.0
    return LISTINGS_PER_DAY * growth * season


def generate(rng: random.Random):
    fx = gen_fx(rng)
    dealers = gen_dealers(rng)
    models = gen_models(rng)
    dealer_weights = [TIERS[d["subscription_tier"]][1] for d in dealers]
    dealer_by_id = {d["dealer_id"]: d for d in dealers}
    dealer_of_listing: dict[str, str] = {}

    listings, status_changes, orders, refunds, commissions = [], [], [], [], []
    n_listing = 0

    for created in days(LISTINGS_START, DATA_END):
        volume = daily_listing_volume(created)
        count = int(volume) + (1 if rng.random() < volume % 1 else 0)
        for _ in range(count):
            n_listing += 1
            listing_id = f"L{n_listing:06d}"
            dealer = rng.choices(dealers, weights=dealer_weights)[0]
            dealer_of_listing[listing_id] = dealer["dealer_id"]
            model = rng.choice(models)
            condition = rng.choice(list(CONDITIONS))
            ccy = dealer["currency"]
            price_eur = model["base_price_eur"] * CONDITIONS[condition] * math.exp(rng.gauss(0, 0.12))
            asking = Decimal(round(price_eur / fx[(created, ccy)], -1)).quantize(CENT)
            created_at = at_time(rng, created)
            listings.append(
                {
                    "listing_id": listing_id,
                    "dealer_id": dealer["dealer_id"],
                    "model_id": model["model_id"],
                    "condition": condition,
                    "asking_price": asking,
                    "currency": ccy,
                    "created_at": created_at,
                    "_loaded_at": created_at + dt.timedelta(hours=rng.randint(1, 6)),
                }
            )
            status_changes.append({"listing_id": listing_id, "status": "active", "changed_on": created})

            outcome = rng.random()
            if outcome < 0.42:
                end_status, duration = "sold", 3 + int(rng.expovariate(1 / 40))
            elif outcome < 0.67:
                end_status, duration = "withdrawn", 7 + int(rng.expovariate(1 / 60))
            else:
                end_status, duration = "withdrawn", 30 + int(rng.expovariate(1 / 180))
            end_date = created + dt.timedelta(days=duration)

            pay_lag = rng.choices([0, 1, 2, 3, 4], weights=[35, 30, 18, 10, 7])[0] if end_status == "sold" else 0
            order_date = end_date - dt.timedelta(days=pay_lag)

            # Optional pause, always finished well before the listing ends.
            if duration > 20 and rng.random() < 0.12:
                pause_start = created + dt.timedelta(days=rng.randint(2, duration - 14))
                pause_end = pause_start + dt.timedelta(days=rng.randint(3, 10))
                for status, day in (("paused", pause_start), ("active", pause_end)):
                    if day <= DATA_END:
                        status_changes.append({"listing_id": listing_id, "status": status, "changed_on": day})
            else:
                pause_start = pause_end = None

            # A failed payment on a day the listing was live; the listing stays up.
            if duration > 10 and rng.random() < FAILED_ORDER_PROBABILITY:
                failed_day = created + dt.timedelta(days=rng.randint(1, duration - 6))
                in_pause = pause_start is not None and pause_start <= failed_day < pause_end
                if failed_day <= DATA_END and not in_pause:
                    orders.append(_order(rng, listing_id, failed_day, asking, ccy, "failed", None))

            if end_status == "sold" and order_date <= DATA_END:
                paid_day = order_date + dt.timedelta(days=pay_lag)
                if paid_day <= DATA_END:
                    order = _order(rng, listing_id, order_date, asking, ccy, "paid", paid_day)
                    orders.append(order)
                    status_changes.append({"listing_id": listing_id, "status": "sold", "changed_on": paid_day})
                else:
                    # Payment still pending at the snapshot; the listing is still live.
                    orders.append(_order(rng, listing_id, order_date, asking, ccy, "pending", None))
            elif end_status == "withdrawn" and end_date <= DATA_END:
                status_changes.append({"listing_id": listing_id, "status": "withdrawn", "changed_on": end_date})

    # Stable IDs: number orders by time placed.
    orders.sort(key=lambda o: (o["ordered_at"], o["listing_id"]))
    for i, order in enumerate(orders, start=1):
        order["order_id"] = f"O{i:07d}"

    n_refund = n_commission = 0
    for order in orders:
        if order["payment_status"] != "paid":
            continue
        dealer = dealer_by_id[dealer_of_listing[order["listing_id"]]]
        rate = TIERS[dealer["subscription_tier"]][2]
        commission = min(money(order["amount"] * rate), COMMISSION_CAP)
        n_commission += 1
        commissions.append(_commission(n_commission, order, None, "charge", commission, order["paid_at"]))

        if rng.random() >= REFUND_SHARE:
            continue
        kind = rng.choices(["full", "partial", "two_step"], weights=[65, 25, 10])[0]
        if rng.random() < 0.30:
            first_lag = rng.randint(35, 120)  # late refund: often lands in a later month or quarter
        else:
            first_lag = rng.randint(3, 30)
        plan = []
        if kind == "full":
            plan.append((first_lag, order["amount"], "returned"))
        elif kind == "partial":
            plan.append((first_lag, money(order["amount"] * Decimal(str(rng.uniform(0.1, 0.4)))), "price_adjustment"))
        else:
            part = money(order["amount"] * Decimal(str(rng.uniform(0.1, 0.4))))
            plan.append((first_lag, part, "price_adjustment"))
            plan.append((first_lag + rng.randint(10, 40), order["amount"] - part, "returned"))

        refunded_so_far = Decimal("0")
        commission_refunded_so_far = Decimal("0")
        for lag, amount, reason in plan:
            refunded_at = at_time(rng, order["paid_at"].date() + dt.timedelta(days=lag), 8, 18)
            if refunded_at.date() > DATA_END:
                break  # not happened yet at the snapshot
            n_refund += 1
            refund_id = f"R{n_refund:06d}"
            refunds.append(
                {
                    "refund_id": refund_id,
                    "order_id": order["order_id"],
                    "refunded_at": refunded_at,
                    "amount": amount,
                    "currency": order["currency"],
                    "reason": reason,
                }
            )
            # Refunded commission is proportional to the cumulative refund, so
            # rounding can never push it above the commission charged.
            refunded_so_far += amount
            target = money(commission * refunded_so_far / order["amount"])
            n_commission += 1
            commissions.append(
                _commission(n_commission, order, refund_id, "refund", target - commission_refunded_so_far, refunded_at)
            )
            commission_refunded_so_far = target

    # Ingestion trap: a replayed export loaded some listings a second time.
    replay_at = dt.datetime(2026, 3, 2, 4, 15, 0)
    for listing in list(listings):
        if listing["created_at"] < replay_at and rng.random() < DUPLICATE_LISTING_SHARE:
            listings.append({**listing, "_loaded_at": replay_at})

    return fx, dealers, models, listings, status_changes, orders, refunds, commissions


def _order(rng, listing_id, order_date, asking, ccy, status, paid_day):
    ordered_at = at_time(rng, order_date)
    discount = Decimal(str(rng.uniform(0, 0.07)))
    paid_at = None
    if paid_day is not None:
        paid_at = at_time(rng, paid_day)
        if paid_at <= ordered_at:
            paid_at = ordered_at + dt.timedelta(minutes=rng.randint(5, 240))
    return {
        "order_id": None,
        "listing_id": listing_id,
        "buyer_id": f"B{rng.randint(1, N_BUYERS):06d}",
        "ordered_at": ordered_at,
        "currency": ccy,
        "amount": (asking * (1 - discount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(CENT),
        "payment_status": status,
        "paid_at": paid_at,
    }


def _commission(n, order, refund_id, entry_type, amount, booked_at):
    return {
        "commission_id": f"C{n:07d}",
        "order_id": order["order_id"],
        "refund_id": refund_id,
        "entry_type": entry_type,
        "amount": amount,
        "currency": order["currency"],
        "booked_at": booked_at,
    }


TABLES = {
    "dealers": """dealer_id VARCHAR, dealer_name VARCHAR, country_code VARCHAR, subscription_tier VARCHAR,
                  currency VARCHAR, joined_on DATE""",
    "watch_models": """model_id VARCHAR, brand VARCHAR, model_name VARCHAR, reference VARCHAR, category VARCHAR,
                       launch_year INTEGER""",
    "listings": """listing_id VARCHAR, dealer_id VARCHAR, model_id VARCHAR, condition VARCHAR,
                   asking_price DECIMAL(18,2), currency VARCHAR, created_at TIMESTAMP, _loaded_at TIMESTAMP""",
    "listing_status_changes": "listing_id VARCHAR, status VARCHAR, changed_on DATE",
    "orders": """order_id VARCHAR, listing_id VARCHAR, buyer_id VARCHAR, ordered_at TIMESTAMP, currency VARCHAR,
                 amount DECIMAL(18,2), payment_status VARCHAR, paid_at TIMESTAMP""",
    "refunds": """refund_id VARCHAR, order_id VARCHAR, refunded_at TIMESTAMP, amount DECIMAL(18,2),
                  currency VARCHAR, reason VARCHAR""",
    "commissions": """commission_id VARCHAR, order_id VARCHAR, refund_id VARCHAR, entry_type VARCHAR,
                      amount DECIMAL(18,2), currency VARCHAR, booked_at TIMESTAMP""",
}


def write_db(path: Path, data: dict[str, list[dict]]) -> None:
    path.unlink(missing_ok=True)
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA raw")
    with tempfile.TemporaryDirectory() as tmp:
        for table, columns in TABLES.items():
            con.execute(f"CREATE TABLE raw.{table} ({columns})")
            names = re.findall(r"(\w+) [A-Z]+", columns)
            csv_path = Path(tmp) / f"{table}.csv"
            with csv_path.open("w", newline="") as f:
                writer = csv.writer(f, lineterminator="\n")
                for row in data[table]:
                    writer.writerow(["" if row[n] is None else row[n] for n in names])
            con.execute(f"COPY raw.{table} FROM '{csv_path}' (HEADER false, NULLSTR '')")
    con.close()


def write_fx_seed(path: Path, fx: dict[tuple[dt.date, str], float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["rate_date", "currency", "eur_per_unit"])
        for (day, ccy), rate in sorted(fx.items()):
            writer.writerow([day.isoformat(), ccy, f"{rate:.6f}"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--fx-seed", type=Path, default=DEFAULT_FX_SEED)
    args = parser.parse_args()

    rng = random.Random(SEED)
    fx, dealers, models, listings, status_changes, orders, refunds, commissions = generate(rng)
    write_fx_seed(args.fx_seed, fx)
    write_db(
        args.db,
        {
            "dealers": dealers,
            "watch_models": models,
            "listings": listings,
            "listing_status_changes": status_changes,
            "orders": orders,
            "refunds": refunds,
            "commissions": commissions,
        },
    )
    print(
        f"Wrote {args.db.name}: {len(dealers)} dealers, {len(models)} models, {len(listings)} listing rows, "
        f"{len(orders)} orders, {len(refunds)} refunds, {len(commissions)} commission entries; "
        f"{len(fx)} FX rates to {args.fx_seed.name}"
    )


if __name__ == "__main__":
    main()
