# Changelog: governed-analytics

## 0.2.0 (16 Nov 2026)

- The reference is shown once, as the answer's last line: "Reference for BI: <id>". With several results, references go in a footnote, never a table column.
- The as-of date is reported as the date the period was worked out, never as the data date. The data snapshot is mentioned only if the user asks.
- Step 1 uses `list_metrics`' new summary line, so uncertified metrics aren't described as certified.

## 0.1.0 (14 Nov 2026)

- First draft: five steps from finding the metric to reporting with the receipt, the split between what the server enforces and what the skill asks for, and two example answers. Evals are pending until model-in-the-loop evals are enabled.
