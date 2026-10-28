from explorer_worker.breadth import coverage_summary, routes_in_code


def test_routes_in_code_finds_page_addresses_not_assets():
    code = 'a="#/AdminSettings";route={path:"/claims/archive"};x="/static/app.js";y="/api/users"'
    routes = routes_in_code(code)
    assert "AdminSettings" in routes
    assert "/claims/archive" in routes
    assert not any("static" in r or "/api/" in r for r in routes)


def test_routes_in_code_skips_back_end_service_paths():
    code = 'a={path:"UsersListView"};b="/pricepoint-management/v4";c="/rule-management-api/v4"'
    assert routes_in_code(code) == {"UsersListView"}


def test_a_page_button_is_only_done_on_its_own_page():
    from explorer_worker.understand import done_key

    campaigns = done_key("Create", "https://a.com/#/CampaignsListView", nav=False)
    assert campaigns != done_key("Create", "https://a.com/#/PricePointsListView", nav=False)
    assert done_key("Users", "https://a.com/#/Home", nav=True) == done_key(
        "Users", "https://a.com/#/Taxes", nav=True
    )


def test_coverage_summary_counts_only_the_apps_own_code():
    scripts = [
        {
            "url": "https://app.com/main.js",
            "functions": [
                {"functionName": "approveClaim", "ranges": [{"count": 0}]},
                {"functionName": "render", "ranges": [{"count": 3}]},
                {"functionName": "", "ranges": [{"count": 1}]},
            ],
        },
        {
            "url": "https://cdn.other.com/lib.js",
            "functions": [{"functionName": "x", "ranges": [{"count": 0}]}],
        },
    ]
    report = coverage_summary(scripts, "https://app.com")
    assert report["functions"] == 2 and report["ran"] == 1 and report["percent"] == 50
    assert report["never_ran"] == ["approveClaim"]


def test_coverage_summary_skips_third_party_bundles_and_library_names():
    scripts = [
        {
            "url": "https://app.com/vendor.js",
            "functions": [{"functionName": "approveAll", "ranges": [{"count": 0}]}],
        },
        {
            "url": "https://app.com/main.js",
            "functions": [
                {"functionName": "defineCustomElementOrderEditor", "ranges": [{"count": 0}]},
                {"functionName": "Lr.reject", "ranges": [{"count": 0}]},
                {"functionName": "submitClaim", "ranges": [{"count": 0}]},
            ],
        },
    ]
    assert coverage_summary(scripts, "https://app.com")["never_ran"] == ["submitClaim"]
