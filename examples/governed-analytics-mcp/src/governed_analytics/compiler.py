"""Compile a structured intent and one metric definition into SQL.

The model chooses the intent; this module turns it into SQL deterministically.
Same intent + same metric version + same COMPILER_VERSION must give
byte-identical SQL, because receipts and replay depend on it (ADR-002).
"""

from __future__ import annotations

from governed_analytics.catalogue import Metric
from governed_analytics.intent import Intent

COMPILER_VERSION = "0.1.0"

MARTS_SCHEMA = "marts"


class IntentError(ValueError):
    """The intent is not valid for the metric.

    The message is returned to the model as a tool error, so it must say what
    to do next: name the valid options (see skills/community/mcp-tool-design).
    """


def compile_intent(intent: Intent, metric: Metric) -> str:
    """Return the SQL that answers `intent` using `metric`.

    The expected format is pinned by tests/test_compiler.py; the first test is
    the worked example in docs/contracts/receipt.md.
    """
    raise NotImplementedError("Write me: see tests/test_compiler.py")
