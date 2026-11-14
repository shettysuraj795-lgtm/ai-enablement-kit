# Contributing

Skills in this kit are governed the same way as metrics. Anyone can add one, but only some are trusted by default. This guide explains the two tiers and what it takes to move a skill from one to the other.

## Two tiers

| | Community | Certified |
|---|---|---|
| Folder | `skills/community/<name>/` | `skills/certified/<name>/` |
| Who can add | Anyone, through a pull request | Promotion only (see below) |
| Review | A maintainer checks it follows the template and is not harmful | Code owners for `skills/certified/` must approve |
| Evals | Encouraged | Required, and must pass in CI |
| Shown by `start-here` | Only when asked for, labelled *community* | By default |
| Promise to users | "Someone found this useful" | "This is maintained, tested and owned" |

The tier lives in the folder path, not in a frontmatter flag. That makes the tier visible wherever a path appears, and lets `CODEOWNERS` protect the certified folder.

## Adding a community skill

1. Copy [`templates/SKILL_TEMPLATE.md`](templates/SKILL_TEMPLATE.md) to `skills/community/<name>/SKILL.md`.
2. Fill in every section. Delete the guidance text.
3. If the skill touches a hard guardrail, list its IDs (for example `GR-04`). A skill can help people follow a guardrail, but it can never be the only control for it: see [`requirements/`](requirements/).
4. Open a pull request.

## The promotion bar

A community skill becomes certified when it meets all three of these:

1. **Owner.** A named team or role, set in `metadata.owner`, that answers questions, reviews changes and keeps the evals passing. "Everyone" is not an owner.
2. **Eval.** At least five cases in `skills/<tier>/<name>/evals/` that pass in CI. At least one case must show the skill changes behaviour, meaning the output differs in the intended way from a run without the skill.
3. **Version.** A semantic version in `metadata.version` and a `CHANGELOG.md` next to the skill. The major version goes up when the skill's behaviour changes in a way users would notice.

To promote, open a pull request that moves the folder from `community/` to `certified/` and links the passing eval run. The code owners approve or decline it, and they give a reason if they decline.

## Staying certified

A certified skill is moved back to `community/` if any of these happen:

- its evals fail on `main` and are not fixed within one release;
- its owner leaves and nobody takes it over;
- it duplicates a newer certified skill.

Demotion is a normal pull request, not a punishment. It keeps the label "certified" meaningful.

## Conventions

- British English.
- Small commits with clear messages.
- Record significant decisions as an ADR in [`docs/adr/`](docs/adr/).
- Never commit credentials, real customer data or personal data.
