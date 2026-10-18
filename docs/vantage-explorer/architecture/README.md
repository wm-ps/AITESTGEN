# Vantage Explorer: documentation

Explorer is the part of Vantage that learns a web application by itself. It asks you to confirm what it learned, tries every important task, and hands you tests it has proven work.

## Where to start

| If you are… | Read |
|---|---|
| **Anyone who wants to understand how it works.** No technical background needed. | **[1. How Explorer works, explained simply](01-how-explorer-works.md)** |
| An engineer joining the project | Doc 1, then docs 2 → 3 → 4 |
| Working on the screens or the API | Doc 7 |
| Running or debugging it | Doc 8 |

## All documents

| # | Document | For | What it answers |
|---|---|---|---|
| 1 | [How Explorer works, explained simply](01-how-explorer-works.md) | Everyone | What Explorer does and how, step by step, with pictures and one running example |
| 2 | [System architecture](02-system-architecture.md) | Engineers | Which parts make up Explorer, what technology each uses, and how they connect |
| 3 | [Technical flow](03-technical-flow.md) | Engineers | The order of steps in a run, who calls whom, the statuses, pause/resume, and failure handling |
| 4 | [Worker modules](04-worker-modules.md) | Worker developers | What each Python module is responsible for, with its limits |
| 5 | [Trust, safety and proof](05-trust-safety-and-proof.md) | Everyone (part 1), engineers (part 2) | Why Explorer never trusts the app blindly, what it won't press, and how tests are proven |
| 6 | [Data model](06-data-model.md) | Engineers | What is stored, what reaches the rest of Vantage, and what healing can use |
| 7 | [API and web UI](07-api-and-web-ui.md) | Front-end and API engineers | Every endpoint, and every view of the Explorer tab |
| 8 | [Operations and configuration](08-operations-and-configuration.md) | Whoever runs it | Starting it, settings, troubleshooting, and known gaps |

## About the pictures

Every picture lives in `diagrams/img/` and shows inline in these documents. To change a picture:

1. Edit its section in [`diagrams/figures.html`](diagrams/figures.html). Each picture is one `<section class="fig" id="…">`. You can also open the file in a browser to see all pictures on one page.
2. Re-create the images from the repo root:

   ```bash
   .venv/Scripts/python.exe docs/vantage-explorer/architecture/diagrams/render.py
   ```

All facts in these documents were checked against the code on `feature-crawl2.0` in October 2026.

## Older documents

These live in `docs/vantage-explorer/`:

- [`../PLAN.md`](../PLAN.md) is the original product plan. It describes the intent, and some details have since changed.
- [`../README.md`](../README.md) is the build log by stage. Its description of the UI is out of date.
- [`../RESUME.md`](../RESUME.md) is a note on where the Stage 8 work stopped.
