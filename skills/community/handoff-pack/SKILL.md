---
name: handoff-pack
description: >-
  Hand a working build over to the teams that will run it: a one-page runbook
  for the business team, an access spec for IT and a responsibility table
  across BI, ML / data science, Tool enablement and IT. Use when a proof of
  concept has passed its guardrail review and is ready to leave the builder.
metadata:
  version: 0.1.0
  owner: ai-enablement
  requirements: [GR-01, GR-02, GR-03, GR-04, GR-05, GR-06, GR-07, GR-08]
---

# Hand-off pack

A proof of concept succeeds when its builder is no longer needed. You write the three documents that let each receiving team **own** their part without asking you: the people who use it, the people who grant its access, and the people who run, monitor and change it.

## When to use

- A build has a passing guardrail review and a team is about to rely on it.
- Ownership of a build is moving between teams.

## When not to use

- The build has no passing `guardrail-review` report. Run that first. Handing over an unreviewed build hands over unknown risk.
- You are still deciding what to build: use `use-case-discovery`.

## Inputs

- The build's folder and its design note (for example `DESIGN.md`): tools, configuration, known limits and hand-off items.
- The latest passing guardrail report and the commit it reviewed.
- [`requirements/README.md`](../../../requirements/README.md) for each requirement's owner.
- The receiving business team and the persona it uses. If either is assumed rather than confirmed, say so in each document.

## Steps

1. **Confirm readiness.** Find the latest guardrail report for the build. If its verdict isn't *Pass*, stop and say why.
   *Done when:* you have the report link and the commit it reviewed.

2. **Take inventory.** From the design note and the code, list:
   - what runs and what it reads and writes;
   - every configuration setting;
   - logs and their retention;
   - every known limit and hand-off item.

   *Done when:* each item is assigned to the runbook, the access spec or the responsibility table.

3. **Write the runbook** for the business team, one page, in their language:
   - what the build is for;
   - how to ask;
   - how to read an answer (labels, receipts);
   - what to do when there is no answer, the answer is exploratory, or a number looks wrong;
   - what it will not do;
   - privacy;
   - who to contact, by role.

   *Done when:* it fits on one page, every user-facing behaviour is covered, and no internal term is left unexplained.

4. **Write the access spec** for IT. For every system the build touches, give:
   - the access needed and its scope;
   - why, citing the tool and the GR ID;
   - what the proof of concept uses today;
   - what production should use.

   Add data classification, logs and retention, identity, network and secrets, and the decisions only IT can make.
   *Done when:* every privilege maps to a tool and a GR ID, and every open decision is listed.

5. **Write the responsibility table.**
   - **Rows:** the ongoing activities: definitions, certification, evals, monitoring, packaging, access, retention, incidents, reviews, onboarding and decommissioning.
   - **Columns:** the business team, BI, ML / data science, Tool enablement, IT and the kit maintainer during transition.
   - **Cells:** RACI (Responsible, Accountable, Consulted, Informed).

   *Done when:* each row has exactly one Accountable team, each GR owner matches `requirements/README.md`, and every hand-off item from the design note appears.

6. **List open questions** per team. Don't invent answers.
   *Done when:* each document ends with its open questions, or says "none".

## Output

Three files in `examples/<build>/handoff/`:

| File | Audience | Length |
|---|---|---|
| `runbook-<team>.md` | The business team | One page |
| `access-spec.md` | IT | As long as the systems need |
| `responsibilities.md` | All receiving teams | One table plus the requirement owners |

Each file names the build, the reviewed commit and the guardrail report it relies on.

## Guardrails

The pack changes no control. It records who owns each requirement after hand-off, and what IT must do so the production controls are at least as strong as the proof of concept's. Example: a read-only warehouse role replaces the read-only file connection for GR-01.

## Evals

This is a process skill, so its eval is evidence of use ([CONTRIBUTING](../../../CONTRIBUTING.md#the-promotion-bar)): a pack produced for a build with a passing guardrail review, checked by at least one receiving team.
