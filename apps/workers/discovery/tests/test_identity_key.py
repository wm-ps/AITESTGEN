"""`compute_identity_key` determinism (Story 2.6, AD-13).

Pure-function test, no DB/AI needed — the identity_key must depend only on
the canonical Application Model signature (Page/Component/ApiEndpoint), never
on anything an AI might name differently between runs (the function doesn't
even take a name as input, so this is structural, not just tested-for).
"""

import uuid

from discovery_worker.identity_key import compute_identity_key
from domain import ApiEndpoint, Component, Page


def _page(url: str) -> Page:
    return Page(application_id=uuid.uuid4(), discovery_run_id=uuid.uuid4(), url=url)


def _api_endpoint(method: str, path: str) -> ApiEndpoint:
    return ApiEndpoint(
        application_id=uuid.uuid4(),
        discovery_run_id=uuid.uuid4(),
        page_id=uuid.uuid4(),
        method=method,
        path=path,
    )


def _component(page_id, name: str) -> Component:
    return Component(
        application_id=uuid.uuid4(), page_id=page_id, name=name, type="button", action="click"
    )


def test_identity_key_stable_regardless_of_input_order() -> None:
    page_a = _page("https://app.example.com/cart")
    page_b = _page("https://app.example.com/checkout")

    key_forward = compute_identity_key([page_a, page_b], [], [])
    key_reversed = compute_identity_key([page_b, page_a], [], [])

    assert key_forward == key_reversed


def test_identity_key_differs_for_different_signatures() -> None:
    page_a = _page("https://app.example.com/cart")
    page_b = _page("https://app.example.com/checkout")
    page_c = _page("https://app.example.com/about")

    assert compute_identity_key([page_a, page_b], [], []) != compute_identity_key(
        [page_a, page_c], [], []
    )


def test_identity_key_is_deterministic_across_calls() -> None:
    page_a = _page("https://app.example.com/cart")
    endpoint = _api_endpoint("POST", "/api/checkout")

    assert compute_identity_key([page_a], [], [endpoint]) == compute_identity_key(
        [page_a], [], [endpoint]
    )


def test_identity_key_includes_component_signature() -> None:
    page_a = _page("https://app.example.com/cart")
    component = _component(page_a.id, "Checkout")

    with_component = compute_identity_key([page_a], [component], [])
    without_component = compute_identity_key([page_a], [], [])

    assert with_component != without_component
