---
name: ponytail
description: Flag deliberate, bounded implementation shortcuts and simplifications with an inline `ponytail:` comment, and check for existing `ponytail:` tags before touching code they cover. This project's own convention (already used in suite_generation_workflow.py, discovery_workflow.py, crawler.py, planner.py, safety_engine.py, invites.py) for marking "this is the simplest thing that satisfies the current scope, not the fully general solution — here's why, and here's what a fuller version would need." Use before writing, adding, modifying, refactoring, fixing, or reviewing code, or choosing a library/dependency — surface prior shortcuts relevant to the area being touched, and tag any new ones you introduce.
---

# Ponytail — flag deliberate implementation shortcuts

This project marks deliberate, scope-bounded shortcuts inline with a `ponytail:`
comment tag, rather than letting them hide as unexplained code. Real examples
already in this codebase:

```python
# ponytail: fixed wave count/cooldown, not configurable — revisit if timeouts
# still exhaust 3 waves at higher real concurrency than observed live.
MAX_SCENARIO_WAVES = 3
```

```python
# ponytail: dev fallback, no SMTP configured — log the link instead
# of failing. Add real SMTP env vars (SMTP_HOST/USER/PASSWORD) to send.
```

```python
# `ponytail:` temporary substitute for Story 2.10's SAME/VARIANT/NEW
# classification (not built yet, per this story's own AC 7) —
# element-count growth answers "did anything appear?", not "is what
# appeared the same kind of thing?".
```

A `ponytail:` comment is not a generic `TODO`. It specifically means: *this
is the simplest thing that satisfies what's being built right now, a fuller
version exists and was consciously not built, here is why, and here is what
would need to change to do it properly.* It makes a scope decision legible
and searchable instead of silent.

## Before generating or editing code

1. **Search for existing `ponytail:` tags in the area you're about to touch**
   (`grep -rn "ponytail:" <dir or file>`). If one exists in code you're
   modifying:
   - If your change makes the flagged shortcut irrelevant (you built the
     fuller version, or removed the code path), remove the tag along with it.
   - If the shortcut still stands but its stated trigger condition ("revisit
     if X") has now happened, that's a signal to actually address it, or at
     minimum update the comment.
   - Otherwise leave it — don't silently work around a documented shortcut
     without acknowledging it.
2. **Do the real work first.** Don't reach for a shortcut to avoid effort —
   only take one when the fully general solution is genuinely out of scope
   (a future story/epic, an explicit non-goal, a dependency that doesn't
   exist yet, a product decision not yet made).

## When you take a shortcut

Tag it at the point of the decision with a `ponytail:` comment that states,
in this order:
1. **What was substituted** — the simplified thing you actually built.
2. **Why** — the scope/dependency/timing reason the full version wasn't
   built (reference a story/epic/AC number if one applies, per this repo's
   convention).
3. **What would need to change** to do it properly, so a future pass doesn't
   have to rediscover the gap from scratch.

Keep it to what the examples above show — a short, specific note at the
decision site, not a design essay. Don't tag routine judgment calls that
aren't a scope shortcut (e.g. picking one valid approach among several
equally-complete ones isn't a `ponytail:` — reserve it for "the general
solution exists but isn't what's here").

## Don't over-apply it

Not every simplification needs a tag — only ones a future reader would
otherwise mistake for the intended final behavior, or would waste time
rediscovering the reasoning behind. If in doubt, prefer explaining the
non-obvious constraint in a normal comment (per this project's existing
comment conventions) and reserve the `ponytail:` prefix for genuine
scope-bounded substitutions worth being able to `grep -rn "ponytail:"` for
later.
