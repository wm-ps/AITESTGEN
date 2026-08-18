"""Test Suite Export — assembly/sanitizer unit tests + download endpoint (Story 4.3).

Unit tests below are pure — no DB, no Vault, no Temporal — covering the
assembly module's own guarantees (AC 3, 7, 8, 9, 11-13) directly. The
endpoint test class at the bottom follows `test_test_suite_generation.py`'s
skip-cleanly convention (requires Postgres + Vault + Temporal reachable) for
AC 1, 4-6, 10.
"""

import io
import uuid
import zipfile

import pytest
from api.test_suite_export import (
    LoginPageEvidence,
    TestSuiteExportError,
    assemble_test_suite_project,
    dedupe_slugs,
    find_login_page_evidence,
    sanitize_slug,
)
from domain import Application, Journey, TestAsset, TestSuite


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


class TestSanitizeSlug:
    def test_lowercases_and_collapses_non_alphanumeric(self) -> None:
        assert sanitize_slug("Claim Search!", fallback="x") == "claim-search"

    def test_empty_name_falls_back(self) -> None:
        assert sanitize_slug("!!!", fallback="journey") == "journey"

    def test_reserved_windows_device_name_falls_back(self) -> None:
        assert sanitize_slug("CON", fallback="journey") == "journey"
        assert sanitize_slug("com1", fallback="journey") == "journey"

    def test_path_traversal_characters_are_stripped(self) -> None:
        assert sanitize_slug("../../etc/passwd", fallback="x") == "etc-passwd"
        assert "/" not in sanitize_slug("a/b\\c", fallback="x")
        assert ".." not in sanitize_slug("../x", fallback="x")


class TestDedupeSlugs:
    def test_two_distinct_keys_sharing_a_base_slug_are_disambiguated(self) -> None:
        result = dedupe_slugs([("key-a", "checkout"), ("key-b", "checkout")])
        assert result["key-a"] == "checkout"
        assert result["key-b"] != "checkout"
        assert result["key-b"].startswith("checkout-")

    def test_same_key_twice_is_idempotent(self) -> None:
        result = dedupe_slugs([("key-a", "checkout"), ("key-a", "checkout")])
        assert result["key-a"] == "checkout"


class TestAssembleTestSuiteProject:
    def _basic_zip(
        self, auth_method: str = "standard_login", login_evidence=None
    ) -> zipfile.ZipFile:
        application = _application(auth_method=auth_method)
        journey = _journey("Checkout")
        test_suite = _test_suite(journey)
        asset = _test_asset(
            test_suite,
            "import { test, expect } from '@playwright/test'\n\ntest('x', async () => {})\n",
        )
        data = assemble_test_suite_project(
            application,
            [test_suite],
            {journey.id: journey},
            {test_suite.id: [asset]},
            {asset.id: "Guest checkout"},
            login_evidence,
        )
        return zipfile.ZipFile(io.BytesIO(data))

    def test_one_folder_per_suite_one_file_per_asset(self) -> None:
        zf = self._basic_zip()
        names = zf.namelist()
        assert "tests/checkout/guest-checkout.spec.ts" in names
        assert "package.json" in names
        assert "playwright.config.ts" in names
        assert "README.md" in names
        assert "tests/auth.setup.ts" in names
        assert "fixtures/.gitkeep" in names
        assert "utils/.gitkeep" in names

    def test_baseurl_injected_into_config(self) -> None:
        zf = self._basic_zip()
        config = zf.read("playwright.config.ts").decode()
        assert "https://acme.example.com" in config
        # No login evidence passed -> nothing to authenticate -> one plain
        # project, no auth/public split to maintain.
        assert "projects" not in config

    def test_baseurl_injected_into_config_with_login_evidence(self) -> None:
        evidence = LoginPageEvidence(
            url="https://acme.example.com/login",
            username_locator='page.locator(\'[name="email"]\')',
            password_locator='page.locator(\'[name="password"]\')',
        )
        zf = self._basic_zip(login_evidence=evidence)
        config = zf.read("playwright.config.ts").decode()
        assert "https://acme.example.com" in config
        assert "storageState" in config
        assert "dependencies: ['setup']" in config
        # Project split is tag-driven, not a manual chromium/signed-in split
        # ("public" matches every non-@auth spec via grepInvert, not a
        # literal "@public" tag string).
        assert "@auth" in config
        assert "grepInvert" in config
        assert "'public'" in config

    def test_empty_current_suite_still_gets_a_folder(self) -> None:
        application = _application()
        journey = _journey("Empty Journey")
        test_suite = _test_suite(journey)
        data = assemble_test_suite_project(
            application, [test_suite], {journey.id: journey}, {}, {}, None
        )
        zf = zipfile.ZipFile(io.BytesIO(data))
        assert "tests/empty-journey/.gitkeep" in zf.namelist()

    def test_collision_between_two_journeys_does_not_overwrite(self) -> None:
        application = _application()
        journey_a = _journey("Claim Search!")
        journey_b = _journey("Claim Search?")
        suite_a = _test_suite(journey_a)
        suite_b = _test_suite(journey_b)
        asset_a = _test_asset(suite_a, "// a\n")
        asset_b = _test_asset(suite_b, "// b\n")
        data = assemble_test_suite_project(
            application,
            [suite_a, suite_b],
            {journey_a.id: journey_a, journey_b.id: journey_b},
            {suite_a.id: [asset_a], suite_b.id: [asset_b]},
            {asset_a.id: "t", asset_b.id: "t"},
            None,
        )
        zf = zipfile.ZipFile(io.BytesIO(data))
        suite_folders = {
            n.split("/")[1]
            for n in zf.namelist()
            if n.startswith("tests/") and n.count("/") >= 2
        }
        assert len(suite_folders) == 2

    def test_deterministic_across_two_calls(self) -> None:
        application = _application()
        journey = _journey("Checkout")
        test_suite = _test_suite(journey)
        asset = _test_asset(test_suite, "// code\n")
        args = (
            application,
            [test_suite],
            {journey.id: journey},
            {test_suite.id: [asset]},
            {asset.id: "Guest checkout"},
            None,
        )
        first = assemble_test_suite_project(*args)
        second = assemble_test_suite_project(*args)
        assert first == second

    def test_standard_login_uses_shared_auth_helper_and_config_registry(self) -> None:
        evidence = LoginPageEvidence(
            url="https://acme.example.com/login",
            username_locator='page.locator(\'[name="email"]\')',
            password_locator='page.locator(\'[name="password"]\')',
        )
        zf = self._basic_zip(auth_method="standard_login", login_evidence=evidence)
        setup_script = zf.read("tests/auth.setup.ts").decode()
        auth_helper = zf.read("support/auth.ts").decode()
        config_script = zf.read("support/config.ts").decode()

        # auth.setup.ts and every generated spec share one login
        # implementation (support/auth.ts) instead of each writing its own.
        assert "fillCredentials" in setup_script
        assert "https://acme.example.com/login" in setup_script
        assert "AITESTGEN_LOGIN_USERNAME" in config_script
        assert "AITESTGEN_LOGIN_PASSWORD" in config_script
        assert '[name="email"]' in auth_helper
        assert '[name="password"]' in auth_helper
        # No literal credential value, and no Vault/SecretsClient call, ever.
        combined = setup_script + auth_helper + config_script
        assert "SecretsClient" not in combined
        assert "resolve(" not in combined

    def test_standard_login_setup_verifies_login_actually_succeeded(self) -> None:
        """`[FIXED]` `auth.setup.ts` used to write `storageState` unconditionally
        right after calling `fillCredentials` — a wrong/missing credential (e.g.
        the placeholder default in support/config.ts) submits without throwing,
        silently producing a storageState that was never actually authenticated.
        Every downstream `@auth` test then failed for an unrelated, harder-to-
        diagnose reason instead of one clear failure at setup time."""
        zf = self._basic_zip(auth_method="standard_login")
        setup_script = zf.read("tests/auth.setup.ts").decode()

        # fillCredentials() completing without an exception must not be
        # trusted on its own — there must be a real post-login check before
        # storageState is saved, and it must throw (fail the setup project,
        # which every `@auth` test depends on) when that check fails.
        assert "fillCredentials(page)" in setup_script
        assert "storageState" in setup_script
        fill_index = setup_script.index("fillCredentials(page)")
        storage_index = setup_script.index("storageState")
        assert fill_index < storage_index, "must verify login before saving storageState"
        verification_section = setup_script[fill_index:storage_index]
        assert "throw new Error" in verification_section
        assert 'input[type="password"]' in verification_section

    def test_standard_login_falls_back_to_generic_selectors_without_evidence(self) -> None:
        zf = self._basic_zip(auth_method="standard_login", login_evidence=None)
        auth_helper = zf.read("support/auth.ts").decode()
        assert 'input[type="password"]' in auth_helper
        assert 'input[type="email"]' in auth_helper

    def test_sso_session_reuse_setup_never_logs_in(self) -> None:
        zf = self._basic_zip(auth_method="sso_session_reuse")
        setup_script = zf.read("tests/auth.setup.ts").decode()
        assert "AITESTGEN_STORAGE_STATE" in setup_script
        assert "fill(" not in setup_script
        assert "SecretsClient" not in setup_script

    def test_no_credential_or_selector_content_is_ai_generated(self) -> None:
        # The generated code is entirely template-authored (this module),
        # never round-tripped through an AI provider — nothing to assert
        # beyond confirming no ai_provider import/reference exists anywhere
        # in the assembled files.
        zf = self._basic_zip()
        for name in zf.namelist():
            if name.endswith((".ts", ".json", ".md")):
                assert "ai_provider" not in zf.read(name).decode()


class TestFindLoginPageEvidenceIsDbOnly:
    def test_requires_a_session_argument(self) -> None:
        # Smoke-test the signature only (no DB) — the real query is covered
        # by the endpoint's DB-backed test below.
        import inspect

        params = list(inspect.signature(find_login_page_evidence).parameters)
        assert params == ["session", "application"]


class TestTestSuiteExportErrorFailsClosed:
    def test_raises_rather_than_returning_partial_bytes(self) -> None:
        application = _application()
        journey = _journey("Checkout")
        test_suite = _test_suite(journey)
        asset = _test_asset(test_suite, "// code\n")
        # A TestSuite in `assets_by_suite` that the caller forgot to include
        # in `test_suites` triggers the count-mismatch guard.
        with pytest.raises(TestSuiteExportError):
            assemble_test_suite_project(
                application,
                [],  # no suites passed, but assets_by_suite still has one
                {journey.id: journey},
                {test_suite.id: [asset]},
                {asset.id: "t"},
                None,
            )


# --- Download endpoint (AC 1, 4-6, 9, 10) ---------------------------------
#
# Same skip-cleanly convention as `test_test_suite_generation.py` (requires
# Postgres + Vault + Temporal reachable — `POST /applications` starts a real
# discovery workflow even though this endpoint itself never dispatches one).

import asyncio  # noqa: E402

import hvac  # noqa: E402
from api.db import engine, init_db  # noqa: E402
from api.main import app  # noqa: E402
from api.scripts.seed_dev_data import seed  # noqa: E402
from api.temporal_client import get_temporal_client  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from hvac.exceptions import VaultError  # noqa: E402
from secrets_client.vault_client import VAULT_ADDR, VAULT_TOKEN  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlmodel import Session, select  # noqa: E402


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


def _vault_available() -> bool:
    try:
        return hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN).sys.is_initialized()
    except (VaultError, OSError):
        return False


def _temporal_available() -> bool:
    async def _check() -> bool:
        try:
            await get_temporal_client()
            return True
        except Exception:
            return False

    return asyncio.run(_check())


_db_deps_reachable = _db_available() and _vault_available() and _temporal_available()


def _signed_in_client(org_name: str) -> TestClient:
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=org_name, name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client


def _create_application(client: TestClient, name: str, auth_method: str = "standard_login") -> dict:
    payload = {
        "name": name,
        "url": "https://staging.example.com",
        "environment": "staging",
        "auth_method": auth_method,
    }
    if auth_method == "standard_login":
        payload["username"] = "qa-test-account"
        payload["password"] = "irrelevant"
    else:
        payload["session_state"] = '{"cookies": []}'
    response = client.post("/applications", json=payload)
    assert response.status_code == 201
    return response.json()


def _add_candidate_journey_with_suite(application: dict, journey_name: str, code: str) -> None:
    with Session(engine) as session:
        from domain import DiscoveryRun, Scenario

        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        journey = Journey(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            name=journey_name,
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()
        scenario = Scenario(
            journey_id=journey.id,
            type="happy",
            name="Guest checkout",
            steps=["Add item to cart"],
            expected_result="Order confirmed",
            test_data=[],
            generation_run_id=journey.attempt,
        )
        session.add(scenario)
        session.flush()
        test_suite = TestSuite(
            journey_id=journey.id,
            name=f"{journey.name} Test Suite",
            generation_run_id=journey.attempt,
        )
        session.add(test_suite)
        session.flush()
        session.add(TestAsset(scenario_id=scenario.id, test_suite_id=test_suite.id, code=code))
        session.commit()


@pytest.mark.skipif(
    not _db_deps_reachable,
    reason="requires PostgreSQL + Vault + Temporal reachable — start docker compose",
)
class TestDownloadTestSuiteProjectEndpoint:
    def test_download_returns_a_valid_zip_with_correct_headers(self) -> None:
        init_db()
        client = _signed_in_client("Org Suite Download")
        application = _create_application(client, "Download App")
        _add_candidate_journey_with_suite(
            application,
            "Checkout",
            "import { test, expect } from '@playwright/test'\n\ntest('x', async () => {})\n",
        )

        response = client.get(f"/applications/{application['id']}/test-suites/download")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert 'filename="download-app-tests.zip"' in response.headers["content-disposition"]

        zf = zipfile.ZipFile(io.BytesIO(response.content))
        names = zf.namelist()
        assert "package.json" in names
        assert "playwright.config.ts" in names
        assert any(n.startswith("tests/checkout/") and n.endswith(".spec.ts") for n in names)
        assert "https://staging.example.com" in zf.read("playwright.config.ts").decode()

    def test_download_is_organization_scoped(self) -> None:
        init_db()
        client_a = _signed_in_client("Org Suite Download A")
        client_b = _signed_in_client("Org Suite Download B")
        application = _create_application(client_a, "Org A Download App")
        _add_candidate_journey_with_suite(application, "Checkout", "// code\n")

        response = client_b.get(f"/applications/{application['id']}/test-suites/download")
        assert response.status_code == 404

    def test_download_with_no_current_suites_returns_404(self) -> None:
        init_db()
        client = _signed_in_client("Org Suite Download Empty")
        application = _create_application(client, "Empty Download App")

        response = client.get(f"/applications/{application['id']}/test-suites/download")
        assert response.status_code == 404

    def test_downloading_twice_is_byte_identical(self) -> None:
        init_db()
        client = _signed_in_client("Org Suite Download Determinism")
        application = _create_application(client, "Determinism App")
        _add_candidate_journey_with_suite(application, "Checkout", "// code\n")

        first = client.get(f"/applications/{application['id']}/test-suites/download")
        second = client.get(f"/applications/{application['id']}/test-suites/download")
        assert first.content == second.content

    def test_sso_session_reuse_application_downloads_without_login_setup(self) -> None:
        init_db()
        client = _signed_in_client("Org Suite Download SSO")
        application = _create_application(
            client, "SSO Download App", auth_method="sso_session_reuse"
        )
        _add_candidate_journey_with_suite(application, "Dashboard", "// code\n")

        response = client.get(f"/applications/{application['id']}/test-suites/download")
        assert response.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(response.content))
        setup_script = zf.read("tests/auth.setup.ts").decode()
        assert "AITESTGEN_STORAGE_STATE" in setup_script
        assert "fill(" not in setup_script
