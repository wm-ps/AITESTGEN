"""A screen seen again is recognised by what stays the same (address, title,
fields, columns, buttons), not only by h1-h3 headings, which many apps lack."""

from explorer_worker.browser import Visit
from explorer_worker.mind import _revisit_key
from explorer_worker.sense import url_pattern

HOME = url_pattern("https://a.com/#/Dashboard")


def _visit(url: str, **inv: object) -> Visit:
    return Visit(url, 200, 0, {"title": "", "headings": [], **inv}, b"", [])


def test_same_screen_with_other_records_gets_the_same_key() -> None:
    cols = [{"headers": ["NAME ▲", "STATUS"], "rows": [["Acme", "Open"]]}]
    other = [{"headers": ["NAME ▲", "STATUS"], "rows": [["Zeta", "Won"]]}]
    a = _visit(
        "https://a.com/#/Accounts", title="Accounts", tables=cols, buttons=["New", "Edit", "Edit"]
    )
    b = _visit("https://a.com/#/Accounts", title="Accounts", tables=other, buttons=["Edit", "New"])
    assert _revisit_key(a, HOME) is not None
    assert _revisit_key(a, HOME) == _revisit_key(b, HOME)


def test_a_different_step_at_the_same_address_is_a_different_key() -> None:
    one = _visit(
        "https://a.com/#/Claim", title="Claim", fields=[{"label": "Policy"}], buttons=["Next"]
    )
    two = _visit(
        "https://a.com/#/Claim", title="Claim", fields=[{"label": "Date of loss"}], buttons=["Next"]
    )
    assert _revisit_key(one, HOME) != _revisit_key(two, HOME)


def test_home_without_headings_is_keyed_by_its_shape() -> None:
    dash = _visit("https://a.com/#/Dashboard", title="Dashboard", buttons=["30 days"])
    assert _revisit_key(dash, HOME) is not None
    assert _revisit_key(_visit("https://a.com/#/Dashboard"), HOME) is None


def test_confirmation_screens_are_always_read() -> None:
    done = _visit("https://a.com/#/Done", title="Claim submitted", buttons=["Home"])
    assert _revisit_key(done, HOME) is None
