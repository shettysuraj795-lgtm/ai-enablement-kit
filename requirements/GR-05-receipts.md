# GR-05: Every result has a replayable receipt

- **ID:** GR-05
- **Requirement:** Every tool response that returns data MUST include a receipt ID, and the receipt MUST be stored in the format defined in the [receipt contract](../docs/contracts/receipt.md). Replaying a receipt against the same data snapshot MUST reproduce its result hash.
- **Rationale:** A number nobody can trace is a number BI has to rebuild. A receipt turns "can you double-check this chart?" into one replay command.
- **Owner:** BI. Until handover: kit maintainer.
- **Enforced by:** The server writes the receipt before returning the result; a response without one is an error.
- **How to verify:** `pytest -m gr05` calls each data-returning tool, asserts a valid receipt is stored for every response, then replays each receipt and asserts the compiled SQL and result hash match.
