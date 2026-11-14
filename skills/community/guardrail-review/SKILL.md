---
name: guardrail-review
description: >-
  Check a build against the kit's hard guardrails (requirements/GR-xx) and
  write an evidence report. Use before a pilot, before promoting a skill, when
  someone asks whether a build is safe or compliant, or after a change to a
  guardrail control.
metadata:
  version: 0.1.0
  owner: ai-enablement
  requirements: [GR-01, GR-02, GR-03, GR-04, GR-05, GR-06, GR-07, GR-08]
---

# Guardrail review

You are an **auditor**. You review one fixed commit, run the checks yourself and report what you saw. You don't fix anything during the review: a fix changes the commit, and the evidence would no longer describe it.

## When to use

- Before a build is piloted with a team.
- To produce the evidence a design or process skill needs for promotion ([CONTRIBUTING](../../../CONTRIBUTING.md#the-promotion-bar)).
- After any change to a control named in `requirements/`.

## When not to use

- The build doesn't exist yet: use `mcp-tool-design`.
- You want to change a requirement: that goes through the requirement's owner, not a review.

## Inputs

- The build's path and the commit to review. If none is given, use the current `HEAD` and record its SHA.
- A clean working tree. If there are uncommitted changes, stop and ask: the report must describe a commit someone else can check out.

## Steps

1. **Pin the scope.** Record the build path, commit SHA, date and reviewer. List every requirement in [`requirements/README.md`](../../../requirements/README.md). Mark a requirement *Not applicable* only with a one-line reason, such as "no tool returns data".
   *Done when:* every GR ID is listed with *In scope* or *Not applicable* and a reason.

2. **Find the control.** For each in-scope requirement, locate the code that does what its *Enforced by* line says, and cite it as `file:line`.
   *Done when:* each in-scope requirement has a cited control, or is noted as having none.

3. **Run the verification.** Run each requirement's *How to verify* command exactly, for example `pytest -m gr03`. Record the command, the exit code and the pass and fail counts. Reading the tests doesn't count as running them.
   *Done when:* every in-scope requirement has a command you ran and its recorded result.

4. **Test hard against soft.** For each requirement, ask: if the assistant ignored every skill and prompt, would the control still hold? If the only control is a skill, a prompt or a tool description, the requirement is *Not met*.
   *Done when:* each requirement's control is confirmed to sit in code, configuration or CI.

5. **Cross-check the trace log.** In the trace log from the verification run, confirm that each blocked or capped call has a span whose `kit.guardrail.hits` names the right GR ID ([trace log contract](../../../docs/contracts/trace-log.md)).
   *Done when:* every guardrail test that should log a hit has a matching span, or the gap is recorded under GR-07.

6. **Decide and write.** Give each requirement one status:
   - **Met:** a control in code, a verification that ran and passed, and steps 4 and 5 hold.
   - **Not met:** anything less. Say what is missing.
   - **Not applicable:** as recorded in step 1.

   The verdict is **Pass** only if every in-scope requirement is *Met*.
   *Done when:* the report is saved and every *Not met* names what would make it *Met*.

## Output

A report at `examples/<build>/reports/guardrail-review-<YYYY-MM-DD>.md`:

```markdown
# Guardrail review: <build>

- **Commit:** <sha>  **Date:** <date>  **Reviewer:** <role>
- **Verdict:** Pass | Fail (<n> of <m> in-scope requirements met)

| ID | Status | Control | Verification | Notes |
|---|---|---|---|---|
| GR-01 | Met | `server/db.py:14` read-only connection | `pytest -m gr01`: exit 0, 9 passed | |
| GR-03 | Not met | `server/caps.py:30` row cap | `pytest -m gr03`: exit 1, 1 failed | Timeout not enforced; truncation flag missing in trace |

## Not met: what would fix it
## Sign-off after handover
<one line per requirement: the owning team from requirements/README.md>
```

Each verification cell must be a command that another person can rerun on the same commit and see the same result.

## Guardrails

This skill checks every requirement in `requirements/`; it doesn't enforce any of them. A passing report is evidence about one commit, not a lasting certificate. Re-run it after any change to a control.

## Evals

This is a process skill, but it can't produce evidence about itself. Its eval is a report on the worked example that the owner of at least one requirement has checked by hand against the commit ([CONTRIBUTING](../../../CONTRIBUTING.md#the-promotion-bar), [ADR-006](../../../docs/adr/006-guardrail-evidence.md)).
