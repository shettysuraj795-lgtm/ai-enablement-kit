# GR-07: Every tool call is traced

- **ID:** GR-07
- **Requirement:** Every tool call, including blocked and failed calls, MUST write exactly one span to the trace log in the format defined in the [trace log contract](../docs/contracts/trace-log.md).
- **Rationale:** Rollout success, guardrail hits and promotion candidates are all measured from this log. Missing the failures would hide exactly the calls worth looking at.
- **Owner:** ML / data science (monitoring). Until handover: kit maintainer.
- **Enforced by:** Tracing wraps the tool dispatcher, not individual tools, so a new tool is traced without extra code.
- **How to verify:** `pytest -m gr07` makes successful, blocked and erroring calls to every tool and asserts one valid span per call, with a matching `kit.receipt.id` where a receipt exists.
