---
name: bmad-progress-visualizer
description: Read this project's BMAD story files under _bmad-output/implementation-artifacts/*.md, cross-reference them against the actual codebase, and produce two side-by-side HTML diagrams — one showing the total planned project flow (all epics/stories), and one showing current implementation status (same layout, color-coded by how much of each story is actually built). Use this skill whenever the user asks "what's left to build", "how much is done", "project status", "implementation progress", "show me the roadmap vs reality", or wants a visual of planned-vs-built for a BMAD-style project. Trigger even if the user just says "check progress" or "where are we" in a project that has a _bmad-output/implementation-artifacts folder. This skill is self-contained — it does not require any other skill to function, though it produces HTML output using the same single-file constraints any infographic skill would.
---

# BMAD Progress Visualizer

Turns "what did we plan?" (the story files) and "what actually exists?" (the codebase) into two diagrams with the **identical layout** so a person can flip between them — or view them stacked — and immediately see the gap.

This skill does real analysis, not just rendering. Don't skip straight to drawing — the diagram is only as good as the story-parsing and code-scanning steps underneath it.

## Step 1 — Discover the stories

List every file in `_bmad-output/implementation-artifacts/*.md`. The filename convention is `{epic}-{story}-{slug}.md`, e.g. `1-1-repository-service-scaffold.md` = Epic 1, Story 1, "Repository Service Scaffold".

For each file, read it and extract:

- **Title** (usually the first `#` heading, or derive from the slug if missing)
- **Goal / description** — what the story is trying to accomplish
- **Acceptance criteria / tasks** — the concrete, checkable things that define "done" for this story (bullet lists, checkboxes, "must/should" statements)
- **Explicit non-goals** — anything the story says is *out of scope* ("what not to do"). Keep these — they matter for not penalizing a story for lacking something it was never meant to have.
- **Dependencies** — any mention of other stories/epics this one depends on or blocks. If none are stated explicitly, assume sequential dependency within the same epic (story N depends on story N-1) and no cross-epic dependency unless the text says so.
- **Any explicit status field**, if the file happens to have one (e.g. a `Status:` line). If present, treat it as a strong signal but still verify against the code — don't take it blindly, since a story can be marked planned/approved without a line of code existing yet, or marked in-progress after it's actually finished.

Build an ordered list grouped by epic, then by story number within epic. This ordering becomes the layout skeleton for both diagrams.

## Step 2 — Scan the codebase for evidence

For each story, derive 3-6 concrete search terms from its title/description/acceptance criteria — service names, class names, file names, route paths, table names, function names — anything specific enough to search for. Generic words ("service", "handler") are too broad on their own; combine them with the specific noun from the story (e.g. "repository service" → search for `RepositoryService`, `repository_service`, `repo-service`, matching file paths).

For each story, gather evidence using the repo's actual tools (grep/glob/find, or a code-search tool if one is connected):

1. **File existence** — do files matching the expected module/component exist?
2. **Implementation depth** — is the file a stub (empty function, `TODO`, `NotImplementedError`, a few lines) or does it look substantively implemented (real logic, error handling, multiple functions)?
3. **Test coverage** — is there a corresponding test file, and does it look like it actually exercises the feature (not just a placeholder test)?
4. **Wiring** — is the thing actually referenced/used elsewhere (imported, registered in a router, called from another module), or does it exist in isolation with nothing pointing to it? Code that exists but is never wired in is weaker evidence than code that's connected to the rest of the app.

Score each story on a simple scale based on this evidence:

| Score | Meaning |
|---|---|
| **Not Started** (0%) | No matching files/code found for the story's core deliverable |
| **In Progress** (roughly 25/50/75% — pick the closest) | Some matching code exists but is incomplete, stubbed, untested, or not wired in |
| **Done** (100%) | Core deliverable exists, looks substantively implemented, is wired into the rest of the app, and (ideally) has tests |

Be honest and specific rather than generous — if you can't find it, it's Not Started, regardless of what any status field in the story file claims. Note in your own working notes *why* you scored each story that way (what you found or didn't find) — you'll want this to explain the diagram afterward, and to avoid re-deriving it if the user asks "why is story 2-3 only 50%?".

Roll story scores up into an **epic completion %** (average of its stories, or weighted by story count) and an **overall project completion %**.

## Step 3 — Design the shared layout

Both diagrams must use the exact same node positions and the exact same connections — only the fill/status changes between them. Pick a layout that fits how many epics/stories exist:

- **Small project (≤ 3 epics, ≤ 15 stories total)**: horizontal swimlanes, one row per epic, stories as connected nodes left-to-right within the row, epics stacked top-to-bottom.
- **Larger project**: a vertical flow of epics (top to bottom), each epic as a labeled band containing its stories as a horizontal mini-chain within the band. If it's too dense for one canvas, it's fine to make the canvas tall and let it scroll — these are meant to be viewed in a browser/Notion, not necessarily screenshotted whole.
- **Cross-epic dependencies** (if any were found in Step 1): draw as a distinct dashed connector cutting across bands, separate from the default sequential arrows, so it doesn't clutter the main flow.

Each node = one story. Node content: story number + short title. Keep labels short (title only) in the node itself; put fuller detail (goal, why it's scored that way) in a hover tooltip or a small caption beneath the node — don't cram the acceptance criteria into the node itself.

## Step 4 — Build Diagram A: Total Flow

Every node present, neutral consistent styling (one ink color, one fill, no status color-coding), arrows/connectors showing the planned sequence and any dependencies. This is the "blueprint" — what was planned, full stop, with no judgment about progress. Include the epic labels and story titles clearly. This diagram should look complete and clean regardless of how much is actually built.

## Step 5 — Build Diagram B: Implementation Status

Identical node positions and connectors to Diagram A. Now color each node by its Step 2 score:

- **Not Started** — muted gray/outline only fill
- **In Progress** — amber/yellow fill, with the specific percentage (25/50/75%) labeled on the node
- **Done** — solid green fill with a checkmark

Add a small legend (color → meaning) once, not repeated per node. Add an overall completion readout at the top of this diagram (e.g. "Overall: 42% complete — 3 of 8 stories done, 4 in progress, 1 not started") and a per-epic subtotal near each epic band. This is the "reality" diagram — it should make the gap between plan and progress visible at a glance, without needing to read every node.

## Step 6 — Output

Both diagrams should render as single self-contained HTML files, following the same build constraints as any infographic deliverable:

- All CSS inline in one `<style>` block, no external stylesheets
- SVG or HTML/CSS for the diagram shapes — hand-write simple shapes/connectors, no external icon or diagram libraries
- Google Fonts via `<link>` is fine; always include a system-font fallback
- No network dependency required to open the file

Default to producing **one HTML file with both diagrams stacked** (Total Flow on top, Implementation Status below, same width so nodes visually line up when scrolling between them) unless the user asks for two separate files. Use a shared, restrained palette (e.g. Minimal-mono style: neutral ink/background, single accent used for connectors, status colors reserved only for Diagram B) so the two diagrams read as a matched pair, not two different documents.

Name the output descriptively, e.g. `project-flow-vs-status.html`.

## Step 7 — Report back in text too

After presenting the file, summarize in a few lines what you found — don't make the user hunt through the diagram for the headline numbers:

> "Overall the project is ~42% complete. Epic 1 (Repository layer) is fully done. Epic 2 (API layer) has 2 of 4 stories done, 1 stubbed with no tests, 1 not started. Epic 3 hasn't been touched yet. Diagram below — top is the full planned flow, bottom is current status."

If a story's inferred status seems to contradict something explicit in the story file (e.g. file says "Status: Done" but no code was found), call that out specifically rather than silently picking one — the user may know something the repo doesn't show (e.g. code lives in another repo).

## Notes on ambiguity

- If `_bmad-output/implementation-artifacts/` doesn't exist or is empty, say so plainly and ask where the stories actually live rather than guessing.
- If a story is too vague to derive search terms from, mark it "Unclear — needs more specific acceptance criteria to verify" rather than guessing at a percentage.
- If the codebase is large enough that exhaustive scanning per story is expensive, prioritize: scan directory/file structure first for obvious matches, then grep only within plausible candidate files/directories rather than the whole repo per story.
