"""The seven catalogue metrics: files, division guard and compiled SQL."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from governed_analytics.catalogue import METRICS_DIR, CatalogueError, load_catalogue, load_metric
from governed_analytics.compiler import compile_intent
from governed_analytics.intent import Intent

CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "metric-catalogue-v0.md"
CATALOGUE = load_catalogue()

Q3 = {"start": "2026-07-01", "end": "2026-10-01", "as_of": "2026-11-14"}
ORDERS_Q3 = (
    "FROM marts.fct_orders WHERE is_paid = TRUE "
    "AND order_date >= DATE '2026-07-01' AND order_date < DATE '2026-10-01' "
    "GROUP BY period ORDER BY period"
)
QUARTER = "SELECT date_trunc('quarter', order_date) AS period"

EXPECTED_SQL = {
    "gross_merchandise_value": f"{QUARTER}, sum(gross_amount_eur) AS gross_merchandise_value {ORDERS_Q3}",
    "net_merchandise_value": f"{QUARTER}, sum(net_amount_eur) AS net_merchandise_value {ORDERS_Q3}",
    "commission_revenue": f"{QUARTER}, sum(net_commission_eur) AS commission_revenue {ORDERS_Q3}",
    "refund_rate": f"{QUARTER}, sum(refund_amount_eur) / nullif(sum(gross_amount_eur), 0) AS refund_rate {ORDERS_Q3}",
    "take_rate": f"{QUARTER}, sum(commission_eur) / nullif(sum(gross_amount_eur), 0) AS take_rate {ORDERS_Q3}",
    "paid_orders": f"{QUARTER}, count(order_id) AS paid_orders {ORDERS_Q3}",
    "active_listings": (
        "SELECT date_trunc('month', snapshot_date) AS period, count(DISTINCT listing_id) AS active_listings "
        "FROM marts.fct_listings WHERE is_active = TRUE "
        "AND snapshot_date >= DATE '2026-07-01' AND snapshot_date < DATE '2026-10-01' "
        "GROUP BY period ORDER BY period"
    ),
}


def test_catalogue_has_the_seven_metrics():
    assert sorted(CATALOGUE) == sorted(EXPECTED_SQL)


def test_files_match_the_contract():
    blocks = re.findall(r"```yaml\n(name:.*?)```", CONTRACT.read_text(), re.S)
    in_contract = {yaml.safe_load(b)["name"]: yaml.safe_load(b) for b in blocks}
    in_files = {p.stem: yaml.safe_load(p.read_text()) for p in METRICS_DIR.glob("*.yml")}
    assert in_files == in_contract


def test_only_active_listings_is_uncertified():
    assert {n for n, m in CATALOGUE.items() if not m.certified} == {"active_listings"}


@pytest.mark.parametrize("name", sorted(EXPECTED_SQL))
def test_compiles_last_quarter(name):
    metric = CATALOGUE[name]
    grain = "quarter" if "quarter" in metric.time_grains else "month"
    intent = Intent.from_dict({"metric": name, "time_grain": grain, "time_range": Q3})
    assert compile_intent(intent, metric) == EXPECTED_SQL[name]


@pytest.mark.parametrize(
    "expression",
    ["sum(a) / sum(b)", "sum(a) / nullif(sum(b), 1)", "sum(a) / (sum(b) + 0)"],
)
def test_division_must_be_guarded(tmp_path, expression):
    definition = yaml.safe_load((METRICS_DIR / "refund_rate.yml").read_text())
    definition["expression"] = expression
    path = tmp_path / "bad.yml"
    path.write_text(yaml.safe_dump(definition))
    with pytest.raises(CatalogueError, match="nullif"):
        load_metric(path)
