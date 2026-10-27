"""Small, pure judgement helpers used by the understanding loop — no I/O, so
they're the unit-tested core (tests/test_sense.py)."""

import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_ID_SEGMENT = re.compile(
    r"^(\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,}|[A-Z]{1,4}-?\d{3,}"
    # generated ids mixing letters and digits (FNOL-W84R-7NRY, nanoid
    # V1StGXR8_Z5jdHi6B): 6+ id characters with at least 3 digits, so words
    # like "settings-v2" stay words
    r"|(?=(?:[^\d]*\d){3})[A-Za-z0-9_-]{6,})$",
    re.IGNORECASE,
)
_LOGOUT = re.compile(r"\b(log ?out|sign ?out|logoff)\b", re.IGNORECASE)
_SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "blob:")
_FILE_EXT = re.compile(r"\.(pdf|zip|csv|xlsx?|docx?|png|jpe?g|gif|svg|mp4|exe|dmg)$", re.IGNORECASE)


_INDEX_FILE = re.compile(r"/(index|default)\.(html?|aspx?|php|jsp)$", re.IGNORECASE)
_DEFAULT_PORT = re.compile(r":(80|443)$")


def _collapse(route: str) -> str:
    return "/".join("{id}" if _ID_SEGMENT.match(seg) else seg for seg in route.split("/"))


# Query keys that switch between views of one page (`?view=owe`, `?tab=cards`):
# their word values name different places, unlike ids, search text or sorting.
_VIEW_KEYS = re.compile(r"^(view|tab|section|panel|mode|type|status|category)$", re.IGNORECASE)
_WORD = re.compile(r"^[A-Za-z][A-Za-z_-]{1,30}$")


def _query_keys(query: str) -> str:
    kept = set()
    for kv in query.split("&"):
        key, _, value = kv.partition("=")
        if key:
            view = _VIEW_KEYS.match(key) and _WORD.match(value)
            kept.add(f"{key}={value.lower()}" if view else key)
    return "&".join(sorted(kept))


def url_pattern(url: str) -> str:
    """One name per place in the app, whatever the framework routes on:

    - path routes (React Router, Next.js, Angular, server pages):
      `/customers/17` and `/customers/9031` are `/customers/{id}`;
    - query strings: values dropped, keys kept (sorted) — also inside a
      hash route (`#/claim?ref=A` = `#/claim?ref=B`);
    - hash routes (`#/claims`, hashbang `#!/claims`) are kept: single-page
      apps route on them. A plain in-page anchor (`#billing`, `#top`) is
      not a route and is dropped.
    - the same page written differently is one place: scheme, default
      port, trailing slashes, `index.html`, an empty `#/`."""
    parts = urlsplit(url)
    path = _collapse(_INDEX_FILE.sub("", parts.path)).rstrip("/") or "/"
    route, _, route_query = parts.fragment.lstrip("!").partition("?")
    # ponytail: a hash route must start with "/" (`#/x`, `#!/x`); a router
    # using bare words (`#customers`) reads as an anchor. Treat those as
    # routes too if such an app turns up.
    route = _collapse(route).rstrip("/") if route.startswith("/") else ""
    fragment = route + (f"?{_query_keys(route_query)}" if route and route_query else "")
    netloc = _DEFAULT_PORT.sub("", parts.netloc.lower())
    return urlunsplit(("", netloc, path, _query_keys(parts.query), fragment))


def same_place(landed: str, target: str) -> bool:
    """Did opening `target` arrive there? Landing on the same place, or
    somewhere inside it (`/orders/7` → `/orders/7/summary`, a common
    redirect), counts; being sent elsewhere (home, sign-in) doesn't."""
    here, there = url_pattern(landed), url_pattern(target)
    return here == there or here.startswith(there.rstrip("/") + "/")


def is_explorable_link(href: str, base_origin: str, text: str = "") -> bool:
    if not href or href.startswith(_SKIP_SCHEMES) or href == "#":
        return False
    if _LOGOUT.search(text) or _LOGOUT.search(href.replace("-", " ").replace("_", " ")):
        return False
    if _FILE_EXT.search(urlsplit(href).path):
        return False
    parts = urlsplit(href)
    return f"{parts.scheme}://{parts.netloc}".lower() == base_origin.lower()


def is_sign_out(label: str) -> bool:
    return bool(_LOGOUT.search(label))


def is_risky_label(label: str) -> bool:
    """Words we never click during understanding — they change or destroy
    data, or end the session."""
    return bool(
        re.search(
            r"\b(delete|remove|destroy|cancel (policy|order|account)|deactivate|approve|reject|pay|"
            r"purchase|checkout|submit|save|confirm|send|transfer|archive|reset|log ?out|sign ?out)\b",
            label,
            re.IGNORECASE,
        )
    )


def plain_label(text: str) -> str:
    """Words only, lower case: the model names "💳 CARDS ›" as "Cards"."""
    return " ".join(re.sub(r"[^\w&]+", " ", text).lower().split())


def page_link(inventory: dict[str, Any], label: str) -> str | None:
    """The address a visible link with this label opens, when it opens a
    real page (not `#`). Pressing such a link only navigates."""
    want = plain_label(label)
    for item in inventory.get("links", []):
        href = item.get("href") or ""
        if href and "#" not in href and plain_label(item.get("text") or "") == want:
            return href
    return None


def is_risky_link(label: str, href: str) -> bool:
    """A link only opens a page, so words that name a page ("Payment &
    Transfer", "Send money") are fine to follow — only links that end the
    session or destroy something are skipped."""
    words = f"{label} {urlsplit(href).path.replace('-', ' ').replace('_', ' ').replace('/', ' ')}"
    return bool(
        _LOGOUT.search(words)
        or re.search(r"\b(delete|remove|destroy|deactivate)\b", words, re.IGNORECASE)
    )


def looks_final(label: str) -> bool:
    """Would pressing this commit something for real? Postponing or moving on
    ("Skip - send photos later", "Continue") is not final even if it
    contains a risky word."""
    if re.search(r"\b(skip|later|continue|next|back|cancel)\b", label, re.IGNORECASE):
        return False
    return is_risky_label(label)


def screen_signature(entity: str | None, view_kind: str, mode: str | None, name: str) -> str:
    """Identity of a screen by *meaning*. Falls back to the screen name when
    the model couldn't name a business entity (dashboards, settings...)."""

    def norm(value: str | None) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
        # crude singularisation so "Quotes" and "Quote" merge
        return " ".join(
            w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
            for w in cleaned.split()
        )

    subject = norm(entity) or norm(name)
    # Every step of a form/wizard is its own screen even though they all
    # work on the same business thing (FNOL: policy step, vehicle step...).
    if norm(view_kind) in ("wizard", "form") and entity:
        subject = f"{norm(entity)}/{norm(name)}"
    return f"{subject}|{norm(view_kind) or 'other'}|{norm(mode)}"


_SEVERITY_WEIGHT = {"high": 12, "medium": 5, "low": 2}


def health_score(issues: list[tuple[str, int]], pages_seen: int) -> int:
    """0-100. Each (severity, occurrences) costs points; repeated issues cost
    a little more but saturate so one noisy endpoint can't zero the score.
    Scaled by how much of the app was seen, so 3 problems on 40 screens hurts
    less than 3 problems on 4 screens."""
    if pages_seen <= 0:
        return 0
    penalty = 0.0
    for severity, occurrences in issues:
        weight = _SEVERITY_WEIGHT.get(severity, 2)
        penalty += weight * min(1 + (occurrences - 1) * 0.25, 2.0)
    scale = max(0.5, min(1.5, 10 / pages_seen))
    return max(0, min(100, round(100 - penalty * scale)))


REQUIREMENTS_FIRST_BELOW = 60


def health_label(score: int) -> str:
    if score >= 85:
        return "Healthy"
    if score >= REQUIREMENTS_FIRST_BELOW:
        return "Some problems"
    return "Unhealthy"


_NEEDS_HUMAN = re.compile(
    r"\b(delete|remove|destroy|deactivate|terminate|pay|buy|sell|redeem|purchase|checkout|check out|transfer|"
    r"withdraw|password|approve|reject|decline|archive|refund|place order|log ?out|sign ?out|"
    # A plain "Reset" only clears a form or its filters; resetting data does not.
    r"reset (?:\w+ ){0,2}(?:account|data|settings|everything|all)|"
    r"cancel (?:\w+ ){0,3}(policy|order|account|subscription|claim))\b",
    re.IGNORECASE,
)


def needs_human_ok(label: str, goal: str = "") -> bool:
    """Actions Explorer never takes on its own, in any environment: they
    destroy data, move money, make business decisions or end the session.
    A plain button that carries out the task's risky action counts too:
    "Cancel" while the task is cancelling a policy."""
    if _NEEDS_HUMAN.search(label):
        return True
    risky = _NEEDS_HUMAN.search(goal)
    return bool(risky) and risky.group(0).split()[0].lower() in plain_label(label).split()


def may_commit(label: str, non_production: bool) -> bool:
    """May a mission press a final Save/Submit/Create? Only on a test
    environment, and never for anything that needs a human's OK."""
    return non_production and not needs_human_ok(label)


_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"]  # fmt: skip


def date_variants(value: str) -> list[str]:
    """Ways a person might type a date into a picker that only accepts its
    own display format. The raw value is always tried first."""
    match = re.match(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})", value)
    if not match:
        return [value]
    year, month, day = int(match[1]), int(match[2]), int(match[3])
    if not 1 <= month <= 12:
        return [value]
    mon = _MONTHS[month - 1]
    candidates = [
        value,
        f"{mon[:3]} {day}, {year}",
        f"{month:02d}/{day:02d}/{year}",
        f"{day:02d}/{month:02d}/{year}",
        f"{year}-{month:02d}-{day:02d}",
        f"{day:02d}-{month:02d}-{year}",
        f"{mon} {day}, {year}",
        f"{day} {mon[:3]} {year}",
    ]
    return list(dict.fromkeys(candidates))


# Screens that show the app keeps progress per account (a saved draft, a
# cart). Parallel agents on one account would overwrite each other's state
# there — and report the mess as app bugs.
_KEEPS_STATE = re.compile(
    # "resume" alone is often a CV ("upload resume"): only resuming work counts.
    r"\b(resume (your |my |the |a )?(saved |unfinished )?(report|progress|application|draft|"
    r"claim|order|form|where)|unfinished|saved (report|progress|application|draft|form)|draft|"
    r"where you left off|shopping cart|basket)\b",
    re.IGNORECASE,
)
# The "start fresh" answer to a "resume your saved progress?" prompt.
START_FRESH = re.compile(r"^\s*(start (over|again|fresh|afresh|a new)|discard|begin again)\b", re.I)
# FNOL words it "Pick up where you left off" — missing that left every
# replayed test stuck on the prompt (the handler only answers it when it
# recognises the resume button).
RESUME_LABEL = re.compile(
    r"\b(resume|pick up where|carry on (where|with)|continue (where|my|your|saved))\b",
    re.IGNORECASE,
)
# The way past an in-between screen a recorded path didn't have ("this is a
# separate event — continue", "not now", "skip"). Never the resume answer:
# that would load an old draft instead of the test's own steps.
CONTINUE_LIKE = re.compile(
    r"^\s*(continue|next|proceed|skip|not now|no,? thanks|"
    r"(this|it)( is|'s) (a )?(new|different|separate)|report (it )?(anyway|separately))\b",
    re.IGNORECASE,
)

# The answers that wave away a warning an app shows only sometimes (a
# possible duplicate, an upsell). Whether it shows depends on what earlier
# runs left behind, so a test must not insist on pressing it.
DISMISS_LIKE = re.compile(
    r"^\s*(not now|no,? thanks|(this|it)( is|'s) (a )?(new|different|separate)|"
    r"report (it )?(anyway|separately))\b",
    re.IGNORECASE,
)


def keeps_state(screen_texts: list[str]) -> bool:
    """ponytail: keyword guess from screen names/purposes; a per-app
    'keeps state' answer from the user would be the exact version."""
    return any(_KEEPS_STATE.search(t or "") for t in screen_texts)


def resumes_saved_progress(script: list[dict]) -> bool:
    """Does this recorded test deliberately pick 'resume' on a saved-progress
    prompt? Then that prompt is the point of the test, not an interruption."""
    return any(
        s.get("do") in ("click", "choose")
        and RESUME_LABEL.search(str(s.get("label") or s.get("option") or ""))
        for s in script
    )


_RELATIVE = re.compile(r"\{\{\s*(today|now)\s*(?:([+-])\s*(\d+)\s*([dhm]))?\s*\}\}", re.IGNORECASE)


def resolve_relative(value: str, now: datetime | None = None) -> str:
    """`{{today+1d}}` -> tomorrow as YYYY-MM-DD, `{{now-2h}}` -> YYYY-MM-DD
    HH:MM. Worked out each time the step runs, so a 'future date is
    rejected' test is still about the future when it is replayed later."""
    now = now or datetime.now()

    def one(m: re.Match[str]) -> str:
        amount = int(m[3] or 0) * (-1 if m[2] == "-" else 1)
        unit = (m[4] or "d").lower()
        moment = now + timedelta(**{{"d": "days", "h": "hours", "m": "minutes"}[unit]: amount})
        return moment.strftime("%Y-%m-%d" if m[1].lower() == "today" else "%Y-%m-%d %H:%M")

    return _RELATIVE.sub(one, value)


# A walk that keeps landing on the same screens is going in circles (seen on
# FNOL: Add claim photos <-> Claim status for 30 minutes). A real task moves
# forward; these thresholds leave room for an honest back-and-forth or two.
CYCLE_REPEATS = 3
MAX_VISITS_PER_SCREEN = 4


def going_in_circles(screens: list[str]) -> str | None:
    """The screens a walk has landed on, in order. Returns a plain sentence
    when the tail is the same 1-3 screens repeating CYCLE_REPEATS times, or
    one screen has been landed on more than MAX_VISITS_PER_SCREEN times."""
    for period in (1, 2, 3):
        span = period * CYCLE_REPEATS
        if len(screens) >= span:
            tail = screens[-span:]
            loop = tail[:period]
            if all(tail[i] == loop[i % period] for i in range(span)):
                if period == 1:
                    return f"stayed on {loop[0]} {CYCLE_REPEATS} times without moving on"
                return "kept going round " + " → ".join(loop) + f" ({CYCLE_REPEATS} times)"
    counts: dict[str, int] = {}
    for name in screens:
        counts[name] = counts.get(name, 0) + 1
        if counts[name] > MAX_VISITS_PER_SCREEN:
            return f"came back to {name} {counts[name]} times without finishing"
    return None


def _route_url(url: str) -> str:
    # "/app/", "/app/#" and "/app/#/" are the same entry; "#/Inner" is not.
    return url.rstrip("/").removesuffix("#/").removesuffix("#").rstrip("/")


def route_starts_at_entry(script: list[dict[str, str]], entry_urls: set[str]) -> bool:
    """A test's route is replayable in any clean browser, for any app, only if
    it begins by opening an entry point (the app's start address or where
    sign-in lands) and then gets everywhere else by the user's own actions.
    Opening an inner page by its address worked live only because that
    browser still held the earlier steps' state (a wizard's answers, a
    selected record); a fresh browser lands somewhere else."""
    if not script or script[0].get("do") != "goto":
        return False
    entries = {_route_url(u) for u in entry_urls}
    if _route_url(str(script[0].get("url") or "")) not in entries:
        return False
    return not any(step.get("do") == "goto" for step in script[1:])


# Scenarios that are themselves about resuming saved progress; every other
# scenario starts fresh, so a draft left by an earlier run never steers it.
_ABOUT_RESUMING = re.compile(
    r"\b(resum\w*|pick(s|ed|ing)? up where|unfinished|saved (claim|draft|report|"
    r"progress|application|form|order|cart)|continue later|save and (exit|return)|draft)\b",
    re.I,
)


def about_resuming(text: str) -> bool:
    return bool(_ABOUT_RESUMING.search(text or ""))
