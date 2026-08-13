# Discovery Engine v2 — How Crawling Works

**Status:** design spine for Epic 2 Stories 2.9–2.22.
**Supersedes:** the crawl-mechanics half of `EPIC_2_DISCOVERY_PIPELINE.md` (the
Journey-inference half of that document is unchanged and still authoritative).
**Written:** 2026-08-03, replacing the 2026-07-29 story batch after a
feasibility review.

This document explains what the crawler actually does, in order, and why each
step exists. Every Story 2.9–2.22 implements one labelled box below. If a story
and this document disagree, this document is wrong — fix it here first.

---

## 1. What we are actually trying to do

Point a real browser at an authenticated web application, walk it the way a
careful QA engineer would on their first day, and come out with:

- a structural map of the app (pages, forms, actions, API calls, transitions),
- durable locators for everything interactive,
- an honest account of what we *couldn't* reach and why.

We are explicitly **not** trying to visit every URL or click every button. We
are trying to find every *distinct behaviour* once, cheaply, without breaking
anything.

**The single most important design property:** every step degrades instead of
failing. A page that won't settle gets captured best-effort. A widget with no
ARIA role falls back to structural heuristics. A state we can't return to gets
its remaining actions marked unreached, not silently dropped. There is no step
in this pipeline whose failure stops the run.

---

## 2. The pipeline

```
PHASE 0  PREPARE
  0.1  Load the Application's Test Data Pool            (Story 2.20)
  0.2  Load canonical Pages from prior runs → cache     (Story 2.10)
  0.3  Authenticate, store session state                (Story 2.2, existing)

PHASE 1  CRAWL LOOP  — repeat until the frontier is empty
  A  OBSERVE      settle the page, then capture it       (2.9, 2.14)
  B  IDENTIFY     SAME / VARIANT / NEW                   (2.10)
  C  ENUMERATE    list candidate actions, tier + locate  (2.14, 2.11, 2.21)
  D  DECIDE       one verdict per candidate              (2.11 ← 2.19, 2.12, 2.13)
  E  ACT          execute / defer / skip                 (2.11, 2.15)
  F  RETURN       get back to the state to try the next  (2.11)   ← the hard one

PHASE 2  CLOSE OUT
  2.1  Coverage report: reached / blocked / skipped / errored / unreached  (2.22)
  2.2  Aggregate blocked items into distinct asks        (2.15)
  2.3  Application Model build → Journey inference       (2.5, 2.6, existing)
```

---

## 3. Phase 1 in detail

### A — OBSERVE (Stories 2.9, 2.14)

**Settle first.** A snapshot taken mid-render is worse than useless: it
produces a fingerprint that matches nothing and actions that don't exist yet.
Readiness is three signals with a hard ceiling:

1. **Network quiet** — no *application-relevant* in-flight requests. We
   classify a request as ignorable when it repeats to the same URL at a
   regular cadence (polling), or matches a known analytics/telemetry host
   pattern. This heuristic will be wrong sometimes; the ceiling below is what
   makes that survivable.
2. **DOM stable** — no mutations for a short quiet window, observed via
   `MutationObserver` in-page rather than by polling from the driver.
3. **Content present** — the rendered text is non-empty (catches the SPA shell
   that has "loaded" but not yet fetched its data).

All three are bounded by a **Page Load Timeout** (per-Application default,
per-run override, ~15s). On expiry we capture anyway, best-effort, and log
`DISC-004`. **We never block the run on readiness.**

**Then capture, including the containers everyone forgets:**

- the accessibility tree (primary source for what's interactive),
- the DOM structure (for fingerprinting),
- a screenshot,
- network calls seen since the last capture,
- **inside every same-origin iframe**, recursively, depth-bounded,
- **inside every open shadow root** (closed roots are invisible — logged, not
  fatal).

Iframes and shadow DOM are not exotic. SAP portals, Salesforce Lightning,
embedded legacy apps and most modern design systems use them. A crawler that
doesn't traverse them silently reports an empty page and calls it success.

**Repeating content is sampled, not exhausted.** For infinite scroll and
"Load More": act, re-observe, compare the newly revealed region. Two or three
consecutive SAME classifications confirm "this is a repeating pattern" and we
stop. A hard per-page budget stops us regardless, so a list whose structure
drifts every few items still terminates.

### B — IDENTIFY (Story 2.10)

Every observed state is compared against states already seen this run and
canonical pages from prior runs, held in an in-process cache (no Redis — see
AD-16).

**Cheap hard filter first.** If no cached state shares the candidate's route
template (`/claims/1001` → `/claims/{id}`), it's NEW immediately and we never
run the expensive comparison.

**Then a weighted score** across four signals — heading, action set, form set,
structural shape — against two configurable thresholds:

| Result | Meaning | What we persist |
|---|---|---|
| **SAME** | Same behaviour, different data (`/claims/1001` vs `/claims/1002`) | Nothing. Alias the URL to the existing page. |
| **VARIANT** | Same route, materially different behaviour (Draft has Edit/Submit; Pending has Approve/Reject) | A sibling `Page` row via `variant_of_page_id`. Both stay canonical. |
| **NEW** | Genuinely unseen | Full `Page` + actions + forms + transitions. |

In the ambiguous band between thresholds, the AI provider gives a supporting
opinion. **The engine still owns the verdict** — the AI is evidence, not an
authority.

**The case v1 got wrong: apps where the URL never changes.** A no-routing SPA
(older Angular, Ext JS, in-memory dashboards) makes every state share one route
template, so the hard filter collapses and the weighted score carries 100% of
the load with no pre-filter to protect it. This is now explicit: when route
templates provide no discrimination across the run, the engine widens to
content-derived signals and **logs that it has done so**, so a badly-tuned run
on such an app is diagnosable instead of mysterious.

**Thresholds are observable.** Every classification writes its score and
contributing signals to the run diagnostics (Story 2.22). A tunable knob nobody
can see the effect of is not tunable — this is the fix for the biggest weakness
in the original design.

### C — ENUMERATE (Stories 2.14, 2.11, 2.21)

Candidate actions come from the **accessibility tree first** — roles, names,
states. This is what makes the engine framework-agnostic: React, Angular, Vue
and server-rendered markup all produce the same ARIA surface when built
properly. We special-case no framework, ever.

Where ARIA is absent (legacy markup, bespoke design systems), **structural
heuristics** take over — tag type, click handlers, class-name conventions,
position — and everything they find is marked **low confidence** so it can be
reviewed rather than silently trusted.

Widget patterns handled explicitly, because each strands a naive crawler:

- **Tabs** (`role="tab"`) — each tab is a Tier-1 action; revealed content is
  fingerprinted as its own state.
- **Dialogs/modals** — fingerprinted as nested states even though the URL
  doesn't change. **Closing them reliably matters more than opening them:**
  try Escape, then an accessible "Close"/"Cancel"/"X", then force-navigate back.
  An unclosable dialog strands the rest of the run.
- **New tabs/windows** — same-origin and in-scope: follow as a sub-flow, link
  back to the opening action. Cross-origin: defer, return focus.
- **File inputs** — routed to the Data Resolver for a reusable placeholder file.

Each candidate is tagged **Tier 1 (in-page)** or **Tier 2 (navigation-intent)**
deterministically — ARIA role, whether the href changes route, layout position
inside or outside nav landmarks — with AI only for genuine ambiguity.

Each candidate also gets a **durable locator** captured now, while we can see
the element (Story 2.21). Priority: `data-testid` → ARIA role+name → visible
text → labelled-field association → scoped CSS. Locators that look generated
(`css-1x2y3z`, `ctl00_ContentPlaceHolder1_…`) are detected and **down-ranked**,
because a locator that breaks next deploy makes the generated test worthless
even though the crawl succeeded.

### D — DECIDE (Story 2.11, asking 2.19 / 2.12 / 2.13)

The Planner has **no intelligence of its own**. It asks each specialist exactly
one question, in a fixed order chosen so the cheapest and most decisive checks
run first, and combines the answers into exactly one verdict.

| # | Specialist | Question | Can answer |
|---|---|---|---|
| 1 | Loop guards (2.19) | Done this already? Would it cycle? Over budget? | → SKIP |
| 2 | Safety (2.12) | Safe, destructive, or ambiguous? | → SKIP / DEFER |
| 3 | Data Resolver (2.13) | Can we supply the inputs it needs? | → DEFER |

Verdict: **EXECUTE**, **DEFER**, or **SKIP**. Safety runs before data
resolution deliberately (AD-19) — resolving inputs for an action we'll never
perform is wasted work.

**Safety classification** is verb/pattern-based against three lists, with an AI
opinion for ambiguous language, and **defaults to DEFER when unsure** — never
to Safe. Delete/Remove/Terminate/Transfer/Pay → never executed.
Submit/Approve/Save/Confirm → deferred for authorization.
View/Expand/Filter/Search/Paginate → executed.

The honest limitation: **a destructive action that doesn't look destructive
cannot be detected from the DOM.** "Process", "Archive", or a Save button that
emails a customer will read as ambiguous at best. Because of that, safety
posture is **an explicit per-Application setting**, not a universal guess:

- `non_production` (default, recommended) — ambiguous actions execute, so
  coverage is high; destructive verbs still never run.
- `production` — ambiguous actions defer, so coverage is deliberately
  sacrificed for safety.

This is the one setting that most changes what a run produces, and it is a
decision the customer must make consciously rather than inherit.

**Data resolution** tries, in strict order:

1. the **Test Data Pool** the user seeded for this Application (Story 2.20),
2. a value already visible on the current page,
3. a value used successfully earlier in this run,
4. safe synthetic data for a recognisably generic field (name, email, date,
   quantity, description) or a placeholder file for an upload,
5. otherwise — **defer, never invent.** A field like "Active Policy Number"
   gets no guessed value.

Every value used is logged, **with whether the action it fed actually
succeeded**. That last part is new and it matters: if a value was rejected by
the app, the resolver demotes it and won't keep re-using it for the rest of the
run. Without that feedback the resolver repeats the same failing guess on every
page.

### E — ACT (Stories 2.11, 2.15)

**All untried Tier 1 actions on a state are exhausted before any Tier 2
action.** This is the rule that stops the crawler wandering off a page it only
half-understands.

- **EXECUTE** → perform, re-observe, record the transition.
- **DEFER** → write or attach a `BlockedTask`, then **immediately continue
  elsewhere.** The crawl never waits for a human.
- **SKIP** → next candidate.

Deferred items are **aggregated on a normalized key** — field name + input type
+ route family — not on a generated prose description. Four pages needing a
policy number produce one ask, not four. (Matching on prose was the original
design's bug: descriptions vary in wording and the aggregation silently fails
in exactly the case it exists to handle.)

### F — RETURN (Story 2.11) — the step v1 didn't have

To try the second action on a page, you must first get back to that page. This
is the hidden cost of "exhaust all Tier 1 actions" and the original stories
never addressed it. It is now an explicit, budgeted ladder:

1. **Nothing to do** — the action didn't leave the state (tab switch,
   accordion, filter). Continue directly. *Cheapest, most common.*
2. **Browser back** — try it, then verify by re-fingerprinting. Accept only if
   the state matches.
3. **Re-navigate to the state's URL**, then re-fingerprint to confirm we
   actually landed in the same state.
4. **Replay the shortest known path** from the last stable entry point —
   bounded to a small number of steps, and only for Safe actions.
5. **Give up honestly** — mark this state's remaining untried actions
   `unreached`, record why, move to the next frontier item.

Rung 5 is not a failure mode, it is the design. Applications that hold state
server-side without deep-linkable URLs — ASP.NET WebForms postback, JSF,
wizard flows — will hit it, and the right behaviour is to report reduced
coverage clearly rather than burn the entire run budget replaying paths.

Each state carries a **return budget**. When it's spent, remaining actions are
marked unreached. This converts the original design's unbounded
worst case into a bounded, reportable one.

---

## 4. What happens when things go wrong

| Situation | Behaviour |
|---|---|
| Page won't settle | Best-effort capture, `DISC-004`, continue |
| Target returns 5xx / broken render | Bounded retries → `DiscoveryError` row, continue elsewhere |
| Worker crashes | Every typed row already written is the checkpoint; resume re-verifies the in-flight action rather than assuming it succeeded |
| Dialog won't close | Force-navigate back to the pre-dialog URL |
| Closed shadow root / cross-origin iframe | Logged as an unreachable container; counted in coverage |
| Can't return to a state | Remaining actions marked `unreached`; reported |
| Can't resolve required data | `BlockedTask`, aggregated, asked once at the end |
| Login session expires mid-run | Re-authenticate and resume (existing behaviour) |

Every `DiscoveryError` carries a machine code (`DISC-001`…`006`) **and** a
plain-language message with a suggested next action. Never one without the
other.

---

## 5. What the user gets at the end

Not a bare "Complete". A coverage report (Story 2.22) that states:

- **Reached** — states explored, actions exercised, forms captured
- **Blocked** — distinct data/approval asks, aggregated, each with the paths
  waiting on it
- **Skipped for safety** — what we refused to click, and why
- **Unreached** — states we couldn't return to, containers we couldn't enter
- **Errored** — branches that failed, with codes
- **Diagnostics** — state-identity scores, low-confidence widget detections,
  down-ranked locators, data values that were rejected by the app

The point of that last section is that **every heuristic in this engine is
tunable and every one of them will need tuning per application.** Without
visible scores nobody can tell an over-merging threshold from a genuinely small
app, and the product becomes unfalsifiable. This report is what makes the
system debuggable in the field.

---

## 6. Honest capability gradient

The engine is framework-agnostic — there is no per-framework code path
anywhere. But technology choices in the target still determine how much we get:

| Target application | Expected outcome |
|---|---|
| Modern SPA, semantic ARIA, real routing, test IDs | **Excellent** — high coverage, durable locators |
| Typical enterprise app on a mainstream component library | **Good** — high coverage, some low-confidence widgets, locators mostly stable |
| Heavy iframe/shadow-DOM portal (SAP, Salesforce) | **Good, once traversal lands** — the containers are the whole game |
| Legacy postback app (WebForms, JSF), generated IDs | **Partial** — state return frequently hits rung 5; locators need review |
| No-URL-change SPA (Ext JS, old Angular) | **Partial** — state identity runs without its cheap pre-filter; needs threshold tuning |
| Canvas / WebGL rendered UI | **Not supported** — no DOM semantics to read. Out of scope. |
| CAPTCHA-gated | **Not supported** |

Publish this table. Implying uniform coverage is how trust gets lost on the
first pilot.

---

## 7. Story map

| Story | Box it implements | Change from the 2026-07-29 batch |
|---|---|---|
| 2.9 | A — readiness, bounded sampling | Rewritten: explicit 3-signal readiness, MutationObserver |
| 2.10 | B — state identity | Rewritten: no-URL-SPA case, observable scores |
| 2.11 | C/D/E/F — planner, tiering, **state return** | Rewritten: state-return ladder is new |
| 2.12 | D — safety | Rewritten: explicit environment posture setting |
| 2.13 | D — data resolution | Rewritten: pool first, success feedback |
| 2.14 | A/C — widgets **+ iframe + shadow DOM** | Rewritten: containers were entirely missing |
| 2.15 | E — blocked frontier | Rewritten: normalized aggregation key |
| 2.16 | resume | **Replaced**: re-crawl from entry point, not step replay |
| 2.17 | pause/resume across sessions | Light update |
| 2.18 | crash recovery, error taxonomy | Light update |
| 2.19 | D — loop guards | Light update |
| 2.20 | 0.1 — **Test Data Pool** | **New** |
| 2.21 | C — **locator durability** | **New** |
| 2.22 | 2.1 — **coverage report & diagnostics** | **New** |

**Build order** (value-first, dependency-respecting):

```
[2.22 Task 1 only]                     ← the diagnostics sink contract, first
  → 2.14 → 2.9 → 2.21 → 2.10 → 2.11 → 2.19
  → 2.20 → 2.13 → 2.12 → 2.15
  → [2.22 remainder] → 2.18 → 2.17 → 2.16
```

**2.22 splits.** Its Task 1 defines `record_diagnostic()`, which seven stories
(2.10, 2.11, 2.12, 2.13, 2.14, 2.19, 2.21) write through. Build that one task
before any of them; reconciling seven independently-invented logging shapes
afterwards costs more than the feature. The rest of 2.22 — aggregation, the API
surface — waits until its producers exist.

2.14 and 2.9 next because they raise the floor on every subsequent story.
2.21 early because it is cheap and it is what makes the output worth anything.
2.16 last because it is the least valuable and the most likely to be cut.
