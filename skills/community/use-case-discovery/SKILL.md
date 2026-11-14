---
name: use-case-discovery
description: >-
  Interview a business team and score where AI could help them. Use when
  starting work with a new team, when someone asks what to automate, or when
  several ideas compete and one must be picked for a proof of concept.
metadata:
  version: 0.1.0
  owner: ai-enablement
  requirements: [GR-01, GR-04]
---

# Use-case discovery

You are mapping a team's **recurring work**, not promising a build. The goal is one opportunity the team can pilot and then run themselves, chosen with a score they can see.

## When to use

- First conversation with a team about AI.
- A team has a pain point but no agreed solution.
- Several ideas compete for one proof of concept.

## When not to use

- The use case is already chosen and you are designing the tool: use `mcp-tool-design`.
- Someone just wants a number: use `governed-analytics`.

## Inputs

- A team and at least one person who does the work (not only their manager).
- About 30 minutes with them. If you can't get time with real users, write the brief from stated assumptions and label every one.

## Steps

1. **Frame the session.** Say what you are doing: mapping repeated work to find one thing worth piloting. Say what you are not doing: committing to build anything.
   *Done when:* the team knows the output is a one-page brief they will review.

2. **Interview.** Ask these, following up on anything repeated, slow or double-checked:
   1. What do you do every week that feels like the same steps again?
   2. Which decisions wait on someone else's numbers or answers?
   3. What do you send back to be checked, and why?
   4. Where does the data for that come from, and who owns it?
   5. How long does it take, how often, and who waits for it?
   6. What happens if it's wrong? Who notices?
   7. Does it involve personal data about customers or colleagues?
   8. If it worked, who on your team would run it day to day?

   Record each opportunity as one row: task, frequency, time, data source, data owner, who runs it.
   *Done when:* you have at least five rows, or the team has run out of examples, and every row has a data source and owner (or "unknown", which is a finding in itself).

3. **Score each row** with the *Rubric*, and set any *Stop flags*.
   *Done when:* every row has four scores, a total and its flags, each with a one-line reason.

4. **Pick the pilot.** Choose the highest total among rows with no stop flag; on a tie, choose the higher *Safety*. For the pick, write:
   - the access it needs, stated as read-only APIs or MCP tools ([GR-01](../../../requirements/GR-01-read-only-access.md));
   - which columns or fields hold personal data ([GR-04](../../../requirements/GR-04-pii-protection.md));
   - one success measure the team cares about;
   - the person in the team who will own it.

   *Done when:* the pick has all four.

5. **Play it back.** Show the brief to the team and correct it with them.
   *Done when:* someone from the team confirms the pick and the owner, or the brief records why not.

## Rubric

Score each criterion from 1 to 3. The total is out of 12.

| Criterion | 3 | 2 | 1 |
|---|---|---|---|
| **Value** | Weekly or more, and over an hour each time, or it holds up a decision | Monthly, or under an hour | Rare or minor |
| **Data readiness** | In a governed source with an owner, reachable read-only | Reachable, but undocumented or without an owner | Spreadsheets, email or unknown |
| **Safety** | Internal and easy to correct; no personal data | Feeds decisions, but a person checks the output | Reported externally, a record of truth, or touches personal data |
| **Self-run** | The team can run it after a short handover | Needs occasional help from a specialist | Needs engineers to run it |

### Stop flags

A stop flag takes the row out of the pilot, whatever its score, and names who to talk to first:

| Flag | Talk to |
|---|---|
| Needs write access to a system of record | IT |
| Needs personal data to be returned, not just filtered out | IT (security) |
| Must run unattended for many teams from day one | Tool enablement |
| Needs a trained model, monitoring or an SLA | ML / data science |

## Output

A one-page discovery brief, saved next to the example it leads to (for example `examples/<name>/discovery-brief.md`):

1. **Team and date.** Who was interviewed, by role. Mark the brief *assumed* if no real users were interviewed.
2. **Opportunities.** The scored table: task, the four scores, total, stop flags and reasons.
3. **Pick.** The chosen opportunity with its access, personal data, success measure and owner.
4. **Not now.** Each flagged row and who to talk to.
5. **Assumptions.** Everything not heard directly from the team.

Example scored row:

| Task | Value | Data | Safety | Self-run | Total | Flags |
|---|---|---|---|---|---|---|
| Re-check quarterly revenue with BI before it goes to leadership | 3 | 3 | 2 | 3 | 11 | None |

## Guardrails

The access spec in step 4 states the pilot's needs in terms of [GR-01](../../../requirements/GR-01-read-only-access.md) and [GR-04](../../../requirements/GR-04-pii-protection.md), so later design and review start from them. This skill enforces nothing itself.

## Evals

This is a process skill, so its eval is evidence of use ([CONTRIBUTING](../../../CONTRIBUTING.md#the-promotion-bar)): the discovery brief behind the worked example, and a passing `guardrail-review` report on the build that came from it.
