from types import SimpleNamespace

from explorer_worker.browser import Eyes
from explorer_worker.sense import refused_calls


def _response(status, kind="fetch", method="POST", url="https://app.test/api/leads?x=1"):
    return SimpleNamespace(
        status=status, url=url, request=SimpleNamespace(method=method, resource_type=kind)
    )


def test_a_refused_data_call_is_a_finding_but_a_refused_image_is_not():
    eyes = Eyes("https://app.test/")
    for response in (_response(422), _response(404, kind="image"), _response(200), _response(503)):
        eyes._on_response(response)
    assert [(s.kind, s.title) for s in eyes._pending] == [
        ("api_error", "Data call refused (422)"),
        ("server_error", "Server error 503"),
    ]
    assert len(eyes.calls) == 3  # every data call is still kept for proofs


def test_refused_calls_names_only_the_failed_ones():
    calls = [
        ("GET", "https://app.test/api/leads", 200),
        ("POST", "https://app.test/api/leads?draft=1", 422),
    ]
    assert refused_calls(calls) == "POST //app.test/api/leads?draft -> 422"
    assert refused_calls(calls[:1]) == ""
