# ADR-006: What counts as guardrail evidence

- **Status:** Accepted, 14 Nov 2026
- **Context:** A passing `guardrail-review` report now promotes design and process skills, and gates pilots. If "met" could mean "the code looks right" or "the prompt asks for it", a passing report would be easy to produce and would prove little.
- **Decision:** A requirement is *Met* only when its control sits in code, configuration or CI (cited as `file:line`), and when its verification command was actually run on one pinned commit and passed. A control that lives only in a skill or prompt is *Not met*. There is no "partly met". The reviewer reports without fixing, so the evidence matches the commit.
- **Alternatives:** Review by reading code (faster, but not reproducible); a "partly met" status (softens failures that matter); fixing during review (changes the commit being evidenced).
- **Consequences:** Reports are slower to produce, but anyone can rerun them. Every requirement needs a runnable check before it can pass, which keeps `requirements/` honest. A report describes one commit and goes stale after changes to a control.
