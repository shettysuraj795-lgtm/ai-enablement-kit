# ADR-002: Receipts and replay as the unit of trust

- **Status:** Accepted, 14 Nov 2026
- **Context:** When a self-serve number is questioned, BI currently rebuilds it from scratch. Lowering the model's temperature does not help: the drift comes from different interpretations of a question, not from sampling noise.
- **Decision:** Every data-returning response carries a receipt ([contract](../contracts/receipt.md)) that pins the structured intent, the metric and compiler versions, the exact SQL, the dbt run it ran on and a canonical result hash. A replay command checks the definition and the data separately.
- **Alternatives:** Caching answers by question text (two phrasings of one question miss the cache, and one phrasing can mean two things); logging prompts and responses only (they show what was said, not how the number was produced).
- **Consequences:** Checking a chart becomes one command. Replay can honestly tell "the definition changed" apart from "the data changed". Exact replay of past results needs retained snapshots, which is a handover item. The SQL fingerprint gives the promotion loop something to count.
