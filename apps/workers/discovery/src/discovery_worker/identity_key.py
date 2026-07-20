"""Deterministic Journey `identity_key` computation (Story 2.6, AD-13).

Computed from the Journey's underlying **canonical** Application Model
signature (Page URLs, Component identities, ApiEndpoint signatures) — never
from its AI-generated `name`, which can vary slightly run to run. Story
3.5's re-discovery dedup later compares against this exact key, so its
construction must be stable now.
"""

import hashlib
import json

from domain import ApiEndpoint, Component, Page


def compute_identity_key(
    pages: list[Page], components: list[Component], api_endpoints: list[ApiEndpoint]
) -> str:
    signature = {
        "pages": sorted(page.url for page in pages),
        "components": sorted(f"{c.page_id}:{c.name}:{c.type}" for c in components),
        "api_endpoints": sorted(f"{e.method}:{e.path}" for e in api_endpoints),
    }
    combined = json.dumps(signature, sort_keys=True)
    return hashlib.sha256(combined.encode()).hexdigest()
