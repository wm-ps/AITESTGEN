from explorer_worker.testkit import playwright_code, without_decisive_step


def test_without_decisive_step_drops_last_real_action():
    script = [
        {"do": "goto", "url": "https://a.com/#/form"},
        {"do": "fill", "field": "Email", "value": "x"},
        {"do": "click", "label": "Continue"},
    ]
    assert without_decisive_step(script) == script[:2]
    assert without_decisive_step([{"do": "goto", "url": "u"}]) == [{"do": "goto", "url": "u"}]


def test_playwright_code_is_readable_and_marks_known_bugs():
    script = [
        {"do": "goto", "url": "https://a.com/#/form"},
        {"do": "fill", "field": "Email", "value": "not-an-email"},
        {"do": "click", "label": "Continue"},
    ]
    check = {"kind": "text_visible", "value": "Enter a valid email"}
    code = playwright_code(
        "Email needs @", ["Open form", "Type bad email"], script, check, "Error shown"
    )
    assert 'test("Email needs @"' in code
    # Same house style as Vantage's generated tests: shared helper + timeouts.
    assert "import { ensureVisible } from '../../support/interactions';" in code
    assert "const TEST_TIMEOUT_MS = 180000;" in code
    assert (
        'await fillField(page, await ensureVisible(page.getByLabel("Email").or(page.locator("xpath=//*[normalize-space(text())=\\"Email\\"]/following::*[self::input or self::select or self::textarea][1]")).filter({ visible: true }).first()), "not-an-email")'
        in code
    )
    assert "Enter a valid email" in code
    bug = playwright_code("Age 15", [], script, check, "Rejected", known_bug_observed="Accepted")
    assert "test.fixme(true, " in bug and "KNOWN BUG" in bug and bug.count("\ntest(") == 1


def test_proof_must_be_caused_by_the_test():
    from explorer_worker.tests_stage import proof_was_there_before

    start = "Add Employee\nFirst Name\n* Required"
    assert proof_was_there_before({"kind": "text_visible", "value": "* Required"}, start, "u")
    assert not proof_was_there_before(
        {"kind": "text_visible", "value": "Required field"}, start, "u"
    )
    assert proof_was_there_before(
        {"kind": "url_contains", "value": "pim"}, start, "https://x/pim/list"
    )
    assert not proof_was_there_before(
        {"kind": "url_contains", "value": "addEmployee"}, start, "https://x/pim/list"
    )


def test_sample_files_are_real_files_of_their_kind():
    from explorer_worker.samples import KINDS, sample_file

    heads = {"image": b"\xff\xd8\xff", "png": b"\x89PNG", "pdf": b"%PDF"}
    for kind in KINDS:
        data = sample_file(kind).read_bytes()
        assert data, kind
        if kind in heads:
            assert data.startswith(heads[kind]), kind
    assert sample_file("something-else").name == "claim-photo.jpg"


def test_upload_step_is_replayable_code_with_the_file_inside():
    from explorer_worker.testkit import describe, playwright_code

    step = {"do": "upload", "field": "Upload photos", "kind": "image"}
    code = playwright_code("Attach a photo", [], [step], None, "The photo is listed")
    assert "setInputFiles(" in code and "claim-photo.jpg" in code and "image/jpeg" in code
    assert describe(step) == "attaching a image file" or describe(step).startswith("attaching")


class _FakeEyes:
    """Just enough of Eyes for replay(): `screen` is what is clickable now."""

    def __init__(self, screen: set[str], continue_label: str | None = None) -> None:
        self.page = object()
        self.screen = screen
        self.continue_label = continue_label

    def mark_calls(self) -> None:
        pass
        self.clicked: list[str] = []

    async def start_fresh_on_resume_prompts(self) -> None: ...

    # A "resume your saved progress?" prompt the previous attempt left behind.
    resume_prompt = False

    async def start_fresh_if_asked(self) -> None:
        if self.resume_prompt:
            self.resume_prompt = False
            self.clicked.append("Start over instead")

    async def fingerprint(self) -> str:
        return "x"

    async def wait_for_change(self, before: str, timeout_ms: int = 0) -> bool:
        return True

    async def click_text(self, label: str, role: str | None = None, spec=None) -> bool:
        if label in self.screen and not self.resume_prompt:
            self.clicked.append(label)
            return True
        return False

    async def present(self, step: dict) -> bool:
        return step.get("label") in self.screen

    async def press_continue_like(self) -> str | None:
        if self.continue_label:
            label, self.continue_label = self.continue_label, None
            self.screen = self.screen | {"Next"}
            return label
        return None


def test_replay_answers_a_resume_prompt_left_by_the_previous_attempt():
    import asyncio

    from explorer_worker.testkit import replay

    # Recorded with no saved draft; this replay meets FNOL's "Welcome back".
    script = [{"do": "click", "label": "Auto collision"}, {"do": "click", "label": "Next"}]
    eyes = _FakeEyes({"Auto collision", "Next"})
    eyes.resume_prompt = True
    assert asyncio.run(replay(eyes, script))
    assert eyes.clicked == ["Start over instead", "Auto collision", "Next"]


def test_replay_marks_a_skipped_screen_optional():
    import asyncio

    from explorer_worker.testkit import replay

    script = [{"do": "click", "label": "Kind of claim"}, {"do": "click", "label": "Next"}]
    eyes = _FakeEyes({"Next"})  # the app skipped "Kind of claim" this time
    assert asyncio.run(replay(eyes, script))
    assert script[0]["optional"] is True and eyes.clicked == ["Next"]


def test_replay_presses_past_an_unexpected_screen_and_records_it():
    import asyncio

    from explorer_worker.testkit import playwright_code, replay

    script = [{"do": "click", "label": "Next"}]
    eyes = _FakeEyes(set(), continue_label="This is a separate event — continue")
    assert asyncio.run(replay(eyes, script))
    assert script[0] == {
        "do": "click",
        "label": "This is a separate event — continue",
        "optional": True,
    }
    code = playwright_code("t", [], script, None, "e")
    assert "waitFor({ state: 'visible', timeout: 4000 })" in code


def test_caps_scale_with_app_size():
    from explorer_worker.missions import mission_cap
    from explorer_worker.tests_stage import test_cap

    assert mission_cap(20) == 10 and mission_cap(3) == 6 and mission_cap(200) == 15
    assert test_cap(20) == 150 and test_cap(1) == 15 and test_cap(5) == 75 and test_cap(500) == 150


def test_cap_keeps_every_kind_of_check():
    from explorer_worker.tests_stage import balanced

    planned = (
        [{"kind": "validation"}] * 8 + [{"kind": "navigation"}] * 3 + [{"kind": "error_state"}]
    )
    kinds = [t["kind"] for t in balanced(planned, 6)]
    assert set(kinds) == {"validation", "navigation", "error_state"} and len(kinds) == 6


def test_cap_reaches_every_screen():
    from explorer_worker.tests_stage import balanced

    planned = [{"kind": "validation", "start_screen": "Transfer"}] * 9 + [
        {"kind": "navigation", "start_screen": "Loans"},
        {"kind": "data_load", "start_screen": "Cards"},
    ]
    screens = [t["start_screen"] for t in balanced(planned, 4)]
    assert set(screens) == {"Transfer", "Loans", "Cards"}


def test_warning_dismissal_click_is_optional_in_exported_test() -> None:
    script = [
        {"do": "goto", "url": "https://app.test/"},
        {"do": "click", "label": "This is a separate event — continue"},
        {"do": "click", "label": "Continue"},
    ]
    code = playwright_code(
        "Dup", [], script, {"kind": "text_visible", "value": "Done"}, "Done", None
    )
    dismiss = next(line for line in code.splitlines() if "separate event" in line)
    plain = next(line for line in code.splitlines() if 'name: "Continue"' in line)
    assert "waitFor({ state: 'visible', timeout: 4000 })" in dismiss
    assert "ensureVisible" in plain


def test_choose_skips_an_option_that_is_already_selected() -> None:
    script = [
        {"do": "goto", "url": "https://app.test/"},
        {"do": "choose", "field": "", "option": "Auto collision"},
    ]
    code = playwright_code(
        "Pick", [], script, {"kind": "text_visible", "value": "Done"}, "Done", None
    )
    line = next(
        line for line in code.splitlines() if "ensureVisible" in line and "Auto collision" in line
    )
    # A plain dropdown offering it is used first; otherwise found first (that can answer a resume prompt and restore a draft), then checked, then clicked.
    assert line.index("ensureVisible") < line.index("isChecked()") < line.index("target.click")


def test_continue_unticks_boxes_the_test_did_not_choose() -> None:
    from explorer_worker.testkit import chosen_on_screen

    script = [
        {"do": "goto", "url": "https://app.test/"},
        {"do": "choose", "field": "", "option": "Rear"},
        {"do": "click", "label": "Continue"},
        {"do": "click", "label": "Continue"},
    ]
    assert chosen_on_screen(script, 2) == ["Rear"]
    assert chosen_on_screen(script, 3) == []
    code = playwright_code(
        "Parts", [], script, {"kind": "text_visible", "value": "Done"}, "Done", None
    )
    assert "const UNTICK_UNCHOSEN = " in code
    # Called as an expression: Playwright's TS client does not call a function passed as a string.
    assert "page.evaluate('(' + UNTICK_UNCHOSEN + ')(' + " in code
    assert "Rear" in code.split("const target")[1]
    assert code.count("await page.evaluate('(' + UNTICK_UNCHOSEN") == 2


def test_refresh_test_proves_the_step_that_reached_the_screen():
    from explorer_worker.testkit import without_decisive_step

    script = [
        {"do": "goto", "url": "https://a.com/Dashboard"},
        {"do": "click", "label": "Transfer"},
        {"do": "reload"},
    ]
    assert without_decisive_step(script) == [script[0], script[2]]


def test_sign_in_test_never_writes_the_secret():
    from explorer_worker.browser import Eyes

    script = [
        {"do": "goto", "url": "https://a.com/Account/Login"},
        {"do": "fill", "field": "Username", "value": "{{username}}"},
        {"do": "fill", "field": "Password", "value": "{{password}}"},
        {"do": "click", "label": "Sign in"},
    ]
    code = playwright_code("Signing in works", [], script, None, "e", tag="@public")
    assert "CREDENTIALS.username" in code and "CREDENTIALS.password" in code
    assert "import { CREDENTIALS } from '../../support/config';" in code
    eyes = Eyes("https://a.com/")
    eyes.remember_login("https://a.com/Account/Login", "test.user5", "S3cret!")
    assert eyes._login_value("{{password}}") == "S3cret!"
    assert eyes._login_value("Alice") == "Alice"


def test_unlabelled_dropdown_is_selected_not_clicked() -> None:
    script = [
        {"do": "goto", "url": "https://app.test/"},
        {"do": "choose", "field": "Category", "option": "Card"},
    ]
    code = playwright_code("Pick", [], script, None, "e")
    assert 'selectOption({ label: "Card" }' in code


def test_page_quality_test_runs_the_same_measurement():
    from explorer_worker import quality

    code = quality.playwright_code("Loans fits a phone", "fits_phone", "https://a.com/Loans", "@auth", None)
    assert "setViewportSize" in code and "scrollWidth" in code and "{ tag: \"@auth\" }" in code
    bug = quality.playwright_code("t", "loads_cleanly", "https://a.com/Loans", None, "500 https://a.com/api")
    assert "test.fixme(true" in bug and "expect(problems).toEqual([])" in bug
    assert quality.planned_checks({"fields": []}) == ["loads_cleanly", "no_broken_images"]
