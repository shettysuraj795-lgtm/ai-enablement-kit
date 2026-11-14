---
# Agent Skills frontmatter. `name` and `description` are what the assistant sees
# when deciding whether to load the skill, so the description must say when to use it.
name: skill-name              # lowercase, hyphens, matches the folder name
description: >-
  One or two sentences: what the skill does and when to use it. Name the
  trigger phrases a user would actually say.
metadata:
  version: 0.1.0              # semver; major bump when behaviour changes noticeably
  owner: team-or-role         # required for certified; "everyone" is not an owner
  requirements: []            # hard guardrails this skill relies on, e.g. [GR-05, GR-06]
---

# Skill name

<!-- Delete every HTML comment before opening a pull request. -->

## When to use

<!-- The situations this skill is for, in the user's words. -->

## When not to use

<!-- Nearby situations that belong to another skill, and which skill to use instead. -->

## Inputs

<!-- What the skill needs from the user or the environment before it starts. Say what to ask for if it is missing. -->

## Steps

<!-- Numbered, imperative steps. Each step should produce something checkable. -->

1. …
2. …

## Output

<!-- The exact shape of what the skill produces: a file, a table, a message. Include a short example. -->

## Guardrails

<!--
List the hard guardrails (GR-xx) this skill relies on and what the skill does
when one of them blocks it. A skill guides behaviour; it never replaces the
control in requirements/. If no guardrail applies, write "None".
-->

## Evals

<!--
Where the eval cases live (evals/ next to this file) and what they check.
Certified skills need at least five passing cases, including one that shows
the skill changes behaviour compared with a run without it.
-->
