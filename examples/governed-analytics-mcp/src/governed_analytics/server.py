"""MCP server exposing governed metrics. Run with `python -m governed_analytics.server`.

A thin binding: argument types come from the catalogue, the work happens in
service.py, tracing in tracing.py.
"""

# No `from __future__ import annotations` here: the tool's argument types are
# built from the catalogue at runtime, and pydantic must see them as objects.

import datetime as dt
from typing import Annotated, Any, Literal

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from governed_analytics.catalogue import Metric, load_catalogue, load_glossary
from governed_analytics.intent import OPS
from governed_analytics.periods import RELATIVE_PERIODS
from governed_analytics.service import Config, QueryError, QueryService
from governed_analytics.tracing import TraceMiddleware

VERSION = "0.1.0"
GRAINS = ("day", "week", "month", "quarter", "year")

INSTRUCTIONS = (
    "Governed business metrics. Use list_metrics and describe_metric to choose a metric, answer with "
    "query_metric, and always report "
    "the metric name and version, whether the result is certified, the time range and the receipt ID."
)


def build_server(config: Config, catalogue: dict[str, Metric] | None = None) -> MCPServer:
    catalogue = catalogue or load_catalogue()
    service = QueryService(config, catalogue, load_glossary(catalogue))
    server = MCPServer(
        name="governed-analytics",
        version=VERSION,
        instructions=INSTRUCTIONS,
        middleware=[TraceMiddleware(config.log_dir / "traces.jsonl", config.persona, VERSION, config.transport)],
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

    return server


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
