# Model-in-the-loop evals: claude-haiku-5-5

Run on 2026-11-16 at commit `459e1cc`, effort `medium`, governed-analytics skill v0.2.0. 3 runs per question per condition; a check passes at 2 of 3. Judged by fixed rules ([`model_judge.py`](../../../src/governed_analytics/model_judge.py)), no model. Cost about $0.03.

| Question | Check | Without skill | With skill |
|---|---|---|---|
| GQ-03 "What was revenue last quarter?" | lists the options or names its choice | 3/3 pass | 3/3 pass |
| GQ-04 "What was our revenue after refunds last quarter?" | names the metric | 3/3 pass | 3/3 pass |
| GQ-10 "What were sales last month?" | lists the options or names its choice | 3/3 pass | 3/3 pass |
| GQ-15 "How many days does a listing take to sell, on average?" | offers certification | 3/3 pass | 3/3 pass |
| GQ-15 "How many days does a listing take to sell, on average?" | asks directly | 0/3 fail | 2/3 pass |
| **Checks passed** | | **4 of 5** | **5 of 5** |

## Rule revision, 16 Nov 2026

GQ-15 first had one check, *says exploratory and offers certification*, which counted an offer only when it was phrased as a question. Reading the first transcripts showed that every run mentioned certification, and that the runs it failed offered it as a statement instead. The check was split in two after reading the transcripts: **offers certification** also counts a statement that the assistant can request or ask for certification; **asks directly** is the original rule, unchanged. The same transcripts were re-judged; the model was not re-run ([ADR-008](../../../../../docs/adr/008-model-in-the-loop-evals.md#revision)).

| Rule | Without skill | With skill |
|---|---|---|
| GQ-15 Original: one check, offer must be a question | 0/3 fail | 2/3 pass |
| GQ-15 Revised: offers certification | 3/3 pass | 3/3 pass |
| GQ-15 Revised: asks directly | 0/3 fail | 2/3 pass |

All checks passed: originally 3 of 4 without the skill and 4 of 4 with it; after the revision 4 of 5 and 5 of 5.

The statements the original rule failed:

- GQ-15, with skill, run 2: "I can ask BI to consider certifying a time-to-sell metric if you'll rely on this figure again."
- GQ-15, without skill, run 1: "I can submit a certification request for this result if you want that."
- GQ-15, without skill, run 2: "If you plan to rely on this number regularly, I can ask BI to consider certifying it."
- GQ-15, without skill, run 3: "If you'll rely on this number regularly, I can ask BI to consider certifying it."

## Why runs failed

- GQ-15, asks directly, without skill, run 1: reply does not offer certification as a question
- GQ-15, asks directly, without skill, run 2: reply does not offer certification as a question
- GQ-15, asks directly, without skill, run 3: reply does not offer certification as a question
- GQ-15, asks directly, with skill, run 2: reply does not offer certification as a question

Transcripts are in [`transcripts/`](transcripts/). They go stale when the tools or the skill change: `python -m governed_analytics.model_evals check` warns when their fingerprints differ from the current ones.
