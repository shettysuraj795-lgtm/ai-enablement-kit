"""Metric definitions, as defined by docs/contracts/metric-definition.md.

Loading plus the division guard. Validation against the dbt manifest (GR-04, GR-08) comes later.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import sqlglot
import yaml
from sqlglot import exp

from governed_analytics.intent import Filter

METRICS_DIR = Path(__file__).resolve().parents[2] / "metrics"
GLOSSARY_PATH = Path(__file__).resolve().parents[2] / "glossary.yml"


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


class CatalogueError(ValueError):
    """A metric definition that must not be served."""


def load_metric(path: Path) -> Metric:
    return parse_metric(yaml.safe_load(path.read_text()))


def parse_metric(data: dict) -> Metric:
    _check_division(data["name"], data["expression"])
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


@dataclass(frozen=True)
class GlossaryOption:
    metric: str
    meaning: str


def load_glossary(catalogue: dict[str, Metric], path: Path = GLOSSARY_PATH) -> dict[str, tuple[GlossaryOption, ...]]:
    """Ambiguous terms -> the metrics they could mean. Every metric named must exist."""
    glossary = {
        term.lower(): tuple(GlossaryOption(**option) for option in options)
        for term, options in yaml.safe_load(path.read_text()).items()
    }
    for term, options in glossary.items():
        for option in options:
            if option.metric not in catalogue:
                raise CatalogueError(f"Glossary term '{term}' names unknown metric '{option.metric}'.")
    return glossary


def _check_division(name: str, expression: str) -> None:
    """Every division must be by nullif(..., 0), so an empty group gives NULL, not an error."""
    for division in sqlglot.parse_one(expression, dialect="duckdb").find_all(exp.Div):
        denominator = division.expression
        if not (isinstance(denominator, exp.Nullif) and denominator.expression.sql() == "0"):
            raise CatalogueError(
                f"{name}: divide by nullif(<denominator>, 0), not by {denominator.sql()}, "
                "so an empty group returns NULL instead of failing."
            )
