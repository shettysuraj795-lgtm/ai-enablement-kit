# Runbook: governed numbers in Claude, for Finance

*Build:* governed-analytics MCP server, reviewed at commit `0251a6c` ([guardrail review: Pass](../reports/guardrail-review-2026-11-14-2.md)). *Assumption:* the persona is a finance analyst; the team and contact names below are roles until Finance confirms them.

**What it's for.** You ask Claude for a business figure and get the official one: the same number BI would give, with a reference that proves where it came from.

**How to ask.** Ask normally, and say the period: *"What was net merchandise value last quarter?"*, *"Refund rate by month for Q3"*, *"Take rate by dealer tier last quarter"*. "Last quarter" means the last complete calendar quarter.

**When a word could mean several things,** Claude asks you to choose. That's on purpose:

| You said | Options | Q3 2026 |
|---|---|---|
| revenue | Gross merchandise value: everything buyers paid, before refunds | €9,356,569.82 |
| | Net merchandise value: what buyers paid, after refunds | €8,743,316.38 |
| | Commission revenue: what the marketplace itself earned | €436,367.44 |

**Reading an answer.** Every answer gives four things. Keep them with the number when you share it.

- **Metric and version**, for example `net_merchandise_value v1.0.0`: the definition used.
- **Label.** *Certified* means it's an official definition, owned by BI. *Exploratory* means a one-off query, not official, so don't put it in a board pack as fact. Not every metric is certified: Claude tells you how many are when you ask what's available.
- **Time range**, for example 1 Jul to 30 Sep 2026. For "last quarter" or "last month", Claude says the date it worked the period out from. That's not the date of the data. If you want to know how current the data is, ask.
- **Reference for BI**, the answer's last line, for example `Reference for BI: rcpt_01M7…`. This is how BI can reproduce the exact figure. An answer with several figures lists one reference per figure in a footnote.

**When there's no official metric** (for example "days to sell"), Claude says so, answers with an *exploratory* query, and offers to ask BI to certify one. Say yes if you'll need the number again: your request goes into BI's queue.

**If a number looks wrong,** don't rebuild it in a spreadsheet. Send the reference to BI. They run one replay command, which tells them whether the definition changed, the data changed since, or something is wrong.

**What it won't do.** It won't show anything about individual buyers, change any data, read raw source tables, return more than 1,000 rows, or run a query longer than 30 seconds. If you hit a limit, Claude says which one and what to try instead.

**Privacy.** Your questions are kept for 30 days to improve the metrics, then deleted. Don't type names or personal details into questions.

**Who to contact**

| For | Contact |
|---|---|
| What a metric means, a disputed number, a certification request | BI |
| Installing or updating the Claude connector and skill | Tool enablement |
| Access problems | IT service desk |
| It's slow or failing for everyone | ML / data science (monitoring) |

*Open questions for Finance:* who is the Finance champion for new joiners? Which reports, if any, must use certified figures only?
