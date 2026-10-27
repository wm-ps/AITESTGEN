"""The proof check (testkit.holds) matches the exported test: one visible
element showing the text — never several labels joined into one string —
waited for as the exported expect() waits."""

import asyncio

from explorer_worker.testkit import holds

ELEMENTS = ["Mobile number", "Email", "Continue", "Save and exit"]  # one per element


class _Hit:
    def __init__(self, ok: bool) -> None:
        self.ok = ok
        self.first = self

    def filter(self, **_: object) -> _Hit:
        return self

    async def wait_for(self, state: str, timeout: int) -> None:
        if not self.ok:  # Playwright raises when it never becomes visible
            raise TimeoutError(f"not visible within {timeout} ms")


class _Page:
    url = "https://app.example/#/ContactDetails"

    def get_by_text(self, value: str) -> _Hit:
        # Playwright: some single element's text contains `value` (case-insensitive).
        return _Hit(any(value.lower() in e.lower() for e in ELEMENTS))


class _Eyes:
    page = _Page()


def test_a_single_element_proves_joined_labels_do_not() -> None:
    eyes = _Eyes()
    assert asyncio.run(holds(eyes, {"kind": "text_visible", "value": "Mobile number"}))
    assert not asyncio.run(
        holds(eyes, {"kind": "text_visible", "value": "Mobile number Email Continue Save and exit"})
    )


def test_an_absent_proof_is_checked_briefly_a_present_one_is_waited_for() -> None:
    from explorer_worker.testkit import ABSENT_WAIT_MS, PROOF_WAIT_MS

    waited: list[int] = []

    class _Missing(_Hit):
        async def wait_for(self, state: str, timeout: int) -> None:
            waited.append(timeout)
            raise TimeoutError

    class _Page2(_Page):
        def get_by_text(self, value: str) -> _Hit:
            return _Missing(False)

    class _Eyes2:
        page = _Page2()

    proof = {"kind": "text_visible", "value": "Enter correct mobile number"}
    assert not asyncio.run(holds(_Eyes2(), proof, ABSENT_WAIT_MS))  # broken-on-purpose run
    assert not asyncio.run(holds(_Eyes2(), proof))  # a replay, as the exported test waits
    assert waited == [ABSENT_WAIT_MS, PROOF_WAIT_MS] and ABSENT_WAIT_MS < PROOF_WAIT_MS
