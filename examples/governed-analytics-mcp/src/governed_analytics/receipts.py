"""Query receipts, as defined by docs/contracts/receipt.md (GR-05)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

SCHEMA_VERSION = "1.0"

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_receipt_id() -> str:
    """`rcpt_` plus a ULID: 48-bit millisecond timestamp, 80 random bits, so IDs sort by time."""
    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10))
    chars = []
    for _ in range(26):
        value, index = divmod(value, 32)
        chars.append(_CROCKFORD[index])
    return "rcpt_" + "".join(reversed(chars))


def render(value: Any, column: str) -> str | None:
    """Render one value in the canonical form receipts hash and golden answers store."""
    if value is None:
        return None
    if column == "period" and isinstance(value, dt.datetime):
        return value.date().isoformat()  # date_trunc returns a timestamp; a period is a date
    if isinstance(value, float):
        return f"{value:.6f}"  # ratios
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)  # keeps the column's scale
    return str(value)


def result_hash(columns: list[str], rows: list[list[str | None]]) -> str:
    canonical = json.dumps([columns, *rows], separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def sql_fingerprint(sql: str) -> str:
    """Hash of the query's shape: same tables, columns and clauses, any literal values."""
    tree = sqlglot.parse_one(sql, dialect="duckdb")
    shape = tree.transform(lambda node: exp.Placeholder() if isinstance(node, exp.Literal) else node)
    normalised = shape.sql(dialect="duckdb", normalize=True)
    return "sha256:" + hashlib.sha256(normalised.encode()).hexdigest()


def data_snapshot(dbt_target: Path) -> dict[str, str]:
    """When the dbt build behind the warehouse finished, from dbt's run_results.json."""
    path = dbt_target / "run_results.json"
    try:
        metadata = json.loads(path.read_text())["metadata"]
    except FileNotFoundError:
        raise FileNotFoundError(f"{path} not found: run `dbt build` before querying") from None
    return {"snapshot_at": metadata["generated_at"], "dbt_invocation_id": metadata["invocation_id"]}


def find(path: Path, receipt_id: str) -> dict | None:
    """The stored receipt with this ID, or None."""
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        receipt = json.loads(line)
        if receipt["receipt_id"] == receipt_id:
            return receipt
    return None


def new_id(prefix: str) -> str:
    """`<prefix>_` plus a ULID, as for receipt IDs."""
    return prefix + new_receipt_id()[len("rcpt"):]


def append(path: Path, record: dict) -> None:
    """Append one JSON object as one line. Shared by receipts and traces."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
