from __future__ import annotations

import datetime as dt
import hashlib
import re
from decimal import Decimal

from governed_analytics.receipts import new_receipt_id, render, result_hash, sql_fingerprint

NMV_SQL = (
    "SELECT date_trunc('quarter', order_date) AS period, sum(net_amount_eur) AS net_merchandise_value "
    "FROM marts.fct_orders WHERE is_paid = TRUE AND order_date >= DATE '{start}' "
    "AND order_date < DATE '{end}' GROUP BY period ORDER BY period"
)


def test_receipt_ids_are_ulids_that_sort_by_time():
    first, second = new_receipt_id(), new_receipt_id()
    assert re.fullmatch(r"rcpt_[0-9A-HJKMNP-TV-Z]{26}", first)
    assert first[:15] <= second[:15]  # same or later millisecond prefix
    assert first != second


def test_render_matches_canonical_form():
    assert render(dt.datetime(2026, 7, 1), "period") == "2026-07-01"
    assert render(Decimal("8743316.38"), "net_merchandise_value") == "8743316.38"
    assert render(0.0466712345, "take_rate") == "0.046671"
    assert render(489, "paid_orders") == "489"
    assert render(None, "dealer_tier") is None


def test_result_hash_is_compact_json_sha256():
    # Canonical result from the receipt contract's worked example.
    digest = result_hash(["period", "net_merchandise_value"], [["2026-07-01", "4812337.50"]])
    expected = hashlib.sha256(b'[["period","net_merchandise_value"],["2026-07-01","4812337.50"]]')
    assert digest == "sha256:" + expected.hexdigest()


def test_fingerprint_ignores_literal_values():
    q3 = NMV_SQL.format(start="2026-07-01", end="2026-10-01")
    q2 = NMV_SQL.format(start="2026-04-01", end="2026-07-01")
    assert sql_fingerprint(q3) == sql_fingerprint(q2)


def test_fingerprint_changes_with_shape():
    q3 = NMV_SQL.format(start="2026-07-01", end="2026-10-01")
    with_dimension = q3.replace("AS period,", "AS period, dealer_region,")
    assert sql_fingerprint(q3) != sql_fingerprint(with_dimension)
