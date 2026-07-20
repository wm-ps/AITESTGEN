"""Navigation-graph clustering + bin-packing for InferenceActivity (Story 2.6).

Sibling to `model_builder.py`/`identity_key.py` — heavy logic lives in its
own module, `activities.py` just calls into it.

Replaces "send every canonical Page in one flat LLM call" with: group pages
by how they're actually navigated between (using `PageTransition` rows
already captured by Story 2.2/2.5 — free, no LLM involved), then bin-pack
those connected clusters into batches sized under a page-count budget, so no
single `HostedAIProvider.infer_journeys` call ever has to reason over more
than one coherent, connected subset of the Application.

This does NOT reduce the total number of tokens describing an Application
somewhere across all calls — that's fixed by how much the app has to say. It
bounds how much any single call has to reason over at once, which is what
actually controls per-call accuracy ("lost in the middle"), latency (batches
run independently, so they can be dispatched concurrently), and fault
isolation (one bad batch doesn't cost the whole run). Batch count is driven
by total page count, never by a user-facing setting — see Story 2.6's Dev
Notes for why that's deliberate, not an oversight.
"""

import logging
import os
import uuid
from urllib.parse import urlparse

from domain import Page, PageTransition

logger = logging.getLogger(__name__)

MAX_PAGES_PER_INFERENCE_CALL = int(os.environ.get("MAX_PAGES_PER_INFERENCE_CALL", "150"))


def _find(parent: dict[uuid.UUID, uuid.UUID], x: uuid.UUID) -> uuid.UUID:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _union(parent: dict[uuid.UUID, uuid.UUID], a: uuid.UUID, b: uuid.UUID) -> None:
    root_a, root_b = _find(parent, a), _find(parent, b)
    if root_a != root_b:
        parent[root_a] = root_b


def _connected_components(
    pages: list[Page], transitions: list[PageTransition]
) -> list[list[Page]]:
    """Groups pages by `PageTransition` connectivity via union-find — pages
    with no path between them are very unlikely to be the same Journey, and
    this costs zero LLM tokens to determine."""
    parent = {page.id: page.id for page in pages}
    for transition in transitions:
        if transition.from_page_id in parent and transition.to_page_id in parent:
            _union(parent, transition.from_page_id, transition.to_page_id)

    groups: dict[uuid.UUID, list[Page]] = {}
    for page in pages:
        groups.setdefault(_find(parent, page.id), []).append(page)
    return list(groups.values())


def _split_oversized(pages: list[Page], max_pages: int) -> list[list[Page]]:
    """Fallback for a single connected component larger than the per-call
    budget on its own — a genuine, acknowledged gap in this pass (same
    framing as the crawler's own traversal algorithm), expected to be rare:
    most real applications resolve into multiple naturally-separate
    clusters (login/checkout/admin/reporting rarely all interlink)."""
    logger.warning(
        "journey_clustering: a connected component of %d pages exceeds the %d-page "
        "per-call budget — splitting by URL path prefix as a fallback",
        len(pages),
        max_pages,
    )
    by_prefix: dict[str, list[Page]] = {}
    for page in pages:
        segments = urlparse(page.url).path.strip("/").split("/")
        prefix = segments[0] if segments and segments[0] else "(root)"
        by_prefix.setdefault(prefix, []).append(page)

    chunks: list[list[Page]] = []
    for group in by_prefix.values():
        for i in range(0, len(group), max_pages):
            chunks.append(group[i : i + max_pages])
    return chunks


def _bin_pack(components: list[list[Page]], max_pages: int) -> list[list[Page]]:
    """Bin-packs connected components into batches **by page count**, not by
    raw component count — a lumpy mix of one 60-page cluster and nine 5-page
    clusters should not become 10 equal-count-but-wildly-uneven-size calls.
    First-fit-decreasing: largest pieces placed first, each into the first
    batch it still fits in, else a new batch."""
    pieces: list[list[Page]] = []
    for component in components:
        if len(component) > max_pages:
            pieces.extend(_split_oversized(component, max_pages))
        else:
            pieces.append(component)

    pieces.sort(key=len, reverse=True)

    batches: list[list[Page]] = []
    batch_sizes: list[int] = []
    for piece in pieces:
        for i, size in enumerate(batch_sizes):
            if size + len(piece) <= max_pages:
                batches[i].extend(piece)
                batch_sizes[i] += len(piece)
                break
        else:
            batches.append(list(piece))
            batch_sizes.append(len(piece))
    return batches


def cluster_and_batch(
    pages: list[Page], transitions: list[PageTransition], max_pages_per_call: int | None = None
) -> list[list[Page]]:
    """Entry point: canonical pages + their transitions in -> right-sized,
    navigation-connected batches out, each ready for one
    `HostedAIProvider.infer_journeys` call."""
    if not pages:
        return []
    max_pages = (
        max_pages_per_call if max_pages_per_call is not None else MAX_PAGES_PER_INFERENCE_CALL
    )
    components = _connected_components(pages, transitions)
    return _bin_pack(components, max_pages)
