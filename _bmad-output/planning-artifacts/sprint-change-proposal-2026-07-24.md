---
title: "Change record — Production file storage on AWS (2026-07-24)"
status: approved
created: 2026-07-24
approved: 2026-07-24
last updated: 2026-10-27
---

# Change record: Production file storage on AWS (2026-07-24)

## What was proposed and why

Discovery saves screenshots and page snapshots as files. The architecture had fixed *how* they were stored (files kept separately from the main database, with the database only pointing to them) but had left *where* undecided. Local development used a self-hosted, S3-compatible storage service that could have been carried into production.

The proposal settled the question: use Amazon S3 in production. A local stand-in would stay for development and automated checks.

## What was decided

- Approved.
- AWS S3 became the production file store.
- Moving production onto it was planned as a separate piece of work, with no change to how Discovery saves or reads files.

## Where it stands today (2026-10-27)

**Shipped, and gone further than planned.**

- All stored files live in AWS S3. That covers Discovery screenshots, test-run screenshots and traces, and HTML test reports.
- The local stand-in was dropped too: local development now uses real S3 as well.
