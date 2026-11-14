# ADR-000: A reusable kit, proven by one worked example

- **Status:** Accepted, 14 Nov 2026
- **Context:** Self-serve analytics drift is one instance of a wider pattern: an AI assistant makes work fast, and trust does not keep up. A one-off tool for one team would solve the instance but not the pattern, and would leave the builder as the bottleneck.
- **Decision:** Build a reusable kit (skills, hard guardrails, contribution tiers, contracts, ADRs) and prove it with one worked example, `examples/governed-analytics-mcp/`, built by following the kit's own skills.
- **Alternatives:** A standalone analytics assistant (faster to demo, but nothing to reuse); a kit with no example (nothing to show that it works).
- **Consequences:** Kit content must stay domain-neutral; anything specific to analytics lives under `examples/`. A second example in another domain is the test of whether the kit generalises. Each example is a proof of concept with a handover plan, not a production system.
