---
name: dashboard
description: Open the selected SpielOS company's dashboard or report and inspect workflows, memory, context, evaluations and token usage. Use when the user asks for the company report, dashboard or tracking card.
---

Use only the company folder explicitly selected by the owner. If none is selected, use setup; never select the plugin cache, source checkout or another company. Resolve the plugin root from this installed skill and use its scripts/entry.py with `report --home <selected absolute home> --no-open --json`. Open the returned URL when asked and give a clickable link. The dashboard's local access URL is private; never export its access token.

Inspect actual data before reporting counts. Explain missing capture, pending evaluations and telemetry delivery truthfully. Local-only recording does not require Langfuse. No before/after improvement percentage is established by run counts. Use only actual baseline/candidate evidence for comparisons.

If the user asks for a chat card, render the selected activity session's runtime company.observability.receipts.markdown output. This is a Markdown receipt in the chat; it is not an arbitrary native host card. Use the Director contract and relevant build/run/review skill for work beyond inspection. Opening the dashboard creates no production run and authorizes no external action.
