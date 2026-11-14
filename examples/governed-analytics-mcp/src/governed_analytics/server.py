"""MCP server exposing governed metrics. Run with `python -m governed_analytics.server`.

A thin binding: argument types come from the catalogue, the work happens in
service.py, tracing in tracing.py.
"""

# No `from __future__ import annotations` here: the tool's argument types are
# built from the catalogue at runtime, and pydantic must see them as objects.

import contextlib
import datetime as dt
import logging
from typing import Annotated, Any, Literal

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from governed_analytics.catalogue import CatalogueError, Metric, load_catalogue, load_glossary
from governed_analytics.intent import OPS
from governed_analytics.manifest import Manifest, load_manifest
from governed_analytics.periods import RELATIVE_PERIODS
from governed_analytics.retention import purge_all
from governed_analytics.service import Config, QueryError, QueryService
from governed_analytics.tracing import TraceMiddleware
from governed_analytics.validate import against_manifest

VERSION = "0.1.0"
GRAINS = ("day", "week", "month", "quarter", "year")

INSTRUCTIONS = (
    "Governed business metrics. Use list_metrics and describe_metric to choose a metric, answer with "
    "query_metric, and always report "
    "the metric name and version, whether the result is certified, the time range and the receipt ID."
)


def build_server(config: Config, catalogue: dict[str, Metric] | None = None) -> MCPServer:
    catalogue = catalogue or load_catalogue()
    manifest = load_manifest(config.dbt_target)
    problems = against_manifest(catalogue, manifest)
    if problems:  # e.g. a PII column exposed as a dimension (GR-04): refuse to serve
        raise CatalogueError("Catalogue does not match the dbt marts:\n" + "\n".join(problems))
    service = QueryService(config, catalogue, load_glossary(catalogue), manifest)
    server = MCPServer(
        name="governed-analytics",
        version=VERSION,
        instructions=INSTRUCTIONS,
        middleware=[TraceMiddleware(config.log_dir / "traces.jsonl", config.persona, VERSION, config.transport)],
        lifespan=_retention_lifespan(config),
    )

    # Enums from the catalogue: the model can only ask for what exists (mcp-tool-design step 2).
    MetricName = Literal[tuple(sorted(catalogue))]
    Dimension = Literal[tuple(sorted({d for m in catalogue.values() for d in m.allowed_dimensions}))]

    class FilterArg(BaseModel):
        column: Dimension
        op: Literal[OPS]
        value: str | int | float | bool | list[str | int | float | bool] | None = Field(
            default=None, description="A single value; a list for in/not_in; omit for is_null/is_not_null."
        )

    @server.tool(
        name="list_metrics",
        description=(
            "List the governed metrics, or, with `term`, the metrics an everyday word could mean "
            "(for example 'revenue' or 'sales'). Call this when the user's wording could fit more than one metric."
        ),
    )
    async def list_metrics(
        term: Annotated[
            str | None, Field(description="An everyday word from the user's question, e.g. 'revenue'.")
        ] = None,
    ) -> dict[str, Any]:
        return service.list_metrics(term)

    @server.tool(
        name="describe_metric",
        description="Explain exactly what one metric means: definition, what is always included or excluded, grains and dimensions.",
    )
    async def describe_metric(
        metric: Annotated[MetricName, Field(description="The metric to explain.")],
    ) -> dict[str, Any]:
        try:
            return service.describe_metric(metric)
        except QueryError as e:
            raise ToolError(str(e)) from e

    @server.tool(name="query_metric", description=_describe(catalogue))
    async def query_metric(
        metric: Annotated[MetricName, Field(description="The governed metric to query.")],
        time_grain: Annotated[Literal[GRAINS], Field(description="One row per period of this length.")],
        period: Annotated[
            Literal[RELATIVE_PERIODS] | None,
            Field(description="A relative period, resolved by the server. Use this OR start and end."),
        ] = None,
        start: Annotated[dt.date | None, Field(description="First day, inclusive (ISO date).")] = None,
        end: Annotated[dt.date | None, Field(description="Day after the last day, exclusive (ISO date).")] = None,
        dimensions: Annotated[list[Dimension] | None, Field(description="Columns to group by.")] = None,
        filters: Annotated[list[FilterArg] | None, Field(description="Conditions on dimensions.")] = None,
        question: Annotated[
            str | None,
            Field(description="The user's question in your words. Logged briefly for improving the catalogue; it does not affect the result."),
        ] = None,
    ) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            return service.query_metric(
                metric=metric,
                time_grain=time_grain,
                period=period,
                start=start,
                end=end,
                dimensions=dimensions,
                filters=[f.model_dump() for f in filters or ()],
            )

        try:
            return await anyio.to_thread.run_sync(run)
        except QueryError as e:
            raise ToolError(str(e)) from e  # an is_error result the model can act on (step 5)

    # The escape hatch (mcp-tool-design step 8): guarded, labelled, receipted, never silent.
    @server.tool(name="explore_sql", description=_describe_explore(manifest))
    async def explore_sql(
        sql: Annotated[str, Field(description="One DuckDB SELECT over the marts listed above.")],
        question: Annotated[
            str | None,
            Field(description="The user's question in your words. Logged briefly to find metrics worth certifying."),
        ] = None,
    ) -> dict[str, Any]:
        try:
            return await anyio.to_thread.run_sync(lambda: service.explore_sql(sql))
        except QueryError as e:
            raise ToolError(str(e)) from e

    @server.tool(
        name="request_certification",
        description=(
            "Ask BI to consider certifying a metric for an exploratory result the user wants to rely on. "
            "Only after the user agrees. Logs the request; it does not change the result's label."
        ),
    )
    async def request_certification(
        receipt_id: Annotated[str, Field(pattern=r"^rcpt_[0-9A-Z]{26}$", description="The exploratory result's receipt ID.")],
        question_shape: Annotated[
            str,
            Field(
                max_length=300,
                description="The question in general terms, e.g. 'average days from listing to sale, by region'. "
                "No names, IDs or other personal details.",
            ),
        ],
    ) -> dict[str, Any]:
        try:
            return service.request_certification(receipt_id, question_shape)
        except QueryError as e:
            raise ToolError(str(e)) from e

    return server


def _retention_lifespan(config: Config):
    """GR-04 retention, enforced by the server: purge at start-up, then on a timer while it runs."""

    def purge() -> None:
        spans, requests = purge_all(config.log_dir, dt.datetime.now(dt.UTC), config.retention_days)
        if spans or requests:
            logging.getLogger(__name__).info("Retention: purged %d span(s), %d request(s)", spans, requests)

    async def every_interval() -> None:
        while True:
            await anyio.sleep(config.purge_interval_seconds)
            await anyio.to_thread.run_sync(purge)

    @contextlib.asynccontextmanager
    async def lifespan(server: MCPServer):
        purge()
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(every_interval)
            yield {}
            tasks.cancel_scope.cancel()

    return lifespan


def _describe_explore(manifest: Manifest) -> str:
    lines = [
        "Answer a data question that no governed metric covers, with your own read-only SQL. Use "
        "list_metrics first: if a governed metric fits, use query_metric instead. Results are always "
        "labelled exploratory and get a receipt; say so to the user.",
        "",
        "Rules: one SELECT (CTEs and joins are fine), only the marts below, no table functions or file "
        "access, no personal-data columns, and no SELECT * on a table that has them. Results are capped.",
        "",
        "Marts and their columns:",
    ]
    for model in sorted(manifest.columns):
        columns = sorted(manifest.columns[model] - manifest.pii[model])
        lines.append(f"- marts.{model}: {', '.join(columns)}")
    return "\n".join(lines)


def _describe(catalogue: dict[str, Metric]) -> str:
    lines = [
        "Get a governed business metric. The server compiles the SQL, so the same request always "
        "gives the same number. Results include the metric definition, a certified or exploratory "
        "label and a receipt ID; tell the user all three.",
        "",
        "Metrics:",
    ]
    for m in sorted(catalogue.values(), key=lambda m: m.name):
        label = "certified" if m.certified else "uncertified"
        first_sentence = m.description.split(". ")[0].rstrip(".")
        lines.append(f"- {m.name} ({m.unit}, {label}, v{m.version}): {first_sentence}.")
    lines += [
        "",
        "If the user's words could mean more than one metric (for example 'revenue'), call "
        "list_metrics with that term first, then ask or say which one you chose and why. "
        "Prefer `period` for relative dates.",
    ]
    return "\n".join(lines)


def main() -> None:
    build_server(Config.from_env(transport="pipe")).run()


if __name__ == "__main__":
    main()
