# ADR-008: Model-in-the-loop evals run locally and are judged by fixed rules

- **Status:** Accepted, 16 Nov 2026
- **Context:** Four golden-question checks (GQ-03, GQ-04, GQ-10, GQ-15) are about what the assistant says, not what the tools return, so the tool-layer evals can only report them as `needs-model`. The `governed-analytics` skill exists for exactly these behaviours, and nothing yet showed whether it changes them. Calling a model costs money and needs a key, and an LLM judge would add a second model whose own variance hides the first's.
- **Decision:** `python -m governed_analytics.model_evals run` is a local command. It gives the model (a setting; by default the current Claude Haiku) the five real MCP tools, and asks each needs-model question three times with the skill as instructions and three times without. A check passes at 2 of 3 runs. Transcripts are judged by fixed rules in `model_judge.py`: which tools were called, whether metric names appear, whether the options were listed or the choice named, and whether certification was offered as a question. No model judges. The command prints an estimated cost first, stops if spend passes a cap, and stops at once if a call fails for billing reasons. Transcripts and a results table are committed. CI runs `model_evals check`, which re-judges the committed transcripts with the same rules and fails if the table doesn't match. CI never calls a model and holds no API key.
- **Alternatives:** A scheduled CI job with a repository secret (live results, but a standing cost and a secret to manage in a public repository); LLM-as-judge (catches paraphrases the rules miss, but is itself probabilistic and harder to audit); one run per condition (cheaper, but a single sample can't tell a habit from luck).
- **Consequences:** The results describe one model, one effort level and one version of the tools and skill. **Transcripts go stale when the tools or the skill change**: each records fingerprints of the tool definitions and the skill text, and `check` warns when they differ from today's, but re-running is a person's decision. Fixed rules are strict about wording (a reply that says "GMV" doesn't name `gross_merchandise_value`), so they can fail a good answer; the transcripts are committed so anyone can read why. Scheduled live evals, trend tracking and LLM-as-judge are deliberately not built here; they are an ML / data science hand-off.

## Revision

*16 Nov 2026, after the first run on `claude-haiku-5-5`.* GQ-15 first had one check, which counted a certification offer only when it was phrased as a question. Reading the transcripts showed that all six runs mentioned certification, and that the four runs it failed had offered it as a statement:

- without the skill, run 1: "I can submit a certification request for this result if you want that."
- without the skill, run 2: "If you plan to rely on this number regularly, I can ask BI to consider certifying it."
- without the skill, run 3: "If you'll rely on this number regularly, I can ask BI to consider certifying it."
- with the skill, run 2: "I can ask BI to consider certifying a time-to-sell metric if you'll rely on this figure again."

The check was split in two. **Offers certification** also counts a statement that the assistant can request or ask for certification. **Asks directly** is the original rule, unchanged. The committed transcripts were re-judged and the model was not re-run.

| GQ-15 | Without skill | With skill |
|---|---|---|
| Original rule: one check | 0/3, fail | 2/3, pass |
| Revised: offers certification | 3/3, pass | 3/3, pass |
| Revised: asks directly | 0/3, fail | 2/3, pass |

Overall, the original result was 3 of 4 checks passed without the skill and 4 of 4 with it. After the revision it is 4 of 5 and 5 of 5. With the skill or without it, the model offers certification. The skill's measurable effect on these four questions is that it asks the user directly. A rule changed after seeing the results can be tuned to favour either condition, so both readings are kept side by side in `results.md`, and the original rule survives as *asks directly*.
