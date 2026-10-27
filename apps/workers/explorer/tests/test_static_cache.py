"""Shared app files (browser.cacheable): only unchanging files — scripts,
styles, fonts, images — are served from the shared cache. Pages and data
calls always go to the app, so every window still sees the app's real state."""

from explorer_worker.browser import cacheable


def test_only_unchanging_app_files_are_shared_between_windows() -> None:
    assert cacheable("GET", "script", 200, {"cache-control": "max-age=3600"})
    assert cacheable("GET", "stylesheet", 200, {})
    assert not cacheable("GET", "document", 200, {})  # the page itself
    assert not cacheable("GET", "xhr", 200, {})  # the app's data
    assert not cacheable("POST", "script", 200, {})
    assert not cacheable("GET", "script", 404, {})
    assert not cacheable("GET", "image", 200, {"cache-control": "no-store"})
