"""Unit tests for the dir-writer output mode — the zip-writer path already
has full coverage in apps/api/tests/test_test_suite_export.py (unchanged
after the extraction). These tests cover what's new here: that
`assemble_test_suite_project_to_dir` produces the exact same file set/content
as `assemble_test_suite_project`'s zip, proving the "executed project ==
downloadable project" guarantee this package exists for.
"""

import json
import uuid
import zipfile
from io import BytesIO

from domain import Application, Journey, TestAsset, TestSuite
from test_suite_assembler import assemble_test_suite_project, assemble_test_suite_project_to_dir
from test_suite_assembler.assembler import (
    _build_interactions_helper_script,
    _build_package_json,
    _build_playwright_config,
    _playwright_locator_call,
)


def _application(**overrides) -> Application:
    defaults = dict(
        organization_id=uuid.uuid4(),
        name="Acme App",
        url="https://acme.example.com",
        environment="staging",
        secret_ref="applications/org/secret",
        auth_method="standard_login",
    )
    defaults.update(overrides)
    return Application(**defaults)


def _journey(name: str) -> Journey:
    return Journey(
        application_id=uuid.uuid4(),
        discovery_run_id=uuid.uuid4(),
        name=name,
        identity_key=str(uuid.uuid4()),
    )


def _test_suite(journey: Journey) -> TestSuite:
    return TestSuite(journey_id=journey.id, name=f"{journey.name} Test Suite", generation_run_id=1)


def _test_asset(test_suite: TestSuite, code: str) -> TestAsset:
    return TestAsset(scenario_id=uuid.uuid4(), test_suite_id=test_suite.id, code=code)


def _project_args():
    application = _application()
    journey = _journey("Checkout Flow")
    suite = _test_suite(journey)
    asset = _test_asset(suite, "// spec code\n")
    return dict(
        application=application,
        test_suites=[suite],
        journeys_by_id={journey.id: journey},
        assets_by_suite={suite.id: [asset]},
        scenario_name_by_asset_id={asset.id: "Completes checkout"},
        login_evidence=None,
    )


def test_dir_output_matches_zip_output(tmp_path) -> None:
    args = _project_args()

    zip_bytes = assemble_test_suite_project(**args)
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        zip_files = {name: zf.read(name).decode("utf-8") for name in zf.namelist()}

    dest_dir = tmp_path / "project"
    assemble_test_suite_project_to_dir(dest_dir, **args)
    dir_files = {
        str(p.relative_to(dest_dir)).replace("\\", "/"): p.read_text(encoding="utf-8")
        for p in dest_dir.rglob("*")
        if p.is_file()
    }

    assert dir_files == zip_files


def test_dir_output_writes_test_case_code(tmp_path) -> None:
    args = _project_args()
    dest_dir = tmp_path / "project"

    assemble_test_suite_project_to_dir(dest_dir, **args)

    spec_files = list(dest_dir.glob("tests/*/completes-checkout.spec.ts"))
    assert len(spec_files) == 1
    assert spec_files[0].read_text(encoding="utf-8") == "// spec code\n"


def test_ensure_visible_surfaces_strict_mode_violation_instead_of_masking_it() -> None:
    # `[FIXED]` regression: a bare `catch {}` used to discard whatever
    # Playwright actually threw and always report a generic "not visible"
    # message — live-diagnosed a repeatedly-failing generated test and found
    # the real error was a strict-mode violation (the locator matched an
    # unrelated element elsewhere on the page in addition to the intended
    # one), not a visibility problem. Waiting/scrolling can never fix that,
    # so it must be re-thrown immediately, with Playwright's own message.
    script = _build_interactions_helper_script()

    assert "strict mode violation" in script
    assert "throw err" in script
    # Both attempts (the initial wait, and the post-scroll retry) must check
    # for it — a violation on the second attempt must not fall through to
    # the generic message either.
    assert script.count("strict mode violation") == 2


def test_playwright_locator_call_scopes_selector_locators_to_first_match() -> None:
    # `[FIXED]` regression: a custom element that mirrors an attribute (e.g.
    # `name`) onto an inner native input makes any selector built from that
    # attribute match two elements — Playwright's strict mode then fails the
    # `.fill()` outright instead of picking one. `getByLabel` locates by
    # visible text, not a shared attribute, so it isn't exposed to that.
    assert _playwright_locator_call("css", '[name="j_username"]') == (
        "page.locator('[name=\"j_username\"]').first()"
    )
    assert _playwright_locator_call("label", "Username") == "page.getByLabel('Username')"


def test_package_json_adds_allure_dev_dependencies() -> None:
    dev_deps = json.loads(_build_package_json())["devDependencies"]

    assert "@playwright/test" in dev_deps
    assert "allure" in dev_deps
    assert "allure-playwright" in dev_deps


def test_playwright_config_switches_to_per_attempt_allure_results_with_and_without_login() -> None:
    """The execution worker sets AITESTGEN_ALLURE_RESULTS_DIR and leaves
    `--reporter` off its command line (a CLI reporter drops these options),
    so this branch must keep `json` as the stdout reporter. Unset, an
    exported suite gets the usual list output plus allure-results/."""
    for has_login in (False, True):
        config = _build_playwright_config("https://acme.example.com", has_login=has_login)
        assert (
            "  reporter: process.env.AITESTGEN_ALLURE_RESULTS_DIR\n"
            "    ? [['json'], ['allure-playwright', { resultsDir: process.env.AITESTGEN_ALLURE_RESULTS_DIR }]]\n"
            "    : [['list'], ['allure-playwright']],\n"
        ) in config


def test_project_writes_allurerc_with_escaped_app_name(tmp_path) -> None:
    args = _project_args()
    args["application"] = _application(name='Acme "Bank" App')
    dest_dir = tmp_path / "project"

    assemble_test_suite_project_to_dir(dest_dir, **args)

    allurerc = (dest_dir / "allurerc.mjs").read_text(encoding="utf-8")
    assert (
        "name: process.env.AITESTGEN_REPORT_TITLE || " + json.dumps('Acme "Bank" App tests') + ","
    ) in allurerc
    assert "output: './allure-report'," in allurerc
    # Absolute path: Allure resolves `import` from its own install dir.
    assert (
        "import: fileURLToPath(new URL('./vantage-report/plugin.mjs', import.meta.url)),"
    ) in allurerc
    assert "awesome" not in allurerc


def test_project_ships_the_vantage_report_plugin(tmp_path) -> None:
    dest_dir = tmp_path / "project"

    assemble_test_suite_project_to_dir(dest_dir, **_project_args())

    report_dir = dest_dir / "vantage-report"
    assert sorted(p.name for p in report_dir.iterdir()) == [
        "logo.datauri.txt",
        "model.mjs",
        "plugin.mjs",
        "template.html",
    ]
    assert (report_dir / "logo.datauri.txt").read_text(encoding="utf-8").startswith(
        "data:image/png;base64,iVBORw0KGgo"
    )
    template = (report_dir / "template.html").read_text(encoding="utf-8")
    for placeholder in ("__VANTAGE_PAGE_TITLE__", "__VANTAGE_LOGO__", "__VANTAGE_DATA__"):
        assert placeholder in template
