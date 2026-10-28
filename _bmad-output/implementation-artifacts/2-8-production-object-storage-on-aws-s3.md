---
last_updated: 2026-10-27
---

# Story 2.8: Production Object Storage on AWS S3

Status: done

> This story describes the **classic discovery engine**'s storage. Explorer (Epic 8) keeps its own screenshots and videos in the database instead; it copies a screen's screenshot into this storage only when it hands its results to Journeys.

## Story

As the team operating Vantage,
I want screenshots and other large captured files kept in managed cloud storage (AWS S3),
so that Vantage relies on durable, managed storage rather than a storage service we have to run ourselves.

## What it does today

- Discovery screenshots are saved as files in AWS S3 and linked from the page they belong to. The database only holds the link.
- The same storage also holds test-run screenshots, traces and reports (Epic 6).
- Every environment uses the real S3 storage, including local development. There is no self-hosted storage stand-in any more.
- Journey cards and enlarged screenshots load their images from this storage. If an image fails to load, the card shows a placeholder and tries again later instead of staying broken.
- When an application is permanently cleaned up after the retention period (Settings), its stored files go with it.

## Acceptance criteria

1. **Given** Discovery captures a screenshot, **then** it is stored in S3 and only a link to it is kept with the page.
2. **Given** any environment (local, staging, production), **then** the same S3-backed storage is used.
3. **Given** a stored screenshot, **when** a journey card is shown, **then** the image is loaded from storage, and a failed load shows a placeholder and is retried rather than staying broken.
