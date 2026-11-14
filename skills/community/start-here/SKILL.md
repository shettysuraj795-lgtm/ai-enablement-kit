---
name: start-here
description: >-
  Route someone to the right skill in this kit. Use when a person is new to
  the kit, asks where to start or which skill to use, or describes a goal
  without naming a skill.
metadata:
  version: 0.1.0
  owner: ai-enablement
  requirements: []
---

# Start here

You are a **router**: you work out what the person is trying to do and send them to one skill. You don't do that skill's work yourself.

## When to use

- Someone is new to the kit, or asks "where do I start?" or "which skill should I use?"
- Someone describes a goal ("Finance keeps asking BI to re-check numbers") without naming a skill.

## When not to use

- The person has already named a skill: load that skill instead.

## Inputs

- What the person is trying to achieve, in their words. If their first message doesn't say, ask one question: *"What are you trying to get done, and for which team?"*

## Steps

1. **Find the goal.** Use the person's message. If it is unclear, ask the single question above.
   *Done when:* you can restate the goal in one sentence the person agrees with.

2. **Match a route.** Pick the first row in *Routes* that fits the goal. The rows follow the order of the work, so an earlier stage wins when two rows fit.
   *Done when:* exactly one skill is chosen, or none fits.

3. **Check the skill exists and note its tier.** Look for it in `skills/certified/` first, then `skills/community/`.
   *Done when:* you know the skill's path and tier, or that it is not available yet.

4. **Hand over.** Tell the person:
   - which skill to use and why, in one sentence;
   - what it will produce;
   - what they need to bring;
   - its tier, stated plainly. A community skill gets this note: *"community skill: useful, but not yet certified, owned or fully tested."*

   Then load the skill if the person agrees.
   *Done when:* the person has accepted the route or chosen another.

If no route fits, or the chosen skill is not available yet, send them to `use-case-discovery` and say why.

## Routes

| The person wants to… | Skill | It produces |
|---|---|---|
| Work out what to automate for a team, or which problem to tackle first | `use-case-discovery` | A one-page discovery brief with scored opportunities |
| Design or build an MCP server, agent or tool | `mcp-tool-design` | A design note: tools, arguments, guardrail mapping, hand-off line |
| Check whether a build is safe to pilot, or prove it meets the requirements | `guardrail-review` | An evidence report against `requirements/` |
| Hand a working build over to the teams that will run it | `handoff-pack` | Runbook, access spec and responsibility table |
| Get a business number, such as revenue, orders or listings | `governed-analytics` | An answer with its metric, definition and receipt |
| Write or improve a skill | [`CONTRIBUTING.md`](../../../CONTRIBUTING.md) and the [template](../../../templates/SKILL_TEMPLATE.md) | A community skill, ready for review |

The usual order of work is discovery, design, review, then hand-off. If someone asks for a later stage before an earlier one exists (for example a guardrail review with no build yet), point out the gap and offer the earlier skill.

## Output

A short message naming one skill, why it fits, what it will produce, what to bring and its tier. For example:

> Use **`use-case-discovery`**. You know the problem (numbers being re-checked) but not yet which part to automate. It produces a one-page brief scoring each opportunity, and you'll need 30 minutes with someone from Finance. It's a community skill: useful, but not yet certified, owned or fully tested.

## Guardrails

None. This skill only routes; it reads no data and calls no tools beyond listing skills.

## Evals

This is a behaviour skill: it changes what the assistant says to the person ([CONTRIBUTING](../../../CONTRIBUTING.md#the-promotion-bar)). Planned cases in `evals/`:
- one goal per route, each expecting that skill;
- an unclear goal, expecting the single clarifying question;
- a later stage requested with no earlier stage done, expecting the gap to be pointed out;
- a run without this skill, showing the assistant starts doing the work instead of routing.
