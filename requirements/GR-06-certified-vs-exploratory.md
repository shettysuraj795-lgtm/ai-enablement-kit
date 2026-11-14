# GR-06: Every result is labelled certified or exploratory

- **ID:** GR-06
- **Requirement:** Every result MUST be labelled `certified` or `exploratory`. A result MAY be `certified` only if it was compiled from a metric with `certified: true` at the version recorded in its receipt. Results from `explore_sql` MUST always be `exploratory`.
- **Rationale:** Self-serve analysis is useful as long as everyone can see which numbers are governed. The label is what lets an exploratory answer exist without being mistaken for an official one.
- **Owner:** BI. Until handover: kit maintainer.
- **Enforced by:** The server sets the label from the catalogue; the assistant cannot set or override it.
- **How to verify:** `pytest -m gr06` asserts the label for a certified metric, an uncertified metric and an `explore_sql` query, and asserts the label in the receipt matches the label in the tool response and the trace span.
