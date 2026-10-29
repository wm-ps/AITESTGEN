"""Findings that are the same problem must collapse into one row."""

from explorer_worker.journal import _failure_key
from explorer_worker.mind import _is_sign_in_return


def test_same_server_error_with_other_query_values_is_one_problem() -> None:
    a = "GET https://x.test/category-management/v4/category/search?q=abc&page=1 -> 503"
    b = "GET https://x.test/category-management/v4/category/search?q=zz&page=7 -> 503"
    assert _failure_key(a) == _failure_key(b)
    other = "GET https://x.test/category-management/v4/category -> 503"
    assert _failure_key(a) != _failure_key(other)


def test_console_error_ids_and_line_numbers_ignored() -> None:
    assert _failure_key("TypeError at main.js:120:33 (id 991)") == _failure_key(
        "TypeError at main.js:4:8 (id 12)"
    )


def test_sign_in_hand_back_is_not_a_blank_page_bug() -> None:
    assert _is_sign_in_return("https://x.test/app?code=abc&iss=y&session_state=z&state=q")
    assert _is_sign_in_return("https://x.test/app/#/?state=q&code=abc")
    assert not _is_sign_in_return("https://x.test/app/#/Home")
    assert not _is_sign_in_return("https://x.test/app?code=promo")
