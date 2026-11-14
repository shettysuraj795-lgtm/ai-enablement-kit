"""Shared helpers for tests that drive the MCP server against the real warehouse."""

from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest
from mcp import Client

from governed_analytics.server import build_server
from governed_analytics.service import Config

CONFIG = Config.from_env()
AS_OF = dt.date(2026, 11, 14)  # the golden questions' as-of date
LAST_QUARTER = {"metric": "net_merchandise_value", "time_grain": "quarter", "period": "last_quarter"}

needs_warehouse = pytest.mark.skipif(
    not (CONFIG.warehouse.exists() and (CONFIG.dbt_target / "run_results.json").exists()),
    reason="warehouse not built: run the generator and `dbt build`",
)


def make_config(log_dir: Path, **overrides) -> Config:
    defaults = {"persona": "finance_analyst", "as_of": AS_OF}
    return dataclasses.replace(CONFIG, log_dir=log_dir, **{**defaults, **overrides})


def call(config: Config, arguments: dict, tool: str = "query_metric"):
    return call_many(config, [(tool, arguments)])[0]


def call_many(config: Config, calls: list[tuple[str, dict]]):
    """Several tool calls in one MCP session."""

    async def go():
        async with Client(build_server(config)) as client:
            return [await client.call_tool(tool, arguments) for tool, arguments in calls]

    return asyncio.run(go())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
