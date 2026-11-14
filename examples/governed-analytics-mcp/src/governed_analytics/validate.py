"""Catalogue validation (GR-04, GR-08), run in CI and, for the manifest checks, at server start.

    python -m governed_analytics.validate                  # catalogue against manifest and golden questions
    python -m governed_analytics.validate --base origin/main   # also check version bumps since that ref
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

from governed_analytics.catalogue import METRICS_DIR, Metric, load_catalogue
from governed_analytics.manifest import Manifest, load_manifest
from governed_analytics.service import EXAMPLE_DIR, Config

GOLDEN = EXAMPLE_DIR / "evals" / "golden_questions.yml"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
DEFINITION_FIELDS = ("model", "expression", "time_dimension", "filters")  # change the number: major bump


def against_manifest(catalogue: dict[str, Metric], manifest: Manifest) -> list[str]:
    """Each metric reads one mart, names only its columns, and exposes no PII (GR-04)."""
    problems = []
    for m in catalogue.values():
        if m.model not in manifest.columns:
            problems.append(f"{m.name}: model '{m.model}' is not a mart")
            continue
        columns, pii = manifest.columns[m.model], manifest.pii[m.model]
        named = {m.time_dimension, *m.allowed_dimensions, *(f.column for f in m.filters)}
        for column in sorted(named - columns):
            problems.append(f"{m.name}: '{column}' is not a column of {m.model}")
        for column in sorted(set(m.allowed_dimensions) & pii):
            problems.append(f"{m.name}: dimension '{column}' is personal data (GR-04)")
    return problems


def certification(catalogue: dict[str, Metric], golden_metrics: set[str]) -> list[str]:
    """A certified metric has an owner, a semver version and a golden question (GR-08)."""
    problems = []
    for m in catalogue.values():
        if not SEMVER.match(m.version):
            problems.append(f"{m.name}: version '{m.version}' is not semver")
        if not m.certified:
            continue
        if not m.owner or m.owner.lower() == "everyone":
            problems.append(f"{m.name}: certified but has no owner")
        if m.name not in golden_metrics:
            problems.append(f"{m.name}: certified but no golden question covers it")
    return problems


def version_bumps(old: dict, new: dict) -> list[str]:
    """A change to a definition field without a major version bump (GR-08)."""
    changed = [f for f in DEFINITION_FIELDS if old.get(f) != new.get(f)]
    if not changed:
        return []
    old_major, new_major = (int(SEMVER.match(d["version"])[1]) for d in (old, new))
    if new_major > old_major:
        return []
    return [f"{new['name']}: {', '.join(changed)} changed but version went {old['version']} -> {new['version']}; bump the major version"]


def golden_metrics(path: Path = GOLDEN) -> set[str]:
    names = set()
    for q in yaml.safe_load(path.read_text())["questions"]:
        expected = q.get("expected", {})
        for node in [expected, *expected.get("options", [])]:
            if "intent" in node:
                names.add(node["intent"]["metric"])
    return names


def since(base: str, metrics_dir: Path = METRICS_DIR) -> list[str]:
    problems = []
    for path in sorted(metrics_dir.glob("*.yml")):
        relative = path.relative_to(_repo_root())
        shown = subprocess.run(["git", "show", f"{base}:{relative}"], capture_output=True, text=True)
        if shown.returncode == 0:  # a new file has nothing to compare against
            problems += version_bumps(yaml.safe_load(shown.stdout), yaml.safe_load(path.read_text()))
    return problems


def _repo_root() -> Path:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
    return Path(out.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", help="git ref to compare metric versions against")
    args = parser.parse_args()

    catalogue = load_catalogue()
    problems = against_manifest(catalogue, load_manifest(Config.from_env().dbt_target))
    problems += certification(catalogue, golden_metrics())
    if args.base:
        problems += since(args.base)
    for p in problems:
        print(p)
    print(f"{len(catalogue)} metrics checked, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
