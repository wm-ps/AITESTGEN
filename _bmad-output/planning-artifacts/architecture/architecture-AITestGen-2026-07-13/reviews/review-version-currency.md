---
title: Version Currency Review — Vantage stack as built
target: ../ARCHITECTURE-SPINE.md (Stack table)
date: 2026-10-27
method: Locked versions read from uv.lock, apps/web/package-lock.json, Dockerfiles, docker-compose.yml and the test-suite assembler; compared against upstream release status found by web search on 2026-10-27. Where search results were inconclusive this is stated.
---

# Version Currency Review (2026-10-27)

This replaces the 2026-07-13 review of the July draft. That review's findings (TypeScript "5.x", Vite "6.x/7.x", Jenkins-as-Git-host in the `DeliveryAdapter`) no longer apply: the stack table now lists exact locked versions, TypeScript is deliberately pinned, and CI/CD delivery was removed.

## Verdict

The application stack is current. Python, FastAPI, SQLModel/SQLAlchemy, Postgres 18, React 19, Vite 8 and Tailwind 4 are all on their current lines. The risks are in the **container and test-runtime pins**, not the libraries: `nginx:1.27` is past end of life, Vault 1.18 is several minors behind, Temporal server runs in dev mode, the generated projects' `@playwright/test ^1.48.0` floor sits far below the Python Playwright 1.61 the workers use, and `@playwright/mcp@0.0.41` is an early pre-1.0 pin.

## Findings

### 1. [HIGH] `nginx:1.27-alpine` (web image) is end of life
The 1.27 line stopped receiving security fixes in June 2025, and 1.28/1.29 have since ended too. 1.30 (stable) and 1.31 (mainline) are the supported lines. **Action:** bump the web Dockerfile to `nginx:1.30-alpine`. This is a one-line change and nothing in the static-file config depends on 1.27.

### 2. [HIGH] Temporal server runs `start-dev` from `temporalio/admin-tools:1.31.2` in production
The version itself is fine. The deployment mode is the problem: the dev server keeps state in memory, so workflow history and every Temporal Schedule (user test-run schedules, cleanup, stale-run reconcile) are lost on pod restart. This is an operational risk, not a currency issue, but it belongs here because the "version" in use is the dev-server build. **Action:** run a persistent Temporal (Postgres-backed) or Temporal Cloud before relying on schedules.

### 3. [MEDIUM] Generated test projects pin `@playwright/test ^1.48.0`
The worker images use Playwright 1.61 (Python), but generated, recorded and downloaded TS projects declare `^1.48.0`, as does `packages/playwright_typecheck/typecheck`. The caret allows newer versions to resolve, but the declared floor is about 13 minors old. A downloaded suite installed in a fresh environment may get a different browser build than the one the specs were generated and healed against. **Action:** raise the floor to the version actually used by the execution worker, and keep the two in step.

### 4. [MEDIUM] HashiCorp Vault `1.18`
Third-party trackers list Vault 1.21 as already past end of life and 2.0/2.1 as current (an official HashiCorp source was not found in search). HashiCorp's policy expects customers to stay within two releases of the latest major release. On that basis 1.18 is out of support. Vault holds only target-app credentials here, and auto-unseal keeps the root token on the same volume (see spine risks). **Action:** upgrade to a supported Vault release when the unseal setup is revisited. The KV v2 API used through hvac 2.4.0 is stable across these versions.

### 5. [MEDIUM] `@playwright/mcp@0.0.41`
This is an early pre-1.0 pin used only by the live-exploration agent. Pre-1.0 MCP tooling changes tool names and arguments between releases, so the exact pin is the right *policy*. It is likely well behind upstream, though: this review did not confirm the current release. **Action:** re-test live exploration against a current release before bumping, and keep the version exactly pinned.

### 6. [LOW] TypeScript 5.9.3 instead of 7.x
This pin is deliberate. TypeScript 7.0 (Go-native, GA July 2026) shipped without a programmatic compiler API. 7.1 restores one and is in beta now, with stable expected around late November 2026. `openapi-typescript`, `tsc -b` in CI and the `tsc --noEmit` gate in `playwright_typecheck` all run fine on 5.9. **Action:** stay on 5.9 until 7.1 is stable and the codegen toolchain supports it.

### 7. [LOW] Node 22 for the web build
Node 22 is in maintenance LTS and Node 24 is the active LTS. It is only used at build time, so the risk is low. **Action:** bump to `node:24-alpine` with the next web dependency refresh.

### 8. [LOW] Temporal Python SDK 1.30.0
SDK 1.31.0 was released in about late July 2026, and this review did not confirm anything newer. Being one minor behind carries no known compatibility issue with the 1.31.x dev server. **Action:** routine bump.

## Current as of 2026-10-27 (no action)

| Component | Locked | Note |
| --- | --- | --- |
| Python | 3.14.6 | Current 3.14 line; ruff/pyright target py314 |
| FastAPI / uvicorn | 0.139.0 / 0.51.0 | Active monthly releases |
| SQLModel / SQLAlchemy | 0.0.39 / 2.0.51 | SQLModel's single-maintainer risk is noted, but it is actively released |
| Alembic | 1.18.5 | Current |
| psycopg | 3.3.4 | Current 3.x |
| PostgreSQL | 18.4 (local) | Current major; native `uuidv7()` is relied on. Prod is an external host and its version is not pinned in repo, so verify it is 18+ |
| Playwright (Python) | 1.61.0 | Recent |
| LangGraph / langchain-core / mcp | 1.2.11 / 1.6.1 / 2.1.1 | Post-1.0 lines |
| hvac / boto3 / httpx / pydantic | 2.4.0 / 1.43.55 / 0.28.1 / 2.13.4 | Current |
| React | 19.2.7 | Current major |
| Vite | 8.1.5 | Current major (Rolldown/Oxc) |
| Tailwind CSS | 4.3.3 | Current major |
| vitest / oxlint / recharts / @novnc/novnc | 3.2.7 / 1.74.0 / 3.10.1 / 1.7.0 | Acceptable |
| allure / allure-playwright | ^3.20.1 / ^3.13.0 | Allure 3 (Node, no Java) |
| pypdf | 6.20.1 (`pypdf>=5.0` in `apps/api`) | Added by the Explorer merge (knowledge-document uploads). On the current 6.x major; the exact latest release was not confirmed. Pure Python, no native deps. |

## Explorer merge (2026-10-27, 2d88b20 / 460f8e4)

The merge added two workspace packages, `explorer-worker` (`apps/workers/explorer`) and `explorer-core` (`packages/explorer_core`), and one third-party library, **pypdf 6.20.1** (above). No web (`package.json`/`package-lock.json`), Dockerfile or docker-compose version changed. The Explorer worker's declared floors (`temporalio>=1.9`, `sqlmodel>=0.0.24`, `psycopg[binary]>=3.2`, `httpx>=0.28`, `playwright>=1.57`) resolve to the same locked versions as the rest of the workspace, so the stack table is unchanged apart from pypdf. Python floor is `>=3.14`, matching the workspace.

There is no Explorer worker container image yet, so there is no base-image pin to check. When one is added it should use the same `python:3.14-slim` + Playwright 1.61 browser build as the discovery and execution workers.

Explorer calls the LiteLLM proxy with two new model aliases, `gpt-5.6-sol` (thinking) and `gpt-5.6-luna` (fast), via its own httpx client with `response_format: json_object`. Any alias change must keep JSON-object mode and image input working through the proxy.

## Vendor-compatibility assumptions checked

- **LLM access:** no vendor SDK is installed. All calls go through httpx to a LiteLLM proxy with a model alias (`gpt-5.6-luna` in prod; Explorer adds `gpt-5.6-sol` through its own client, see above). Model swaps are config-only. The one GPT-specific request-param branch in `hosted.py` is the only place a non-GPT alias could behave differently.
- **`GEMINI_API_KEY`** is present in `.env` but no code references it. It is harmless, but dead config.

## Sources
- [nginx versions and EOL (versionlog.com)](https://versionlog.com/nginx-oss/)
- [nginx EOL (isitpatched.com)](https://isitpatched.com/eol/nginx)
- [endoflife.date — nginx](https://endoflife.date/nginx)
- [HashiCorp Vault 2.1 version status (endoflife.ai)](https://endoflife.ai/hashicorp-vault/2.1)
- [HashiCorp Vault releases & EOL (versio.io)](https://www.versio.io/en/product-release-end-of-life-eol-hashicorp-vault.html)
- [TypeScript 7.1 beta (digitalapplied.com)](https://www.digitalapplied.com/blog/typescript-7-1-beta-whats-new-what-to-test)
- [TypeScript 7.1 beta API (warp2search.net)](https://www.warp2search.net/story/typescript-71-beta-released-new-api-unblocks-vue-svelte-and-angular-tooling/)
- [temporalio on piwheels](https://www.piwheels.org/project/temporalio/)
- [temporalio summary (ecosyste.ms)](https://summary.ecosyste.ms/projects/371560)
