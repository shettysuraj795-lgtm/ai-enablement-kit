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

from governed_analytics import allowlist, receipts, tracing
from governed_analytics.catalogue import GlossaryOption, Metric
from governed_analytics.compiler import COMPILER_VERSION, IntentError, compile_intent
from governed_analytics.intent import Filter, Intent, TimeRange
from governed_analytics.manifest import Manifest
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
    retention_days: int = 30  # GR-04: question text older than this is deleted
    purge_interval_seconds: float = 86400.0  # how often a running server purges
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
            retention_days=int(env("KIT_QUESTION_RETENTION_DAYS", "30")),
            purge_interval_seconds=float(env("KIT_PURGE_INTERVAL_SECONDS", "86400")),
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
    def __init__(
        self,
        config: Config,
        catalogue: dict[str, Metric],
        glossary: dict[str, tuple[GlossaryOption, ...]] | None = None,
        manifest: Manifest | None = None,
    ):
        self.config = config
        self.catalogue = catalogue
        self.glossary = glossary or {}
        self.manifest = manifest

    def list_metrics(self, term: str | None = None) -> dict[str, Any]:
        """The catalogue, or the governed options for one ambiguous term."""
        if term:
            options = self.glossary.get(term.strip().lower())
            if options:
                return {
                    "term": term,
                    "options": [
                        {**_summary(self.catalogue[o.metric]), "meaning": o.meaning} for o in options
                    ],
                    "next_step": (
                        f"'{term}' could mean {len(options)} governed metric(s). Unless the user's question "
                        "already settles it, list these options and ask which one they mean; otherwise "
                        "say which one you chose and why."
                        if len(options) > 1
                        else f"'{term}' maps to one metric. Say which one you used."
                    ),
                }
        return {
            "metrics": [_summary(m) for m in sorted(self.catalogue.values(), key=lambda m: m.name)],
            "glossary": {t: [o.metric for o in opts] for t, opts in sorted(self.glossary.items())},
            "next_step": (
                (f"No glossary entry for '{term}'. " if term else "")
                + "Pick the metric whose definition fits the question; call describe_metric for details."
            ),
        }

    def describe_metric(self, metric: str) -> dict[str, Any]:
        definition = self.catalogue.get(metric)
        if definition is None:
            raise QueryError(
                f"Unknown metric '{metric}'. Use one of: {', '.join(sorted(self.catalogue))}.",
                "invalid_intent",
            )
        return {
            **_summary(definition),
            "definition": definition.description,
            "owner": definition.owner,
            "time_grains": list(definition.time_grains),
            "allowed_dimensions": list(definition.allowed_dimensions),
            "always_applied": [_describe_filter(f) for f in definition.filters],
            "glossary_terms": sorted(t for t, opts in self.glossary.items() if any(o.metric == metric for o in opts)),
        }

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

        classification = "certified" if definition.certified else "exploratory"  # GR-06
        receipt, rows = self._run_with_receipt(sql, classification, "metric", _intent_record(intent), definition.version)
        tracing.annotate(**{"kit.metric.name": definition.name, "kit.metric.version": definition.version})
        truncated = receipt["result"]["truncated"]
        columns = receipt["result"]["columns"]
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

    def explore_sql(self, sql: str) -> dict[str, Any]:
        """The escape hatch: checked against the allow-list, always exploratory, always receipted."""
        if self.manifest is None:
            raise QueryError("Exploratory SQL is not available: the server has no dbt manifest.", "internal")
        try:
            checked = allowlist.check(sql, self.manifest)
        except allowlist.SqlRejected as e:
            tracing.guardrail_hit(e.requirement)
            raise QueryError(str(e), "guardrail_blocked") from e

        receipt, rows = self._run_with_receipt(checked.sql, "exploratory", "explore_sql", None, None)  # GR-06
        truncated = receipt["result"]["truncated"]
        return {
            "classification": "exploratory",
            "sql": checked.sql,
            "columns": receipt["result"]["columns"],
            "rows": rows,
            "truncated": truncated,
            "receipt_id": receipt["receipt_id"],
            "how_to_report": (
                "Say plainly that this is an exploratory result, not a certified metric, and quote receipt "
                f"{receipt['receipt_id']}. If the user will rely on it again, offer to call "
                "request_certification with this receipt ID." + (f" Only the first {len(rows)} rows are shown." if truncated else "")
            ),
        }

    def request_certification(self, receipt_id: str, question_shape: str) -> dict[str, Any]:
        """Queue an exploratory result for BI to consider certifying. Returns no data, so no receipt."""
        receipt = receipts.find(self.config.log_dir / "receipts.jsonl", receipt_id)
        if receipt is None:
            raise QueryError(
                f"No receipt {receipt_id}. Use the receipt_id returned by explore_sql or query_metric.",
                "invalid_intent",
            )
        if receipt["classification"] == "certified":
            raise QueryError(
                f"Receipt {receipt_id} is already a certified result ({receipt['intent']['metric']}); "
                "there is nothing to certify.",
                "invalid_intent",
            )
        trace_id, span_id = tracing.current_ids()
        request = {
            "request_id": receipts.new_id("creq"),
            "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "receipt_id": receipt_id,
            "source": receipt["source"],
            "metric": (receipt["intent"] or {}).get("metric"),  # set for an uncertified metric
            "sql_fingerprint": receipt["sql_fingerprint"],
            "question_shape": question_shape,  # purged with kit.question under GR-04 retention
            "persona": self.config.persona,
            "trace_id": trace_id,
            "span_id": span_id,
        }
        receipts.append(self.config.log_dir / "certification_requests.jsonl", request)
        tracing.annotate(**{"kit.certification_request.id": request["request_id"]})
        return {
            "request_id": request["request_id"],
            "status": "queued for BI review",
            "next_step": (
                f"Tell the user the request {request['request_id']} is logged for BI, who decide whether to "
                "certify a metric. Until then the answer stays exploratory."
            ),
        }

    def _run_with_receipt(
        self, sql: str, classification: str, source: str, intent: dict | None, metric_version: str | None
    ) -> tuple[dict[str, Any], list[list[str | None]]]:
        """Execute, write the receipt before returning (GR-05) and annotate the span."""
        snapshot = receipts.data_snapshot(self.config.dbt_target)
        columns, rows, truncated = self.execute(sql)
        trace_id, span_id = tracing.current_ids()
        receipt = {
            "schema_version": receipts.SCHEMA_VERSION,
            "receipt_id": receipts.new_receipt_id(),
            "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "classification": classification,
            "source": source,
            "intent": intent,
            "metric_version": metric_version,
            "compiler_version": COMPILER_VERSION,
            "compiled_sql": sql,
            "sql_fingerprint": receipts.sql_fingerprint(sql),
            "data_snapshot": snapshot,
            "result": {
                "columns": columns,
                "row_count": len(rows),
                "truncated": truncated,
                "hash": receipts.result_hash(columns, rows),
            },
            "trace_id": trace_id,
            "span_id": span_id,
        }
        receipts.append(self.config.log_dir / "receipts.jsonl", receipt)
        tracing.annotate(
            **{
                "db.system.name": "duckdb",
                "db.query.text": sql,
                "db.response.returned_rows": len(rows),
                "kit.receipt.id": receipt["receipt_id"],
                "kit.result.classification": classification,
                "kit.result.truncated": truncated,
            }
        )
        return receipt, rows

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

    def execute(self, sql: str) -> tuple[list[str], list[list[str | None]], bool]:
        cap = self.config.row_cap
        con = connect_read_only(self.config.warehouse)
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


def connect_read_only(warehouse: Path) -> duckdb.DuckDBPyConnection:
    """The only way the server opens the warehouse (GR-01).

    `read_only` blocks writes to the database, but not to files: without
    `enable_external_access: False`, `COPY ... TO`, `read_csv` and `INSTALL`
    still work. SQL cannot switch external access back on.
    """
    return duckdb.connect(str(warehouse), read_only=True, config={"enable_external_access": False})


def _summary(metric: Metric) -> dict[str, Any]:
    return {
        "name": metric.name,
        "summary": metric.description.split(". ")[0].rstrip(".") + ".",
        "unit": metric.unit,
        "version": metric.version,
        "certified": metric.certified,
    }


def _describe_filter(f: Filter) -> str:
    if f.op in ("is_null", "is_not_null"):
        return f"{f.column} {f.op.replace('_', ' ')}"
    return f"{f.column} {f.op} {f.value}"


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
