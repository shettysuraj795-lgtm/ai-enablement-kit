# GR-08: Certified metric definitions are change-controlled

- **ID:** GR-08
- **Requirement:** A certified metric MUST have an owner, a semantic version and at least one golden eval question. Any change to its `model`, `expression`, `time_dimension` or `filters` MUST increase its major version.
- **Rationale:** If a definition can change without a version change, two receipts with the same version can disagree, and reproducibility is lost without anyone noticing.
- **Owner:** BI. Until handover: kit maintainer.
- **Enforced by:** CI validates every metric file against the [metric contract](../docs/contracts/metric-definition.md) and compares definition fields with the main branch.
- **How to verify:** `pytest -m gr08` asserts that a certified metric without an owner, version or eval fails validation, and that changing `filters` without a major version bump fails the CI check.
