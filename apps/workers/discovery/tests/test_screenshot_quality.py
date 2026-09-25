"""Screenshot Content Score (`screenshot_quality.score_screenshot`) — pure
unit tests, no Playwright/DB/network needed. Fixtures are small synthetic
PNGs built with Pillow (already a project dependency for this feature)
rather than checked-in image assets, per the "small deterministic fixtures,
not large image assets" guidance.
"""

import io
import random
import socket

from discovery_worker.screenshot_quality import score_screenshot
from PIL import Image

_SIZE = (800, 600)


def _png(fill: str = "white", *, noisy: bool = False) -> bytes:
    img = Image.new("RGB", _SIZE, fill)
    if noisy:
        rng = random.Random(42)
        pixels = img.load()
        for x in range(0, _SIZE[0], 3):
            for y in range(0, _SIZE[1], 3):
                pixels[x, y] = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


_BLANK_PNG = _png("white")
_DENSE_PNG = _png("white", noisy=True)

# A real, rendered application page: settled, a substantial DOM with the
# kind of tags/roles a table/nav/form page actually has, a real heading, and
# visually dense content.
_REAL_PAGE_TOKENS = [
    "html", "body", "nav", "h1", "table", "thead", "tr", "th", "th",
    "tbody", "tr", "td", "td", "tr", "td", "td", "button[button]",
    "a[link]", "a[link]", "form", "input", "label", "ul", "li", "li",
]


def test_completely_blank_screenshot_scores_low() -> None:
    score = score_screenshot(
        _BLANK_PNG, structural_tokens=["html", "body"], heading="", page_settled=False
    )
    assert score < 0.2


def test_mostly_blank_screenshot_scores_low() -> None:
    # A near-blank page still settled and with a couple of chrome-only
    # elements (a shell that never got real content) — not zero DOM, still
    # low.
    score = score_screenshot(
        _BLANK_PNG,
        structural_tokens=["html", "body", "nav"],
        heading="",
        page_settled=True,
    )
    assert score < 0.4


def test_loading_skeleton_screenshot_scores_lower_than_a_real_page() -> None:
    loading_score = score_screenshot(
        _BLANK_PNG,
        structural_tokens=["html", "body", "div[status]"],
        heading="",
        page_settled=False,
    )
    real_score = score_screenshot(
        _DENSE_PNG, structural_tokens=_REAL_PAGE_TOKENS, heading="Users", page_settled=True
    )
    assert loading_score < real_score


def test_screenshot_with_meaningful_content_scores_high() -> None:
    score = score_screenshot(
        _DENSE_PNG, structural_tokens=_REAL_PAGE_TOKENS, heading="Users", page_settled=True
    )
    assert score > 0.6


def test_selects_the_highest_scoring_screenshot_among_several() -> None:
    """Category 5: given several candidate screenshots, the highest-scoring
    one wins — the same comparison `apps/api/src/api/main.py`'s
    `_best_screenshot_page` performs, exercised here at the scoring level."""
    candidates = {
        "blank": score_screenshot(
            _BLANK_PNG, structural_tokens=["html", "body"], heading="", page_settled=False
        ),
        "loading": score_screenshot(
            _BLANK_PNG,
            structural_tokens=["html", "body", "div[status]"],
            heading="",
            page_settled=False,
        ),
        "partial": score_screenshot(
            _BLANK_PNG,
            structural_tokens=["html", "body", "nav", "h1"],
            heading="Users",
            page_settled=True,
        ),
        "real": score_screenshot(
            _DENSE_PNG, structural_tokens=_REAL_PAGE_TOKENS, heading="Users", page_settled=True
        ),
        "mostly_empty": score_screenshot(
            _BLANK_PNG,
            structural_tokens=["html", "body", "nav", "h1", "p"],
            heading="Users",
            page_settled=True,
        ),
    }

    assert max(candidates, key=lambda k: candidates[k]) == "real"


def test_legitimate_empty_state_page_is_not_treated_as_blank() -> None:
    """Category 6: "Users / No users found." — settled, a real (if small)
    DOM with a heading and empty-state chrome, just a visually sparse
    screenshot. Must score well above a genuinely blank/loading capture,
    even though its image is just as visually empty."""
    empty_state_score = score_screenshot(
        _BLANK_PNG,
        structural_tokens=["html", "body", "nav", "h1", "p", "div[status]"] * 3,
        heading="Users",
        page_settled=True,
    )
    blank_score = score_screenshot(
        _BLANK_PNG, structural_tokens=["html", "body"], heading="", page_settled=False
    )
    assert empty_state_score > blank_score * 2


def test_handles_missing_structural_tokens_and_heading_without_raising() -> None:
    score = score_screenshot(_BLANK_PNG, structural_tokens=None, heading=None, page_settled=False)
    assert 0.0 <= score <= 1.0


def test_handles_corrupt_image_bytes_without_raising() -> None:
    score = score_screenshot(
        b"not a real png", structural_tokens=_REAL_PAGE_TOKENS, heading="Users", page_settled=True
    )
    assert 0.0 <= score <= 1.0


def test_score_is_always_within_bounds() -> None:
    score = score_screenshot(
        _DENSE_PNG, structural_tokens=_REAL_PAGE_TOKENS * 10, heading="Users", page_settled=True
    )
    assert 0.0 <= score <= 1.0


def test_no_network_call_is_made_while_scoring() -> None:
    """Category 8: deterministic and local — blocking every socket
    connection attempt for the duration of the call proves no LLM/vision-
    model/API call (or any other network I/O) happens."""

    def _blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("score_screenshot attempted a network connection")

    original_connect = socket.socket.connect
    socket.socket.connect = _blocked  # type: ignore[method-assign]
    try:
        score = score_screenshot(
            _DENSE_PNG, structural_tokens=_REAL_PAGE_TOKENS, heading="Users", page_settled=True
        )
    finally:
        socket.socket.connect = original_connect  # type: ignore[method-assign]
    assert 0.0 <= score <= 1.0
