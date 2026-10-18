# Vantage Explorer — Architecture Documentation

This folder explains how Vantage Explorer is built and how it works. Everything here was checked against the code on branch `feature-crawl2.0` (October 2026), not against older planning documents.

Explorer is Vantage's new discovery module. It studies a web application the way a sharp new QA engineer would. It signs in, looks around, writes a one-page summary for you to confirm, and then tries every business task. Along the way it hunts for screens that only appear sometimes and asks you only when it truly needs you. Finally, it writes test cases and proves each one before handing them to the rest of Vantage.

## Reading order

| # | Document | Who it is for | What it answers |
|---|---|---|---|
| 1 | [Explorer in plain words](01-explorer-in-plain-words.md) | Everyone: product, sales, QA, stakeholders | What Explorer does, step by step, with no jargon |
| 1b | [How Explorer actually does it](01b-how-explorer-does-it.md) | Everyone who wants the "how" without code | The tricks behind each step: seeing screens, choosing where to go, staying safe, asking, hunting, proving tests |
| 2 | [System architecture](02-system-architecture.md) | Engineers, architects | The deployable pieces, the technology used, and how they connect |
| 3 | [Technical flow](03-technical-flow.md) | Engineers | The Temporal workflow, run statuses, pause/resume, and failure handling |
| 4 | [Worker modules](04-worker-modules.md) | Engineers working on the worker | What each Python module is responsible for, with its limits and constants |
| 5 | [Trust, safety and proof](05-trust-safety-and-proof.md) | Everyone (sections 1–2), engineers (the rest) | Why Explorer never treats the app as the truth, what it will never click, and how a test is proven |
| 6 | [Data model](06-data-model.md) | Engineers, DBAs | The `explorer_*` tables, the migrations, and what Explorer writes into classic Vantage |
| 7 | [API and web UI](07-api-and-web-ui.md) | Front-end and API engineers | Every `/explorer` endpoint and every screen of the Explorer tab |
| 8 | [Operations and configuration](08-operations-and-configuration.md) | Whoever runs or debugs it | How to start it, the settings, troubleshooting, and known gaps |

## Diagrams

The diagrams are interactive HTML files made with Archify. Open them in a browser to zoom, use guided views, switch dark/light, and export PNG or SVG. The `.json` file next to each diagram is its source. Edit the JSON and re-render it instead of editing the HTML.

| Diagram | Type | Used in |
|---|---|---|
| [How Explorer works, in plain words](diagrams/explorer-plain-flow.html) | Workflow | Doc 1 |
| [Inside Explorer: the helpers](diagrams/explorer-inside-plain.html) | Architecture | Doc 1b |
| [System architecture](diagrams/explorer-system.html) | Architecture (4 guided views) | Doc 2 |
| [Pipeline: activities in order](diagrams/explorer-pipeline.html) | Workflow | Doc 3 |
| [Request sequence](diagrams/explorer-run-sequence.html) | Sequence | Doc 3 |
| [Run status lifecycle](diagrams/explorer-run-lifecycle.html) | Lifecycle | Doc 3 |
| [Trust model](diagrams/explorer-trust.html) | Data flow | Doc 5 |

To re-render one after editing its JSON (Archify skill installed at `~/.claude/skills/archify`):

```bash
node ~/.claude/skills/archify/bin/archify.mjs deliver workflow \
  docs/vantage-explorer/architecture/diagrams/explorer-pipeline.workflow.json \
  docs/vantage-explorer/architecture/diagrams/explorer-pipeline.html --quality standard --json
```

Use `architecture`, `workflow`, `sequence`, `lifecycle` or `dataflow` to match the file's middle extension.

## Related documents

- [`../PLAN.md`](../PLAN.md) is the original product plan, written in plain words. It describes intent, and some details have since changed.
- [`../README.md`](../README.md) is the stage-by-stage build log. Its UI section describes earlier tabs (Missions, App map, Report) that have since been folded into the current five tabs. Document 7 has the current UI.
- [`../RESUME.md`](../RESUME.md) records where the Stage 8 work stopped.
