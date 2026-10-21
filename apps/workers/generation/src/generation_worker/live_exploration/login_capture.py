"""Login-form capture for an Application that skips Discovery.

`discovery_required=true` Applications get their login Page/Form/FormFields
(real selectors) from Discovery's `establish_session`, which the suite
assembler and `spec_linter` then read. A `discovery_required=false`
`standard_login` Application never runs Discovery, so nothing was ever
captured and the exported suite's `auth.setup.ts` had to guess its locators.

`establish_session` already has an optional capture hook; this module only
supplies the arguments for it (`login_capture_kwargs`) and writes what it
captured as the same plain Page/Form/FormField rows (`persist_login_capture`),
once, on the Application's first live-exploration login. Applications with
`discovery_required=true` never go through here.
"""

import logging
import uuid
from typing import Any

from discovery_worker.crawler import CapturedForm, CapturedPage
from domain import Application, DiscoveryRun, Form, FormField, Page
from sqlmodel import Session

from generation_worker import spec_linter
from generation_worker.db import engine

logger = logging.getLogger(__name__)


class _NoScreenshotStore:
    """`establish_session` only captures when given an object store, but the
    login screenshot isn't needed to ground locators.

    ponytail: stand-in that stores nothing (`Page.object_storage_key` stays
    null) instead of wiring S3 into the generation worker. Pass a real
    `ObjectStore` if the login page's screenshot is ever wanted."""

    def put(
        self, data: bytes, discovery_run_id: uuid.UUID, content_type: str = "image/png"
    ) -> None:
        return None


def needs_login_capture(application: Application) -> bool:
    """True only for a no-Discovery `standard_login` app with no login form
    captured yet — so the login is captured once, never on every exploration."""
    if application.discovery_required is not False or application.auth_method != "standard_login":
        return False
    with Session(engine) as session:
        return spec_linter._find_login_page_url(session, application.id) is None


def login_capture_kwargs(captured: list[CapturedPage | CapturedForm]) -> dict[str, Any]:
    """Extra `establish_session` arguments that make it append the login page
    and form it saw to `captured`. The run id is only a label for the object
    store key; the `DiscoveryRun` row is created later by `persist_login_capture`."""
    return {
        "object_store": _NoScreenshotStore(),
        "discovery_run_id": uuid.uuid4(),
        "on_capture": captured.append,
    }


def persist_login_capture(
    application_id: uuid.UUID, captured: list[CapturedPage | CapturedForm]
) -> None:
    page = next((c for c in captured if isinstance(c, CapturedPage)), None)
    form = next((c for c in captured if isinstance(c, CapturedForm)), None)
    if page is None or form is None:
        return

    with Session(engine) as session:
        # A concurrent exploration may have captured it since `needs_login_capture`.
        if spec_linter._find_login_page_url(session, application_id) is not None:
            return

        discovery_run = DiscoveryRun(
            application_id=application_id, status="complete", source="live_exploration"
        )
        session.add(discovery_run)
        session.commit()
        session.refresh(discovery_run)

        page_row = Page(
            application_id=application_id,
            discovery_run_id=discovery_run.id,
            url=page.url,
            title=page.title,
            object_storage_key=page.object_storage_key,
        )
        session.add(page_row)
        session.commit()
        session.refresh(page_row)

        form_row = Form(
            application_id=application_id,
            discovery_run_id=discovery_run.id,
            page_id=page_row.id,
            action_url=form.action_url,
            method=form.method,
        )
        session.add(form_row)
        session.commit()
        session.refresh(form_row)

        for captured_field in form.fields:
            session.add(
                FormField(
                    form_id=form_row.id,
                    name=captured_field.name,
                    input_type=captured_field.input_type,
                    required=captured_field.required,
                    default_value=captured_field.default_value,
                    captured_selector=captured_field.captured_selector,
                    locator_candidates=captured_field.locator_candidates,
                )
            )
        session.commit()
    logger.info("login_capture: stored login page %s for application %s", page.url, application_id)
