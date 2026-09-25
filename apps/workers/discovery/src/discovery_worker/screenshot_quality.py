"""Deterministic Screenshot Content Score — picks the most meaningful of a
Journey's several candidate screenshots (its steps' Pages) without an LLM/
vision model. Pure, local, and cheap: no browser navigation, no network call,
no OCR — image analysis runs once on bytes the crawler already captured, and
the DOM evidence it's combined with (`structural_tokens`/`heading`/
`page_settled`) is already computed once per Page by `_capture_state_signals`
(crawler.py) and `wait_for_page_ready`'s own readiness gate — reused as-is,
not recomputed.

Four sub-scores, each normalized to [0, 1], weighted to roughly the
DOM 40 / visual 30 / text 20 / page-state 10 split a screenshot's actual
usefulness tends to follow — DOM structure is the strongest signal (it's
ground truth from the real page, not a pixel guess), visual density catches
what DOM alone can't (a settled page that's still visually near-empty), and
the "text evidence" bucket substitutes captured DOM tags/roles for OCR
(explicitly out of scope — no heavy dependency, no extra pass over the
image) since a real content page almost always has *some* text-bearing
structure (headings, table cells, list items, labels) even before OCR would
ever need to read the pixels.

Deliberately does NOT try to tell a blank/failed capture apart from a
legitimate empty-state page ("No users found.") by looking for the absence
of content — an empty-state page still has a full, settled DOM (nav chrome,
page heading, an empty-state message element, layout structure) and a
normal-looking screenshot; only a genuinely blank/loading/mid-render capture
scores low on every one of these signals at once.
"""

import io
import logging

from PIL import Image, ImageFilter, ImageStat

logger = logging.getLogger(__name__)

# Meaningful content/interactive DOM evidence — a real, rendered application
# page overwhelmingly has several of these; a blank or still-loading capture
# has none. Matched against both the bare tag and any role `_STATE_SIGNALS_
# SCRIPT` (crawler.py) folded into a token like "button[button]"/"div[list]".
_MEANINGFUL_TAGS = frozenset(
    {
        "table", "form", "input", "select", "textarea", "button",
        "ul", "ol", "li", "img", "a", "h1", "h2", "h3", "h4",
        "thead", "tbody", "tr", "td", "th", "label", "nav",
    }
)
_MEANINGFUL_ROLES = frozenset(
    {
        "table", "list", "listitem", "button", "link", "textbox",
        "combobox", "checkbox", "radio", "row", "cell", "columnheader",
        "navigation", "heading", "tab", "grid",
    }
)

# Normalization ceilings — deliberately generous, not exact: these only need
# to separate "clearly sparse" from "clearly substantial", not rank pages
# precisely against each other. Tune here if real data shows otherwise; nothing
# downstream depends on the exact constant.
_DOM_ELEMENT_COUNT_CEILING = 80
_MEANINGFUL_TOKEN_COUNT_CEILING = 15
_EDGE_INTENSITY_CEILING = 40.0
_THUMBNAIL_SIZE = (128, 128)

_DOM_WEIGHT = 0.4
_VISUAL_WEIGHT = 0.3
_TEXT_WEIGHT = 0.2
_PAGE_STATE_WEIGHT = 0.1


def _is_meaningful_token(token: str) -> bool:
    tag, _, role_part = token.partition("[")
    role = role_part.rstrip("]")
    return tag in _MEANINGFUL_TAGS or role in _MEANINGFUL_ROLES


def _dom_structure_score(structural_tokens: list[str], *, page_settled: bool) -> float:
    """40% weight — the single strongest signal, since it's ground truth
    from the real page rather than inferred from pixels. A page that never
    settled (Story 2.9's own readiness gate) is very likely blank/mid-load
    regardless of how many elements happened to exist at capture time."""
    size_score = min(len(structural_tokens) / _DOM_ELEMENT_COUNT_CEILING, 1.0)
    settled_score = 1.0 if page_settled else 0.0
    return 0.7 * settled_score + 0.3 * size_score


def _text_evidence_score(structural_tokens: list[str], heading: str) -> float:
    """20% weight — a DOM-based stand-in for OCR/text density (explicitly
    out of scope): counts text-bearing/content tags and roles already
    captured, plus whether a real heading was found. Legitimate empty-state
    pages ("No users found.") still have this (a heading, a table shell,
    label/nav chrome) — only a genuinely blank capture has none of it."""
    meaningful_count = sum(1 for t in structural_tokens if _is_meaningful_token(t))
    tag_score = min(meaningful_count / _MEANINGFUL_TOKEN_COUNT_CEILING, 1.0)
    heading_score = 1.0 if heading.strip() else 0.0
    return 0.7 * tag_score + 0.3 * heading_score


def _image_scores(image_bytes: bytes) -> tuple[float, float]:
    """Returns (visual_density_score, page_state_score) — decodes the PNG
    bytes exactly once and derives both from the same downscaled thumbnail,
    per the "avoid opening the same image multiple times" requirement.
    Never raises: a corrupt/undecodable image (or occasionally happens live
    — a zero-byte screenshot from a mid-navigation capture race) is itself
    evidence of a bad capture, so it scores both components 0 rather than
    failing screenshot selection outright."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            thumbnail = img.convert("RGB").resize(_THUMBNAIL_SIZE)
    except Exception:
        logger.warning("screenshot_quality: could not decode screenshot bytes", exc_info=True)
        return 0.0, 0.0

    # Blank/background ratio (page-state, 10%): the dominant color's share
    # of a small, fixed-size sample — a blank/near-blank capture is almost
    # entirely one color; real UI is not.
    total_pixels = _THUMBNAIL_SIZE[0] * _THUMBNAIL_SIZE[1]
    # `getcolors` returns `None` when the image has more distinct colors
    # than `maxcolors` — can't happen with this thumbnail (at most
    # `total_pixels` distinct colors exist, exactly the cap used here), but
    # the return type doesn't guarantee it, and "never raises" is this
    # function's own contract.
    colors = thumbnail.getcolors(maxcolors=total_pixels)
    # `None` would mean *more* distinct colors than pixels — impossible,
    # but if it ever happened that's a busy image, not a blank one, so the
    # fallback leans "not blank" (0), not "blank" (total_pixels).
    dominant_count = max((count for count, _ in colors), default=0) if colors else 0
    blank_ratio = dominant_count / total_pixels
    page_state_score = 1.0 - blank_ratio

    # Edge/content density (visual, 30%): mean intensity of an edge-filtered
    # grayscale thumbnail — a blank/loading screen has almost no edges; real
    # UI (text, borders, controls, table grid lines) has plenty.
    edges = thumbnail.convert("L").filter(ImageFilter.FIND_EDGES)
    mean_edge_intensity = ImageStat.Stat(edges).mean[0]
    visual_density_score = min(mean_edge_intensity / _EDGE_INTENSITY_CEILING, 1.0)

    return visual_density_score, page_state_score


def score_screenshot(
    image_bytes: bytes,
    *,
    structural_tokens: list[str] | None,
    heading: str | None,
    page_settled: bool,
) -> float:
    """The Screenshot Content Score (0.0-1.0, higher is more meaningful) —
    the sole entry point every caller uses. Deterministic and local: no
    LLM/vision-model/OCR call, no browser navigation, one image decode.
    Internal weighting only — never surfaced to users, see the module
    docstring for the reasoning behind each bucket."""
    tokens = structural_tokens or []
    text = heading or ""
    visual_density_score, page_state_score = _image_scores(image_bytes)
    return (
        _DOM_WEIGHT * _dom_structure_score(tokens, page_settled=page_settled)
        + _VISUAL_WEIGHT * visual_density_score
        + _TEXT_WEIGHT * _text_evidence_score(tokens, text)
        + _PAGE_STATE_WEIGHT * page_state_score
    )
