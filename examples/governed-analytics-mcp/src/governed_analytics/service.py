"""The governed query path, independent of MCP.

Intent in, rows plus provenance out: resolve the period, compile, run
read-only with caps, label, write the receipt. The model chooses the intent;
everything here is code (mcp-tool-design steps 2 to 6).
"""

from __future__ import annotations

import datetime as dt
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from governed_analytics import receipts, tracing
from governed_analytics.catalogue import Metric
from governed_analytics.compiler import COMPILER_VERSION, IntentError, compile_intent
from governed_analytics.intent import Filter, Intent, TimeRange
from governed_analytics.periods import RELATIVE_PERIODS, resolve

EXAMPLE_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Config:
    warehouse: Path
    dbt_target: Path
    log_dir: Path
    persona: str
    as_of: dt.date | None = None  # None: today in UTC
    row_cap: int = 1000
    timeout_seconds: float = 30.0
    transport: str | None = None

    @classmethod
    def from_env(cls, transport: str | None = None) -> Config:
        env = os.environ.get
        as_of = env("KIT_AS_OF")
        return cls(
            warehouse=Path(env("KIT_WAREHOUSE", EXAMPLE_DIR / "data" / "warehouse.duckdb")),
            dbt_target=Path(env("KIT_DBT_TARGET", EXAMPLE_DIR / "dbt" / "target")),
            log_dir=Path(env("KIT_LOG_DIR", EXAMPLE_DIR / "logs")),
            persona=env("KIT_PERSONA", "unspecified"),
            as_of=dt.date.fromisoformat(as_of) if as_of else None,
            row_cap=int(env("KIT_ROW_CAP", "1000")),
            timeout_seconds=float(env("KIT_TIMEOUT_SECONDS", "30")),
            transport=transport,
        )

    def today(self) -> dt.date:
        return self.as_of or dt.datetime.now(dt.UTC).date()


class QueryError(Exception):
    """An anticipated failure. The message is guidance for the model."""

    def __init__(self, message: str, reason: str):
        super().__init__(message)
        tracing.annotate(**{"kit.error.reason": reason})


class QueryService:
    def __init__(self, config: Config, catalogue: dict[str, Metric]):
        self.config = config
        self.catalogue = catalogue

    def query_metric(
        self,
        metric: str,
        time_grain: str,
        period: str | None = None,
        start: dt.date | None = None,
        end: dt.date | None = None,
        dimensions: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        definition = self.catalogue.get(metric)
        if definition is None:
            raise QueryError(
                f"Unknown metric '{metric}'. Use one of: {', '.join(sorted(self.catalogue))}.",
                "invalid_intent",
            )
        intent = Intent(
            metric=metric,
            time_grain=time_grain,
            time_range=self._time_range(period, start, end),
            dimensions=tuple(dimensions or ()),
            filters=tuple(Filter.from_dict(f) for f in filters or ()),
        )
        try:
            sql = compile_intent(intent, definition)
        except IntentError as e:
            raise QueryError(str(e), "invalid_intent") from e

        snapshot = receipts.data_snapshot(self.config.dbt_target)
        columns, rows, truncated = self._execute(sql)
        classification = "certified" if definition.certified else "exploratory"  # GR-06
        result_hash = receipts.result_hash(columns, rows)
        trace_id, span_id = tracing.current_ids()

        receipt = {
            "schema_version": receipts.SCHEMA_VERSION,
            "receipt_id": receipts.new_receipt_id(),
            "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "classification": classification,
            "source": "metric",
            "intent": _intent_record(intent),
            "metric_version": definition.version,
            "compiler_version": COMPILER_VERSION,
            "compiled_sql": sql,
            "sql_fingerprint": receipts.sql_fingerprint(sql),
            "data_snapshot": snapshot,
            "result": {"columns": columns, "row_count": len(rows), "truncated": truncated, "hash": result_hash},
            "trace_id": trace_id,
            "span_id": span_id,
        }
        receipts.append(self.config.log_dir / "receipts.jsonl", receipt)  # GR-05: before returning
        tracing.annotate(
            **{
                "db.system.name": "duckdb",
                "db.query.text": sql,
                "db.response.returned_rows": len(rows),
                "kit.receipt.id": receipt["receipt_id"],
                "kit.result.classification": classification,
                "kit.metric.name": definition.name,
                "kit.metric.version": definition.version,
                "kit.result.truncated": truncated,
            }
        )
        return {
            "classification": classification,
            "metric": {
                "name": definition.name,
                "version": definition.version,
                "definition": definition.description,
                "unit": definition.unit,
                "owner": definition.owner,
            },
            "time_range": receipt["intent"]["time_range"],
            "columns": columns,
            "rows": rows,
            "truncated": truncated,
            "receipt_id": receipt["receipt_id"],
            "how_to_report": (
                f"Name the metric ({definition.name} v{definition.version}), say the result is "
                f"{classification}, state the time range, and quote receipt {receipt['receipt_id']}."
                + (f" Only the first {len(rows)} rows are shown." if truncated else "")
            ),
        }

    def _time_range(self, period: str | None, start: dt.date | None, end: dt.date | None) -> TimeRange:
        today = self.config.today()
        if period and (start or end):
            raise QueryError("Give either `period` or `start` and `end`, not both.", "invalid_intent")
        if period:
            return resolve(period, today)
        if start and end:
            return TimeRange(start=start, end=end, as_of=today)
        raise QueryError(
            f"Give a time range: `period` (one of {', '.join(RELATIVE_PERIODS)}), "
            "or both `start` and `end` as ISO dates (end is exclusive).",
            "invalid_intent",
        )

    def _execute(self, sql: str) -> tuple[list[str], list[list[str | None]], bool]:
        cap = self.config.row_cap
        con = duckdb.connect(str(self.config.warehouse), read_only=True)  # GR-01
        timer = threading.Timer(self.config.timeout_seconds, con.interrupt)  # GR-03
        timer.start()
        try:
            cursor = con.execute(sql)
            columns = [d[0] for d in cursor.description]
            fetched = cursor.fetchmany(cap + 1)  # GR-03: one extra row tells us it was cut
        except duckdb.InterruptException:
            tracing.guardrail_hit("GR-03")
            raise QueryError(
                f"The query took longer than {self.config.timeout_seconds:g} seconds and was stopped. "
                "Narrow the time range, use a coarser time grain or drop a dimension.",
                "timeout",
            ) from None
        finally:
            timer.cancel()
            con.close()
        truncated = len(fetched) > cap
        if truncated:
            tracing.guardrail_hit("GR-03")
        rows = [[receipts.render(v, c) for v, c in zip(row, columns)] for row in fetched[:cap]]
        return columns, rows, truncated


def _intent_record(intent: Intent) -> dict[str, Any]:
    """The intent in receipt-contract shape, with dimensions and filters in canonical order."""
    time_range = {
        "start": intent.time_range.start.isoformat(),
        "end": intent.time_range.end.isoformat(),
        "as_of": intent.time_range.as_of.isoformat(),
    }
    if intent.time_range.relative:
        time_range["relative"] = intent.time_range.relative
    filters = [
        {k: v for k, v in {"column": f.column, "op": f.op, "value": f.value}.items() if v is not None}
        for f in sorted(intent.filters, key=lambda f: (f.column, f.op, repr(f.value)))
    ]
    return {
        "metric": intent.metric,
        "dimensions": sorted(intent.dimensions),
        "filters": filters,
        "time_grain": intent.time_grain,
        "time_range": time_range,
    }
