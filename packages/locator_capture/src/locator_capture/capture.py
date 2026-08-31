"""Pure DOM/locator-extraction helpers — no dependency on any crawl-run
state (no `DiscoveryRun`/BFS/`_CaptureSink`). Extracted verbatim from
`discovery_worker/crawler.py` (Story 2.21) so `execution_worker`'s
self-heal live inspection can reuse the exact same locator-ranking logic
discovery's own crawl already relies on, without a cross-worker-app
dependency on `discovery_worker` itself.
"""

import re

from playwright.async_api import Locator, Page

_NO_TEXT_TAGS = {"input", "select", "textarea"}


async def capture_selector(locator: Locator, fallback_text: str | None = None) -> str:
    """Whatever selector info is reasonably available, in priority order:
    data-testid, id, name, or a text/role fallback — needed by Story 2.5 to
    derive a usable `ComponentLocator` for this element."""
    testid = await locator.get_attribute("data-testid")
    if testid:
        return f'[data-testid="{testid}"]'
    el_id = await locator.get_attribute("id")
    if el_id:
        return f"#{el_id}"
    name = await locator.get_attribute("name")
    if name:
        return f'[name="{name}"]'
    tag = await locator.evaluate("el => el.tagName.toLowerCase()")
    # input/select/textarea never render fallback_text as real innerText —
    # a `text=` selector built from it (a field's internal name/id) could
    # never match real page content, unlike for a button/link.
    if fallback_text and tag not in _NO_TEXT_TAGS:
        return f'text="{fallback_text}"'
    return f"css={tag}"


# Story 2.21 AC 1: capture-time ranked locator candidates. Tier order —
# lower is more durable. `capture_selector` above stays untouched (existing
# consumers of `captured_selector` keep working); this is the new, additive
# path Story 2.5's `ComponentLocator` derivation extends to consume.
_LOCATOR_TIER_ORDER = {
    "testid": 0,
    # A real, non-generated CSS attribute (id/name/class — `css_scoped`)
    # ranks above name/text-derived strategies: a button/link's own visible
    # text becomes its "aria" accessible name AND its "text" candidate, so
    # any other element sharing that same common label (a generic verb like
    # "Logout"/"Submit"/"Close" reused across a header, a mobile-nav clone,
    # a modal, etc.) matches it too. A real class/id doesn't have that
    # collision risk nearly as often. (A CSS-in-JS-style generated class is
    # still caught and ranked below via `_is_fragile_locator_value` — this
    # reordering only ever promotes a class/id that already passed that
    # check.) Only `_resolve_known_application_model_sync`
    # (generation_worker/activities.py) ever surfaces to the AI, so
    # whichever candidate ranks here IS the only one it ever sees.
    "css_scoped": 1,
    "css_value": 2,
    "aria": 3,
    "text": 4,
    "label": 5,
    "css_absolute": 6,
}

# Story 2.21 AC 2: machine-generated identifiers, syntactically valid CSS but
# semantically worthless — a value matching any of these is down-ranked below
# every human-meaningful alternative, never discarded outright.
#
# `word-word` alone (e.g. "data-testid", "save-button") is indistinguishable
# from a real CSS-in-JS hash by shape — the actual signal is that a hash's
# second segment isn't a dictionary word: it contains a digit
# (`css-1x2y3z`) or mixes case in a way an English word never does
# (`sc-hKgILt`). `_looks_like_generated_token` carries that distinction;
# the regex below only finds the candidate segment to test.
_HYPHENATED_SEGMENT_RE = re.compile(r"\b[a-zA-Z]{1,10}-([0-9a-zA-Z]{5,})\b")
_FRAMEWORK_GENERATED_ID_RE = re.compile(
    r"ctl00_|ContentPlaceHolder|^gwt-|^ext-gen|^x-auto", re.IGNORECASE
)
_HEX_OR_UUID_FRAGMENT_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{12,}", re.IGNORECASE
)
_POSITIONAL_ONLY_PATH_RE = re.compile(
    r"^(css=)?(\w+:nth-child\(\d+\)\s*(>|\s)\s*)*\w+:nth-child\(\d+\)$"
)
# Defense in depth alongside the `_LOCATOR_INFO_SCRIPT` name-computation fix
# above: a `name=`/`text=` quoted value that's purely a number (optionally
# with currency/percent/thousands punctuation) is data — a real loan
# principal, interest rate, or term — never a stable label, whichever field
# happened to carry it at capture time (the site's own pre-filled example
# value, or a synthetic fill). Catches this shape wherever else it might
# surface (e.g. a confirmation page's own rendered text), not just the one
# call site the fix above closes.
_QUOTED_NUMERIC_VALUE_RE = re.compile(
    r'(?:name|text)="[\s$€£¥₹]*[\d,]+(?:\.\d+)?\s*%?"'
)


def _looks_like_generated_token(token: str) -> bool:
    has_digit = any(c.isdigit() for c in token)
    has_mixed_case = any(c.isupper() for c in token) and any(c.islower() for c in token)
    return has_digit or has_mixed_case


def _is_fragile_locator_value(value: str) -> bool:
    if any(
        _looks_like_generated_token(m.group(1)) for m in _HYPHENATED_SEGMENT_RE.finditer(value)
    ):
        return True
    return bool(
        _FRAMEWORK_GENERATED_ID_RE.search(value)
        or _HEX_OR_UUID_FRAGMENT_RE.search(value)
        or _POSITIONAL_ONLY_PATH_RE.match(value)
        or _QUOTED_NUMERIC_VALUE_RE.search(value)
    )


# One round trip, computed while the element is live — deriving this from a
# stored DOM snapshot afterwards loses the accessibility context (computed
# role, accessible name) tiers 2 and 4 depend on (Dev Notes).
_LOCATOR_INFO_SCRIPT = r"""
(el) => {
  function nthOfTag(node) {
    let idx = 1, sib = node;
    while ((sib = sib.previousElementSibling)) if (sib.tagName === node.tagName) idx++;
    return node.tagName.toLowerCase() + ':nth-child(' + idx + ')';
  }
  function absolutePath(node) {
    const parts = [];
    while (node && node.nodeType === 1 && node !== document.documentElement) {
      parts.unshift(nthOfTag(node));
      node = node.parentElement;
    }
    return parts.join(' > ');
  }
  function scopedPath(node) {
    let depth = 0, cur = node.parentElement, scope = null;
    while (cur && depth < 4) {
      if (cur.id) { scope = cur; break; }
      cur = cur.parentElement; depth++;
    }
    if (!scope) return null;
    const parts = [];
    let n = node;
    while (n && n !== scope) { parts.unshift(nthOfTag(n)); n = n.parentElement; }
    return '#' + scope.id + (parts.length ? ' > ' + parts.join(' > ') : '');
  }
  const implicitRoles = {
    BUTTON: 'button', A: 'link', INPUT: 'textbox', SELECT: 'combobox', TEXTAREA: 'textbox',
  };
  const isFormControl = el.tagName === 'INPUT' || el.tagName === 'SELECT'
    || el.tagName === 'TEXTAREA';
  let label = null;
  if (el.id) {
    const lab = document.querySelector('label[for="' + el.id + '"]');
    if (lab) label = lab.innerText.trim();
  }
  if (!label && el.closest('label')) label = el.closest('label').innerText.trim();
  const testid = el.getAttribute('data-testid') || el.getAttribute('data-test')
    || el.getAttribute('data-cy');
  return {
    testid: testid,
    role: el.getAttribute('role') || implicitRoles[el.tagName] || null,
    // A form control's accessible name never legitimately falls back to its
    // current `.value` (whatever happens to be typed in at capture time,
    // e.g. discovery's own synthetic fill) or `innerText` (inputs/selects/
    // textareas never render meaningful innerText anyway) — only a real
    // static `aria-label` counts here; `label` (below) and `placeholderAttr`
    // are this script's other, separately-ranked signals for an unlabeled
    // control. A non-form element's accessible name still legitimately
    // falls back to its own innerText (a button/link's visible text really
    // is its accessible name).
    name: (
      el.getAttribute('aria-label') || (isFormControl ? '' : el.innerText) || ''
    ).trim().slice(0, 80),
    label: label,
    text: (el.innerText || '').trim().slice(0, 80),
    tag: el.tagName.toLowerCase(),
    idAttr: el.id || null,
    nameAttr: el.getAttribute('name') || null,
    placeholderAttr: isFormControl ? (el.getAttribute('placeholder') || null) : null,
    // A form control's pre-set `.value` (the page's own static default, or
    // whatever discovery itself already typed in before this capture runs)
    // is never used as the "name" above — but for a control with no
    // testid/id/name/label/placeholder at all, it's still the only concrete,
    // verifiable signal left; captured separately so it can only ever become
    // its own explicitly-fragile candidate, never masquerade as a name.
    valueAttr: (isFormControl && el.value) ? String(el.value).trim().slice(0, 80) : null,
    firstClass: (el.className || '').trim().split(/\s+/)[0] || null,
    scoped: scopedPath(el),
    absolute: absolutePath(el),
  };
}
"""


def _build_locator_candidates(info: dict, frame_path: str | None) -> list[dict]:
    candidates: list[dict] = []

    def add(strategy: str, value: str | None, *, force_fragile: bool = False) -> None:
        if not value:
            return
        # "label" isn't a real Playwright selector engine — its value is
        # the raw label text for `getByLabel(...)`, not a `page.locator()`
        # selector string, so it never gets a frame_path `>>` prefix either.
        full_value = value if strategy == "label" else (
            f"{frame_path} >> {value}" if frame_path else value
        )
        candidates.append(
            {
                "strategy": strategy,
                "value": full_value,
                "fragile": force_fragile or _is_fragile_locator_value(value),
            }
        )

    if info.get("testid"):
        add("testid", f'[data-testid="{info["testid"]}"]')
    if info.get("role") and info.get("name"):
        add("aria", f'role={info["role"]}[name="{info["name"]}"]')
    if info.get("text"):
        add("text", f'text="{info["text"]}"')
    if info.get("label"):
        add("label", info["label"])
    if info.get("idAttr"):
        add("css_scoped", f"#{info['idAttr']}")
    # A form control's own HTML `name` attribute — distinct from its ARIA
    # accessible name (`info["name"]` above) — is durable in practice (real
    # sites rarely rename a submitted field) and, for the very common
    # unlabeled-input case, is often the ONLY human-meaningful signal this
    # element has at all; without it, such a field had nothing better than
    # the fragile absolute path to fall back to.
    if info.get("nameAttr"):
        add("css_scoped", f'[name="{info["nameAttr"]}"]')
    # A placeholder genuinely IS a control's real ARIA accessible name once
    # no label/aria-label exists (confirmed by both fields together being
    # empty here) — but unlike a static label, it can echo dynamic/example
    # content (a currency hint, a rotating example), so it's captured as its
    # own explicitly-fragile "aria" candidate: usable, ranked below every
    # non-fragile alternative, never the sole reason a field gets no
    # candidate at all. `ponytail:` no attempt to tell a static hint
    # ("Enter your email") apart from a dynamic example ("e.g. 500000") —
    # both get the same fragile treatment; upgrade only if a real target's
    # own placeholder churn proves this too conservative.
    if not info.get("label") and not info.get("name") and info.get("placeholderAttr"):
        add(
            "aria",
            f'role={info.get("role")}[name="{info["placeholderAttr"]}"]',
            force_fragile=True,
        )
    # Last resort for a control with no testid/id/name/label/placeholder at
    # all: an attribute selector on its own pre-set value. Fragile (a later
    # fill legitimately changes it) but still a concrete, verifiable
    # locator — better than falling straight through to a pure positional
    # path that breaks the moment an unrelated sibling element is added.
    if info.get("valueAttr"):
        add("css_value", f'{info.get("tag") or "input"}[value="{info["valueAttr"]}"]', force_fragile=True)
    if info.get("firstClass"):
        add("css_scoped", f"css=.{info['firstClass']}")
    if info.get("scoped"):
        add("css_scoped", f"css={info['scoped']}")
    if info.get("absolute"):
        add("css_absolute", f"css={info['absolute']}")

    seen: set[tuple[str, str]] = set()
    deduped = []
    for c in candidates:
        key = (c["strategy"], c["value"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    deduped.sort(key=lambda c: (c["fragile"], _LOCATOR_TIER_ORDER.get(c["strategy"], 9)))
    return deduped


async def capture_locator_candidates(
    locator: Locator, fallback_text: str | None = None, frame_path: str | None = None
) -> list[dict]:
    """Story 2.21 AC 1/2/3: the ranked, fragility-aware candidate list.
    Best-effort — a capture failure (a detached/stale element) yields an
    empty list rather than raising, same tolerance as every other capture
    helper in this file."""
    try:
        info = await locator.evaluate(_LOCATOR_INFO_SCRIPT)
    except Exception:
        return []
    # input/select/textarea never render innerText — stamping a fallback
    # (a field's internal name/id) in as "text" would produce a `text=`
    # candidate that can never match real page content.
    if not info.get("text") and fallback_text and info.get("tag") not in _NO_TEXT_TAGS:
        info["text"] = fallback_text
    return _build_locator_candidates(info, frame_path)


# Self-heal live inspection (execution_worker) needs a page-level entry
# point, not just a per-element one — capture_selector/capture_locator_
# candidates above both take an already-resolved Locator, which discovery's
# own crawl gets from following its own DOM traversal. Live inspection has
# no such traversal: it just has a bare Page it navigated to, and needs
# "give me every plausible locator on this page" in one call. Bounded to
# max_candidates so an inspection call stays cheap and the AI prompt it
# feeds doesn't balloon — this is a snapshot for diagnosis, not a full
# capture pass.
_INTERACTIVE_ELEMENTS_SELECTOR = "button, a, input, select, textarea, [role], [data-testid]"


async def extract_page_locator_snapshot(page: Page, *, max_candidates: int = 40) -> list[dict]:
    """Bounded, page-scoped locator snapshot: every interactive element
    currently on `page` (button/link/input/select/textarea/[role]/
    [data-testid]), up to `max_candidates`, each run through
    `capture_locator_candidates`. Never follows a link or queries a second
    page — the caller is responsible for navigating to the right page
    first."""
    locator = page.locator(_INTERACTIVE_ELEMENTS_SELECTOR)
    count = min(await locator.count(), max_candidates)
    results: list[dict] = []
    for i in range(count):
        element = locator.nth(i)
        try:
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
        except Exception:
            continue
        for candidate in await capture_locator_candidates(element):
            results.append({**candidate, "element_tag": tag})
    return results
