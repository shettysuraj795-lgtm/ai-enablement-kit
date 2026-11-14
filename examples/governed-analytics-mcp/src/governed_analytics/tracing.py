"""One span per tool call, as defined by docs/contracts/trace-log.md (GR-07).

Tracing is MCP middleware, so it wraps the dispatcher rather than each tool
(mcp-tool-design step 7): calls that fail argument validation or name an
unknown tool are traced too. Tool code adds detail with `annotate`, and
never decides whether a span is written.
"""

from __future__ import annotations

import contextvars
import datetime as dt
import re
import secrets
from pathlib import Path
from typing import Any

from mcp.shared.exceptions import MCPError
from pydantic import ValidationError

from governed_analytics.receipts import append

SERVICE_NAME = "governed-analytics-mcp"

_current: contextvars.ContextVar[dict | None] = contextvars.ContextVar("span", default=None)
_TRACEPARENT = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")


def annotate(**attributes: Any) -> None:
    """Add attributes to the current tool call's span; a no-op outside one."""
    span = _current.get()
    if span is not None:
        span["attributes"].update(attributes)


def guardrail_hit(requirement_id: str) -> None:
    span = _current.get()
    if span is not None:
        span["attributes"]["kit.guardrail.hits"].append(requirement_id)


def current_ids() -> tuple[str | None, str | None]:
    span = _current.get()
    return (span["trace_id"], span["span_id"]) if span else (None, None)


class TraceMiddleware:
    def __init__(self, path: Path, persona: str, service_version: str, transport: str | None):
        self._path = path
        self._persona = persona
        self._service_version = service_version
        self._transport = transport
        # No traceparent from the client: one trace per server process, which
        # for stdio is one MCP session.
        self._session_trace_id = secrets.token_hex(16)

    async def __call__(self, ctx, call_next):
        if ctx.method != "tools/call":
            return await call_next(ctx)

        params = dict(ctx.params or {})
        arguments = params.get("arguments")
        arguments = dict(arguments) if isinstance(arguments, dict) else {}
        question = arguments.pop("question", None)  # kit.question only, never the arguments
        trace_id, parent_span_id = self._trace_context(ctx.meta)

        attributes: dict[str, Any] = {
            "mcp.method.name": "tools/call",
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": params.get("name"),
            "gen_ai.tool.call.arguments": arguments,
            "jsonrpc.request.id": None if ctx.request_id is None else str(ctx.request_id),
            "mcp.protocol.version": ctx.protocol_version,
            "network.transport": self._transport,
            "kit.persona": self._persona,
            "kit.guardrail.hits": [],
            "kit.question": question if isinstance(question, str) else None,
        }
        span = {
            "trace_id": trace_id,
            "span_id": secrets.token_hex(8),
            "parent_span_id": parent_span_id,
            "name": f"tools/call {params.get('name')}",
            "kind": "SERVER",
            "start_time": _now(),
            "end_time": None,
            "status": {"code": "OK", "message": None},
            "resource": {"service.name": SERVICE_NAME, "service.version": self._service_version},
            "attributes": attributes,
        }
        token = _current.set(span)
        try:
            result = await call_next(ctx)
            if _is_error(result):
                message = _first_text(result)
                span["status"] = {"code": "ERROR", "message": message}
                attributes["error.type"] = "tool_error"
                # A crash reaches the model as the bare "Error executing tool <name>";
                # anything longer is an anticipated error or a schema rejection.
                crashed = message == f"Error executing tool {params.get('name')}"
                attributes.setdefault("kit.error.reason", "internal" if crashed else "invalid_intent")
            return result
        except MCPError as e:
            span["status"] = {"code": "ERROR", "message": e.error.message}
            attributes["error.type"] = str(e.error.code)
            raise
        except ValidationError:
            span["status"] = {"code": "ERROR", "message": "Invalid request parameters"}
            attributes["error.type"] = "-32602"
            raise
        finally:
            _current.reset(token)
            span["end_time"] = _now()
            span["attributes"] = {k: v for k, v in attributes.items() if v is not None}
            append(self._path, span)

    def _trace_context(self, meta: Any) -> tuple[str, str | None]:
        if hasattr(meta, "model_dump"):
            meta = meta.model_dump(by_alias=True)
        match = _TRACEPARENT.match(str((meta or {}).get("traceparent", "")))
        return (match[1], match[2]) if match else (self._session_trace_id, None)


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _is_error(result: Any) -> bool:
    if isinstance(result, dict):
        return bool(result.get("is_error") or result.get("isError"))
    return bool(getattr(result, "is_error", False))


def _first_text(result: Any) -> str:
    content = result.get("content", []) if isinstance(result, dict) else getattr(result, "content", [])
    for item in content or []:
        text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
        if text:
            return text
    return ""
