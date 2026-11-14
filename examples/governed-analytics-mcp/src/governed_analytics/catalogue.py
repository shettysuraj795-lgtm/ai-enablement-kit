"""Metric definitions, as defined by docs/contracts/metric-definition.md.

Loading only: validation against the dbt manifest (GR-04, GR-08) comes later.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from governed_analytics.intent import Filter

METRICS_DIR = Path(__file__).resolve().parents[2] / "metrics"


@dataclass(frozen=True)
class Metric:
    name: str
    description: str
    model: str
    expression: str
    time_dimension: str
    time_grains: tuple[str, ...]
    allowed_dimensions: tuple[str, ...]
    filters: tuple[Filter, ...]
    unit: str
    version: str
    owner: str
    certified: bool


def load_metric(path: Path) -> Metric:
    data = yaml.safe_load(path.read_text())
    return Metric(
        name=data["name"],
        description=data["description"],
        model=data["model"],
        expression=data["expression"],
        time_dimension=data["time_dimension"],
        time_grains=tuple(data["time_grains"]),
        allowed_dimensions=tuple(data["allowed_dimensions"]),
        filters=tuple(Filter.from_dict(f) for f in data["filters"]),
        unit=data["unit"],
        version=data["version"],
        owner=data["owner"],
        certified=data["certified"],
    )


def load_catalogue(directory: Path = METRICS_DIR) -> dict[str, Metric]:
    metrics = (load_metric(p) for p in sorted(directory.glob("*.yml")))
    return {m.name: m for m in metrics}
