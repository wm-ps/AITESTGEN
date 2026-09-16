"""_url_template: hash-routed SPA pages must not collapse into one (regression)."""

from discovery_worker.model_builder import _url_template


def test_distinct_hash_routes_stay_distinct():
    assert _url_template("https://app.example.com/#/Dashboard") != _url_template(
        "https://app.example.com/#/SalesPipeline"
    )


def test_hash_route_with_query_state_ignores_state():
    assert _url_template(
        "https://app.example.com/?products_formWidget=0%3A+'undefined'#/SalesPipeline"
    ) == _url_template("https://app.example.com/#/SalesPipeline")
    assert _url_template(
        "https://app.example.com/#/MyTeam&wm_state=('ws'~('RepsList1'~('selectedItem')))"
    ) == _url_template("https://app.example.com/#/MyTeam")


def test_path_routed_app_unaffected():
    assert _url_template("https://app.example.com/customers/123") == _url_template(
        "https://app.example.com/customers/456"
    )
    assert _url_template("https://app.example.com/customers/123") != _url_template(
        "https://app.example.com/orders/123"
    )
