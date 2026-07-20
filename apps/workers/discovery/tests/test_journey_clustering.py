"""journey_clustering (Story 2.6) — pure-function tests, no DB/network."""

import uuid

from discovery_worker.journey_clustering import cluster_and_batch
from domain import Page, PageTransition


def _page(url: str) -> Page:
    return Page(application_id=uuid.uuid4(), discovery_run_id=uuid.uuid4(), url=url, title=url)


def _transition(from_page: Page, to_page: Page) -> PageTransition:
    return PageTransition(
        application_id=from_page.application_id,
        discovery_run_id=from_page.discovery_run_id,
        from_page_id=from_page.id,
        to_page_id=to_page.id,
    )


def test_connected_pages_end_up_in_the_same_batch() -> None:
    cart = _page("/cart")
    checkout = _page("/checkout")
    confirmation = _page("/checkout/confirmation")
    transitions = [_transition(cart, checkout), _transition(checkout, confirmation)]

    batches = cluster_and_batch([cart, checkout, confirmation], transitions)

    assert len(batches) == 1
    assert {p.id for p in batches[0]} == {cart.id, checkout.id, confirmation.id}


def test_disconnected_clusters_split_into_separate_batches_when_over_budget() -> None:
    cart = _page("/cart")
    checkout = _page("/checkout")
    confirmation = _page("/checkout/confirmation")
    help_home, help_faq = _page("/help"), _page("/help/faq")
    transitions = [
        _transition(cart, checkout),
        _transition(checkout, confirmation),
        _transition(help_home, help_faq),
    ]

    # Artificially tiny budget (3) forces the two disconnected clusters
    # (3 pages + 2 pages) into separate batches, mirroring the story's
    # worked example.
    batches = cluster_and_batch(
        [cart, checkout, confirmation, help_home, help_faq], transitions, max_pages_per_call=3
    )

    assert len(batches) == 2
    batch_ids = [{p.id for p in batch} for batch in batches]
    assert {cart.id, checkout.id, confirmation.id} in batch_ids
    assert {help_home.id, help_faq.id} in batch_ids


def test_small_disconnected_clusters_bin_pack_into_one_batch_under_budget() -> None:
    # Two disconnected clusters that both fit comfortably under a real-sized
    # budget should share a single call, not each get their own.
    cart, checkout = _page("/cart"), _page("/checkout")
    help_home, help_faq = _page("/help"), _page("/help/faq")
    transitions = [_transition(cart, checkout), _transition(help_home, help_faq)]

    batches = cluster_and_batch(
        [cart, checkout, help_home, help_faq], transitions, max_pages_per_call=150
    )

    assert len(batches) == 1
    assert len(batches[0]) == 4


def test_oversized_single_cluster_falls_back_to_url_prefix_split() -> None:
    admin_pages = [_page(f"/admin/users/{i}") for i in range(5)]
    transitions = [_transition(admin_pages[i], admin_pages[i + 1]) for i in range(4)]

    batches = cluster_and_batch(admin_pages, transitions, max_pages_per_call=2)

    # No batch may exceed the budget, and every page must still appear
    # exactly once across all batches.
    assert all(len(batch) <= 2 for batch in batches)
    all_ids = [p.id for batch in batches for p in batch]
    assert sorted(all_ids) == sorted(p.id for p in admin_pages)


def test_empty_input_returns_no_batches() -> None:
    assert cluster_and_batch([], []) == []
