from datetime import datetime

from explorer_worker.sense import (
    START_FRESH,
    keeps_state,
    resolve_relative,
    resumes_saved_progress,
    date_variants,
    health_label,
    health_score,
    is_explorable_link,
    is_risky_label,
    looks_final,
    may_commit,
    needs_human_ok,
    screen_signature,
    url_pattern,
)


def test_url_pattern_collapses_ids_and_query_values():
    assert url_pattern("https://a.com/customers/17") == url_pattern("https://a.com/customers/9031")
    assert url_pattern("https://a.com/q/3f2b8c1e-1d2a-4b3c-9d8e-0a1b2c3d4e5f/edit").endswith(
        "/q/{id}/edit"
    )
    assert url_pattern("https://a.com/list?page=2&sort=x") == url_pattern(
        "https://a.com/list?sort=y&page=9"
    )
    assert url_pattern("https://a.com/#/policies/POL-1234") == url_pattern(
        "https://a.com/#/policies/POL-99887"
    )
    assert url_pattern("https://a.com/#/quotes") != url_pattern("https://a.com/#/claims")


def test_url_pattern_works_for_every_kind_of_router():
    # path routes (React Router / Next.js / Angular)
    assert url_pattern("https://a.com/orders/17/items") == url_pattern(
        "https://a.com/orders/88/items"
    )
    assert url_pattern("https://a.com/orders") != url_pattern("https://a.com/customers")
    # an in-page anchor is not a different screen; a hash route is
    assert url_pattern("https://a.com/settings#billing") == url_pattern("https://a.com/settings")
    assert url_pattern("https://a.com/app/#/claims") != url_pattern("https://a.com/app/")
    # hashbang and query values inside a hash route
    assert url_pattern("https://a.com/#!/claims") == url_pattern("https://a.com/#/claims/")
    assert url_pattern("https://a.com/#/claim?ref=A") == url_pattern("https://a.com/#/claim?ref=B")
    # the same page written differently
    same = {
        url_pattern(u)
        for u in (
            "https://a.com/app",
            "http://a.com/app/",
            "https://a.com:443/app/index.html",
            "https://A.com/app/#/",
            "https://a.com/app/#",
        )
    }
    assert len(same) == 1, same
    # generated ids, but not words
    assert url_pattern("https://a.com/c/FNOL-W84R-7NRY") == url_pattern(
        "https://a.com/c/FNOL-A12B-3CDE"
    )
    assert url_pattern("https://a.com/u/V1StGXR8_Z5jdHi6B") == url_pattern(
        "https://a.com/u/k9x2m7q4p1"
    )
    assert url_pattern("https://a.com/settings-v2") != url_pattern("https://a.com/settings-v3x")


def test_same_place_allows_redirects_deeper_but_not_elsewhere():
    from explorer_worker.sense import same_place

    assert same_place("https://a.com/orders/7/summary", "https://a.com/orders/7")
    assert same_place("https://a.com/#/claims", "https://a.com/#!/claims/")
    assert not same_place("https://a.com/login", "https://a.com/orders/7")
    assert not same_place("https://a.com/#/", "https://a.com/#/vehicles")


def test_explorable_link_rules():
    origin = "https://a.com"
    assert is_explorable_link("https://a.com/quotes", origin)
    assert not is_explorable_link("https://other.com/x", origin)
    assert not is_explorable_link("https://a.com/logout", origin)
    assert not is_explorable_link("https://a.com/x", origin, text="Sign out")
    assert not is_explorable_link("https://a.com/report.pdf", origin)
    assert not is_explorable_link("mailto:x@a.com", origin)


def test_risky_labels():
    assert is_risky_label("Delete customer")
    assert is_risky_label("Submit quote")
    assert is_risky_label("Log out")
    assert not is_risky_label("Quotes")
    assert not is_risky_label("View details")


def test_screen_signature_merges_by_meaning():
    assert screen_signature("Quotes", "list", None, "All quotes") == screen_signature(
        "Quote", "list", None, "Quote list"
    )
    assert screen_signature("Quote", "form", "create", "x") != screen_signature(
        "Quote", "form", "edit", "x"
    )
    assert screen_signature(None, "dashboard", None, "Home") == "home|dashboard|"
    # wizard steps on the same business thing stay distinct
    assert screen_signature("Claim", "wizard", "create", "Policy search") != screen_signature(
        "Claim", "wizard", "create", "Vehicle selection"
    )


def test_health_score_bands():
    assert health_score([], 10) == 100
    healthy = health_score([("low", 1)], 20)
    sick = health_score([("high", 3), ("high", 1), ("medium", 4), ("high", 2)], 6)
    assert health_label(healthy) == "Healthy"
    assert health_label(sick) == "Unhealthy"
    assert health_score([("high", 1000)], 10) >= health_score([("high", 1)] * 3, 10)
    assert health_score([("high", 1)], 0) == 0


def test_looks_final():
    assert looks_final("Submit claim")
    assert looks_final("Send")
    assert not looks_final("Skip - send photos later")
    assert not looks_final("Continue")


def test_commit_policy():
    assert may_commit("Save", non_production=True)
    assert may_commit("Submit claim", non_production=True)
    assert not may_commit("Save", non_production=False)
    assert not may_commit("Delete employee", non_production=True)
    assert not may_commit("Approve", non_production=True)
    assert needs_human_ok("Pay now")
    assert not needs_human_ok("Add candidate")


def test_date_variants():
    variants = date_variants("1985-04-12")
    assert variants[0] == "1985-04-12"
    assert "Apr 12, 1985" in variants
    assert "04/12/1985" in variants and "12/04/1985" in variants
    assert date_variants("next Tuesday") == ["next Tuesday"]


def test_resolve_relative_dates_are_worked_out_at_run_time() -> None:
    now = datetime(2026, 10, 16, 9, 30)
    assert resolve_relative("{{today+1d}}", now) == "2026-10-17"
    assert resolve_relative("{{ today - 30d }}", now) == "2026-09-16"
    assert resolve_relative("{{now+2h}}", now) == "2026-10-16 11:30"
    assert resolve_relative("{{today}}", now) == "2026-10-16"
    assert resolve_relative("POL-10001", now) == "POL-10001"


def test_keeps_state_spots_saved_drafts_and_carts() -> None:
    assert keeps_state(["Resume claim report A returning policyholder can continue"])
    assert keeps_state(["Shopping cart Review items"])
    assert not keeps_state(["Quote list Agents browse quotes", "Policy details"])


def test_start_fresh_and_resume_labels() -> None:
    assert START_FRESH.search("Start over instead")
    assert START_FRESH.search("Discard and start again")
    assert not START_FRESH.search("Continue")
    assert resumes_saved_progress([{"do": "click", "label": "Resume my report"}])
    from explorer_worker.sense import RESUME_LABEL

    assert RESUME_LABEL.search("Pick up where you left off")
    assert not RESUME_LABEL.search("Continue")
    assert not resumes_saved_progress([{"do": "click", "label": "Start over"}])


def test_going_in_circles():
    from explorer_worker.sense import going_in_circles

    wizard = ["Safety", "Policy", "Kind", "When", "Where", "What", "Vehicles", "Review"]
    assert going_in_circles(wizard) is None
    # One honest back-and-forth is fine.
    assert going_in_circles(["Status", "Photos", "Status", "Photos", "Done"]) is None
    assert "Photos → Status" in going_in_circles(
        ["Home", "Photos", "Status"] * 1 + ["Photos", "Status"] * 2
    )
    assert "stayed on Photos" in going_in_circles(["Home", "Photos", "Photos", "Photos"])
    assert "A → B → C" in going_in_circles(["A", "B", "C"] * 3)
    assert "came back to Hub" in going_in_circles(
        ["Hub", "A", "Hub", "B", "Hub", "C", "Hub", "D", "Hub"]
    )


def test_dismiss_like_matches_only_warning_answers() -> None:
    from explorer_worker.sense import DISMISS_LIKE

    assert DISMISS_LIKE.match("This is a separate event — continue")
    assert DISMISS_LIKE.match("Report it anyway")
    assert DISMISS_LIKE.match("Not now")
    assert not DISMISS_LIKE.match("Continue")
    assert not DISMISS_LIKE.match("Skip photos")


def test_url_pattern_keeps_view_switches_apart():
    # `?view=have` and `?view=owe` are two tabs of one page, not one id'd record
    assert url_pattern("https://a.com/Dashboard?view=have") != url_pattern(
        "https://a.com/Dashboard?view=owe"
    )
    assert url_pattern("https://a.com/x?tab=Cards") == url_pattern("https://a.com/x?tab=cards")
    # ids and free text under a view key still collapse
    assert url_pattern("https://a.com/x?type=17") == url_pattern("https://a.com/x?type=42")


def test_page_links_named_like_actions_are_followed():
    from explorer_worker.sense import is_risky_link

    assert not is_risky_link("PAYMENT & TRANSFER", "https://a.com/Transfer")
    assert not is_risky_link("Send Money", "https://a.com/Transfer")
    assert is_risky_link("Remove", "https://a.com/Cards/Remove/4")
    assert is_risky_link("Me", "https://a.com/Account/Logout")


def test_credential_changes_always_need_a_human():
    from explorer_worker.sense import may_commit

    assert needs_human_ok("Change password")
    assert needs_human_ok("Buy now") and needs_human_ok("Sell units")
    # a plain "Cancel" is harmless, unless it is how the task cancels something
    assert not needs_human_ok("Cancel", "Fill the transfer form")
    assert needs_human_ok("Cancel", "Cancel an insurance policy safely")
    # a plain Save is judged together with the task it finishes
    assert not may_commit("Save (Change the account password)", non_production=True)
    assert may_commit("Save (Add a beneficiary)", non_production=True)


def test_a_link_to_another_page_is_only_navigation():
    from explorer_worker.sense import page_link

    inventory = {
        "links": [
            {"text": "💰 Send Money", "href": "https://a.com/Transfer"},
            {"text": "💳 Pay Bills", "href": "https://a.com/Dashboard#"},
        ]
    }
    assert page_link(inventory, "Send Money") == "https://a.com/Transfer"
    assert page_link(inventory, "Pay Bills") is None  # `#` link: a real button press
    assert page_link(inventory, "Send transfer") is None


def test_a_cv_resume_is_not_saved_progress():
    assert not keeps_state(["Add candidate: upload the candidate's resume and contact details"])
    assert keeps_state(["Resume claim report: pick up where you left off"])
