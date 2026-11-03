# Documentation

Every document for AITestGen / Vantage, all in one place. Start at the top if you're new.

## Getting started

| Document | What it is |
|---|---|
| [getting-started/developer-guide.md](getting-started/developer-guide.md) | Onboarding for developers: repo layout, how to run things, house rules |
| [getting-started/vantage-knowledge-base.md](getting-started/vantage-knowledge-base.md) | What Vantage is, how it works and why it's built this way |

## Explorer (the current discovery engine)

| Document | What it is |
|---|---|
| [vantage-explorer/how-explorer-works.html](vantage-explorer/how-explorer-works.html) | **Start here.** A visual walkthrough of every stage, from the first look to test cases (open it in a browser) |
| [vantage-explorer/README.md](vantage-explorer/README.md) | What's built today and how to run it |
| [vantage-explorer/architecture/](vantage-explorer/architecture/README.md) | Detailed docs 01–08: system architecture, technical flow, worker modules, trust and safety, data model, API and UI, operations |
| [vantage-explorer/PLAN.md](vantage-explorer/PLAN.md) | The original design plan. Code comments cite its sections ("PLAN.md §5") |

## Architecture diagrams (open in a browser)

| Document | What it is |
|---|---|
| [architecture/vantage-diagrams.html](architecture/vantage-diagrams.html) | All diagrams in one tabbed page, to share with other teams |
| [architecture/vantage-how-it-works.html](architecture/vantage-how-it-works.html) | How Vantage works, for a non-technical reader |
| [architecture/vantage-platform-and-test-flows.html](architecture/vantage-platform-and-test-flows.html) | Platform architecture and test flows |
| [architecture/vantage-end-to-end-flow.html](architecture/vantage-end-to-end-flow.html) | End-to-end flow |
| [architecture/aitestgen-system-architecture.html](architecture/aitestgen-system-architecture.html) | System architecture |

Each `.architecture.json` file next to a diagram is its editable source.

## Crawler (the older discovery engine)

| Document | What it is |
|---|---|
| [DISCOVERY_ENGINE_V2.md](DISCOVERY_ENGINE_V2.md) | How crawling works (v2). The name is kept because code cites this path |
| [crawler/pipeline-end-to-end.md](crawler/pipeline-end-to-end.md) | The real pipeline, end to end |
| [crawler/discovery-pipeline-epic-2.md](crawler/discovery-pipeline-epic-2.md) | Epic 2: the discovery pipeline (stories 2.1–2.5) |

## Feature designs and plans

| Document | What it is |
|---|---|
| [superpowers/specs/2026-10-27-explorer-goal-scope-design.md](superpowers/specs/2026-10-27-explorer-goal-scope-design.md) | Design: the run's Goal becomes a strict scope. The path is kept because code cites it |
| [plans/2026-10-27-explorer-goal-scope-plan.md](plans/2026-10-27-explorer-goal-scope-plan.md) | Implementation plan for the goal scope |
