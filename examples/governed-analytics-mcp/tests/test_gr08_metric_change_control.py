"""GR-08: certified metric definitions are change-controlled. Evidence for `pytest -m gr08`."""

from __future__ import annotations

import dataclasses

import pytest
import yaml
from support import CONFIG, needs_warehouse

from governed_analytics.catalogue import METRICS_DIR, load_catalogue
from governed_analytics.manifest import load_manifest
from governed_analytics.validate import against_manifest, certification, golden_metrics, version_bumps

pytestmark = pytest.mark.gr08

CATALOGUE = load_catalogue()
NMV = CATALOGUE["net_merchandise_value"]
NMV_FILE = yaml.safe_load((METRICS_DIR / "net_merchandise_value.yml").read_text())


@needs_warehouse
def test_current_catalogue_passes():
    assert against_manifest(CATALOGUE, load_manifest(CONFIG.dbt_target)) == []
    assert certification(CATALOGUE, golden_metrics()) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"owner": ""}, "certified but has no owner"),
        ({"owner": "everyone"}, "certified but has no owner"),
        ({"version": "1.0"}, "is not semver"),
    ],
)
def test_certified_metric_needs_owner_and_version(change, problem):
    catalogue = {NMV.name: dataclasses.replace(NMV, **change)}
    assert any(problem in p for p in certification(catalogue, {NMV.name}))


def test_certified_metric_needs_a_golden_question():
    assert certification({NMV.name: NMV}, golden_metrics=set()) == [
        "net_merchandise_value: certified but no golden question covers it"
    ]


def test_uncertified_metric_needs_neither():
    draft = dataclasses.replace(NMV, certified=False, owner="")
    assert certification({NMV.name: draft}, golden_metrics=set()) == []


@pytest.mark.parametrize(
    "field, value",
    [
        ("filters", []),
        ("expression", "sum(gross_amount_eur)"),
        ("model", "fct_orders_v2"),
        ("time_dimension", "paid_at"),
    ],
)
def test_definition_change_needs_a_major_bump(field, value):
    minor = {**NMV_FILE, field: value, "version": "1.1.0"}
    major = {**NMV_FILE, field: value, "version": "2.0.0"}
    assert version_bumps(NMV_FILE, minor) and "bump the major version" in version_bumps(NMV_FILE, minor)[0]
    assert version_bumps(NMV_FILE, major) == []


def test_wording_change_needs_no_major_bump():
    reworded = {**NMV_FILE, "description": "Reworded.", "version": "1.0.1"}
    assert version_bumps(NMV_FILE, reworded) == []
