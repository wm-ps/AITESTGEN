"""Building a project for a non-default environment: the default app's base
URL inside each test's code is rewritten to the environment's, and the config,
sign-in script and README follow the effective application. The default
environment (`retarget_from=None`) is byte-for-byte what it always was.
"""

import io
import uuid
import zipfile

from domain import Application, ApplicationEnvironment, Journey, TestAsset, TestSuite, effective_application
from test_suite_assembler import assemble_test_suite_project, retarget_code

DEFAULT_URL = "https://prod.example.com/"
ENV_URL = "https://uat.example.com/"

SPEC = (
    "import { test, expect } from '@playwright/test';\n"
    "const SIGN_IN_URL = 'https://prod.example.com/signin?next=%2Fhome';\n"
    "test('checkout', async ({ page }) => {\n"
    "  await page.goto('https://prod.example.com/cart');\n"
    "  await page.goto('/orders');\n"
    "  await expect(page).toHaveURL('https://prod.example.com/done');\n"
    "  await page.goto('https://prod.example.com.evil.io/x');\n"
    "});\n"
)


def _application() -> Application:
    return Application(
        organization_id=uuid.uuid4(),
        name="Acme App",
        url=DEFAULT_URL,
        login_url="https://prod.example.com/signin",
        environment="production",
        secret_ref="applications/org/default",
        auth_method="standard_login",
    )


def _environment(application: Application) -> ApplicationEnvironment:
    return ApplicationEnvironment(
        application_id=application.id,
        name="UAT",
        url=ENV_URL,
        login_url="https://uat.example.com/signin",
        auth_method="standard_login",
        secret_ref="applications/org/uat",
    )


def _zip_for(application: Application, retarget_from: str | None) -> dict[str, str]:
    journey = Journey(
        application_id=uuid.uuid4(),
        discovery_run_id=uuid.uuid4(),
        name="Checkout",
        identity_key=str(uuid.uuid4()),
    )
    suite = TestSuite(journey_id=journey.id, name="Checkout Test Suite", generation_run_id=1)
    asset = TestAsset(scenario_id=uuid.uuid4(), test_suite_id=suite.id, code=SPEC)
    data = assemble_test_suite_project(
        application,
        [suite],
        {journey.id: journey},
        {suite.id: [asset]},
        {asset.id: "Completes checkout"},
        None,
        retarget_from,
    )
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {name: zf.read(name).decode("utf-8") for name in zf.namelist()}


def test_retarget_code_swaps_only_whole_base_urls() -> None:
    out = retarget_code(SPEC, DEFAULT_URL, ENV_URL)
    assert "https://uat.example.com/cart" in out
    assert "toHaveURL('https://uat.example.com/done')" in out
    assert "page.goto('/orders')" in out  # relative navigation untouched
    # A longer host that merely starts with the base URL is left alone.
    assert "https://prod.example.com.evil.io/x" in out
    assert "https://prod.example.com/cart" not in out


def test_retarget_code_respects_a_path_prefix_and_is_a_no_op_for_the_same_url() -> None:
    code = "goto('https://a.io/app/home'); goto('https://a.io/application');"
    assert (
        retarget_code(code, "https://a.io/app/", "https://u.io/")
        == "goto('https://u.io/home'); goto('https://a.io/application');"
    )
    assert retarget_code(SPEC, DEFAULT_URL, DEFAULT_URL) == SPEC


def test_the_default_environment_project_is_unchanged() -> None:
    files = _zip_for(_application(), None)
    spec = next(content for name, content in files.items() if name.endswith(".spec.ts"))
    assert spec == SPEC
    assert "Environment" not in files["README.md"]


def test_an_environment_project_targets_the_environment_everywhere() -> None:
    default = _application()
    effective = effective_application(default, _environment(default))
    files = _zip_for(effective, default.url)

    assert "https://uat.example.com/" in files["playwright.config.ts"]
    assert "prod.example.com" not in files["playwright.config.ts"]
    spec = next(content for name, content in files.items() if name.endswith(".spec.ts"))
    assert "https://uat.example.com/cart" in spec
    assert "**UAT** environment" in files["README.md"]
    # No credential or secret reference is ever written into the project.
    assert all("applications/org" not in content for content in files.values())


def test_the_effective_application_is_a_detached_copy() -> None:
    default = _application()
    environment = _environment(default)
    effective = effective_application(default, environment)

    assert (effective.url, effective.login_url, effective.environment, effective.secret_ref) == (
        ENV_URL,
        "https://uat.example.com/signin",
        "UAT",
        "applications/org/uat",
    )
    assert effective.id == default.id
    assert default.url == DEFAULT_URL and default.environment == "production"
    assert effective_application(default, None) is default
