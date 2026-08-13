"""Unit tests for the dir-writer output mode — the zip-writer path already
has full coverage in apps/api/tests/test_test_suite_export.py (unchanged
after the extraction). These tests cover what's new here: that
`assemble_test_suite_project_to_dir` produces the exact same file set/content
as `assemble_test_suite_project`'s zip, proving the "executed project ==
downloadable project" guarantee this package exists for.
"""

import uuid
import zipfile
from io import BytesIO

from domain import Application, Journey, TestAsset, TestSuite
from test_suite_assembler import assemble_test_suite_project, assemble_test_suite_project_to_dir


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
