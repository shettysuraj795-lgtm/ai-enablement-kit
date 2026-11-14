"""What dbt says about the marts: their columns and which columns are personal data.

The dbt manifest is the single source for both (GR-04: PII is flagged with
`meta: {pii: true}` where columns are documented).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

MARTS_SCHEMA = "marts"


@dataclass(frozen=True)
class Manifest:
    columns: dict[str, frozenset[str]]  # mart model -> its columns
    pii: dict[str, frozenset[str]]  # mart model -> its PII columns

    def all_pii(self) -> frozenset[str]:
        return frozenset().union(*self.pii.values())


def load_manifest(dbt_target: Path) -> Manifest:
    path = dbt_target / "manifest.json"
    try:
        nodes = json.loads(path.read_text())["nodes"].values()
    except FileNotFoundError:
        raise FileNotFoundError(f"{path} not found: run `dbt build` first") from None
    columns, pii = {}, {}
    for node in nodes:
        if node["resource_type"] != "model" or node["schema"] != MARTS_SCHEMA:
            continue
        columns[node["name"]] = frozenset(node["columns"])
        pii[node["name"]] = frozenset(
            name
            for name, column in node["columns"].items()
            if {**column.get("meta", {}), **column.get("config", {}).get("meta", {})}.get("pii")
        )
    return Manifest(columns=columns, pii=pii)
