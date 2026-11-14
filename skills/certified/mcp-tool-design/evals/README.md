# Evidence of use: mcp-tool-design

`mcp-tool-design` is a design skill, so its eval is evidence of use ([CONTRIBUTING](../../../../CONTRIBUTING.md#the-promotion-bar)): at least one build made with the skill, plus a passing `guardrail-review` report on that build.

| Evidence | Link |
|---|---|
| Build made with the skill | [`examples/governed-analytics-mcp/`](../../../../examples/governed-analytics-mcp/): an MCP server with five intent-named tools |
| Design note mapping each choice to a skill step | [`DESIGN.md`](../../../../examples/governed-analytics-mcp/DESIGN.md), *Where the skill shaped the build* |
| First guardrail review: **Fail**, 7 of 8 | [commit `7b9ae0a`](../../../../examples/governed-analytics-mcp/reports/guardrail-review-2026-11-14.md): GR-04 retention wasn't enforced |
| Second guardrail review: **Pass**, 8 of 8 | [commit `0251a6c`](../../../../examples/governed-analytics-mcp/reports/guardrail-review-2026-11-14-2.md): gap closed by server-side retention |
| CI on the passing commit | [run 43640713589](https://github.com/shettysuraj795-lgtm/ai-enablement-kit/actions/runs/43640713589) |

What the evidence shows about the skill: steps 1–9 each map to a concrete choice in the build. The guardrail controls the skill asks for in step 6 are each met with a cited control and a passing test. The failed first review is part of the evidence: the process caught a soft control and the fix made it hard.

If the linked build's latest guardrail report stops passing and isn't fixed within one release, this skill goes back to `community/`.
