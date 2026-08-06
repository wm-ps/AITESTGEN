"""DiscoveryActivity / ApplicationModelBuilderActivity / InferenceActivity —
the I/O boundary DiscoveryWorkflow dispatches to (AD-2).

Story 2.2 (reworked 2026-07-18): establish a session using the Application's
stored credentials (via `SecretsClient`), autonomously explore the entire
Application, and write each captured page/form/action/API call/transition
directly as a typed row (`Page`/`Form`/`FormField`/`ValidationRule`/`Action`/
`ApiEndpoint`/`PageTransition`) — there is no generic `Evidence` table.
Story 2.3 adds the `complete` transition; Story 2.4 adds the
`failed`/`session_expired` distinction (AD-11) and a catch-all for any other
crash. Story 2.5 adds `ApplicationModelBuilderActivity`: merges duplicate
typed captures into canonical rows and derives Component/ComponentLocator/
Assertion. Story 2.6 adds `InferenceActivity`: canonical Page rows ->
candidate Journey/Capability rows. `[CORRECTED 2026-07-21]` No longer starts
`GenerationWorkflow` — Story 4.1 moved that to an explicit "Continue to
Scenarios" trigger (its Task 5), not automatic per candidate here.
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field

from ai_provider.hosted import HostedAIProvider
from domain import (
    Action,
    ApiEndpoint,
    Application,
    Assertion,
    BlockedTask,
    Capability,
    Component,
    DiscoveryError,
    DiscoveryRun,
    DiscoverySettings,
    ExplorationStep,
    Form,
    FormField,
    Journey,
    JourneyStep,
    Page,
    PageTransition,
    SyntheticDataEntry,
    TestDataEntry,
    ValidationRule,
)
from object_store import ObjectStore
from playwright.async_api import async_playwright
from secrets_client.vault_client import SecretRef, VaultSecretsClient
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from temporalio import activity
from workflows import (
    ApplicationModelBuilderActivityInput,
    ApplicationModelBuilderActivityOutput,
    DiscoveryActivityInput,
    DiscoveryActivityOutput,
    InferenceActivityInput,
)

from discovery_worker import blocked_frontier
from discovery_worker.crawler import (
    CapturedAction,
    CapturedApiCall,
    CapturedForm,
    CapturedItem,
    CapturedPage,
    CapturedPageComplete,
    CapturedTransition,
    CrawlResult,
    run_discovery_crawl,
)
from discovery_worker.data_resolver import PoolEntry
from discovery_worker.db import engine
from discovery_worker.diagnostics import record_diagnostic
from discovery_worker.identity_key import compute_identity_key
from discovery_worker.journey_clustering import cluster_and_batch
from discovery_worker.model_builder import build_application_model
from discovery_worker.safety_engine import SafetyState
from discovery_worker.session import establish_session
from discovery_worker.state_identity import (
    CachedState,
    StateIdentityCache,
    compute_fingerprint,
    route_template,
)

logger = logging.getLogger(__name__)

# AC6: a per-run backstop, not a per-batch one — bounds a bad/hallucinating
# inference run's blast radius (number of Journey/JourneyStep rows written),
# independent of whether generation is triggered automatically or on request.
MAX_CANDIDATE_JOURNEYS_PER_RUN = int(os.environ.get("MAX_CANDIDATE_JOURNEYS_PER_RUN", "50"))


@dataclass
class _PageBuffer:
    """Story 2.10 Task 7: one page's captures, held until its
    `CapturedPageComplete` signal arrives."""

    page: CapturedPage | None = None
    forms: list[CapturedForm] = field(default_factory=list)
    actions: list[CapturedAction] = field(default_factory=list)
    api_calls: list[CapturedApiCall] = field(default_factory=list)


def _seed_state_identity_cache(
    session: Session, application_id: uuid.UUID, cache: StateIdentityCache
) -> None:
    """Story 2.10 Task 5/AC 7: seeds the in-process cache from canonical
    (`merged_into_id IS NULL`) `Page` rows for this Application, across
    every prior Discovery Run — Story 2.5's cross-run canonicalization is
    complementary, not superseded (Dev Notes)."""
    canonical_pages = list(
        session.exec(
            select(Page).where(
                Page.application_id == application_id,
                Page.merged_into_id.is_(None),  # type: ignore[union-attr]
            )
        ).all()
    )
    if not canonical_pages:
        return

    actions_by_page: dict[uuid.UUID, list[str]] = {}
    for action_row in session.exec(
        select(Action).where(Action.application_id == application_id)
    ).all():
        actions_by_page.setdefault(action_row.page_id, []).append(action_row.description)

    fields_by_page: dict[uuid.UUID, list[str]] = {}
    for form_row, field_row in session.exec(
        select(Form, FormField)
        .join(FormField, FormField.form_id == Form.id)  # type: ignore[arg-type]
        .where(Form.application_id == application_id)
    ).all():
        if field_row.name:
            fields_by_page.setdefault(form_row.page_id, []).append(field_row.name)

    cache.seed(
        [
            CachedState(
                page_id=page.id,
                url=page.url,
                route_template=route_template(page.url),
                fingerprint=compute_fingerprint(
                    page.heading,
                    actions_by_page.get(page.id, []),
                    fields_by_page.get(page.id, []),
                    page.structural_tokens or [],
                ),
            )
            for page in canonical_pages
        ]
    )


def _seed_resume_frontier(
    session: Session, application_id: uuid.UUID
) -> tuple[frozenset[str], list[tuple[str, str | None]]]:
    """Story 2.17 AC 2/3: canonical `Page` URLs already confirmed for this
    Application (from any prior Discovery Run) are skipped entirely on this
    crawl — not just deduplicated at persist time (Story 2.10 already does
    that), never re-visited or re-interacted with at all. The BFS instead
    starts from the frontier just past them: `PageTransition` edges leading
    OUT of a canonical page to a URL that isn't itself canonical yet. Falls
    back to `(frozenset(), [])` — today's exact behaviour, a plain crawl from
    `base_url` — for a brand-new Application or one with no such frontier
    (fully explored, or nothing confirmed yet)."""
    canonical_pages = list(
        session.exec(
            select(Page).where(
                Page.application_id == application_id,
                Page.merged_into_id.is_(None),  # type: ignore[union-attr]
            )
        ).all()
    )
    if not canonical_pages:
        return frozenset(), []
    canonical_urls = frozenset(page.url for page in canonical_pages)

    # Every Page row, not just canonical ones — a transition can reference a
    # since-superseded row, same resolution `InferenceActivity` already does.
    all_pages_by_id = {
        page.id: page
        for page in session.exec(
            select(Page).where(Page.application_id == application_id)
        ).all()
    }

    def _canonical_url(page_id: uuid.UUID) -> str | None:
        row = all_pages_by_id.get(page_id)
        if row is None:
            return None
        canonical_row = all_pages_by_id.get(row.merged_into_id or row.id)
        return canonical_row.url if canonical_row else None

    frontier: dict[str, str | None] = {}
    for transition in session.exec(
        select(PageTransition).where(PageTransition.application_id == application_id)
    ).all():
        from_url = _canonical_url(transition.from_page_id)
        to_url = _canonical_url(transition.to_page_id)
        if from_url in canonical_urls and to_url and to_url not in canonical_urls:
            frontier.setdefault(to_url, from_url)
    return canonical_urls, list(frontier.items())


def _seed_test_data_pool(session: Session, application_id: uuid.UUID) -> dict[str, PoolEntry]:
    """Story 2.20 Task 3: loads the Application's Test Data Pool into an
    in-process dict, the same "seeded once at Activity start" pattern as
    `_seed_state_identity_cache` above. Sensitive entries are resolved
    through the Vault-backed client at load time — the Data Resolver only
    ever sees plaintext in memory for the duration of this Activity, never a
    `SecretRef` it would have to know how to resolve itself."""
    entries = list(
        session.exec(
            select(TestDataEntry).where(TestDataEntry.application_id == application_id)
        ).all()
    )
    if not entries:
        return {}
    vault = VaultSecretsClient()
    pool: dict[str, PoolEntry] = {}
    for entry in entries:
        value = entry.value
        if entry.is_sensitive and entry.secret_ref:
            try:
                value = vault.resolve(SecretRef(path=entry.secret_ref)).decode()
            except Exception:
                logger.exception(
                    "_seed_test_data_pool: failed to resolve secret for %s — skipping entry",
                    entry.normalized_key,
                )
                continue
        if value is None:
            continue
        pool[entry.normalized_key] = PoolEntry(value=value, is_sensitive=entry.is_sensitive)
    return pool


def _record_exploration_path(
    session: Session,
    *,
    blocked_task: BlockedTask,
    current_page_id: uuid.UUID | None,
    blocking_action_description: str,
    blocking_input_values: dict,
    max_hops: int = 25,
) -> None:
    """Story 2.16 Task 2/4 (AC 1/2/5): a human-readable diagnostic record of
    how the crawler reached `blocked_task` — never a replay script (Dev
    Notes). Reconstructed retroactively by walking the already-durable
    `PageTransition` graph backward from the blocked page to its entry
    point, rather than a new per-click bookkeeping structure threaded
    through the whole crawl — every hop this walk finds was already
    committed in real time by `_persist_one`. `step_order` continues from
    this `BlockedTask`'s existing maximum (AC 5: a second block on the same
    `aggregation_key` extends the trail rather than colliding with it).

    Disclosed scope: only the terminal (blocking) step's `input_values` are
    populated — the resolved values used at each *preceding* hop aren't
    durably tracked anywhere else in the engine, and per-hop masking of
    values from a sensitive pool entry (the letter of Task 2's bullet)
    is therefore moot for this reconstruction; masking is applied to the
    terminal step alone, the only one that could ever carry a value."""
    if current_page_id is None:
        return
    hops: list[tuple[uuid.UUID, str, dict]] = []
    page_id: uuid.UUID | None = current_page_id
    action_description = blocking_action_description
    input_values = blocking_input_values
    seen: set[uuid.UUID] = set()
    while page_id is not None and page_id not in seen and len(hops) < max_hops:
        seen.add(page_id)
        hops.append((page_id, action_description, input_values))
        transition = session.exec(
            select(PageTransition)
            .where(PageTransition.to_page_id == page_id)
            .order_by(PageTransition.created_at.asc())  # type: ignore[arg-type]
        ).first()
        if transition is None:
            break
        triggering_action = (
            session.get(Action, transition.triggered_by_action_id)
            if transition.triggered_by_action_id
            else None
        )
        action_description = triggering_action.description if triggering_action else "Navigation"
        input_values = {}
        page_id = transition.from_page_id
    hops.reverse()  # entry point first, blocked step last

    existing_max = session.exec(
        select(func.max(ExplorationStep.step_order)).where(
            ExplorationStep.blocked_task_id == blocked_task.id
        )
    ).one()
    start_order = (existing_max or 0) + 1

    for offset, (hop_page_id, hop_action_description, hop_input_values) in enumerate(hops):
        session.add(
            ExplorationStep(
                blocked_task_id=blocked_task.id,
                step_order=start_order + offset,
                page_id=hop_page_id,
                action_description=hop_action_description,
                input_values=hop_input_values,
            )
        )
    session.commit()


@activity.defn(name="DiscoveryActivity")
async def discovery_activity(input: DiscoveryActivityInput) -> DiscoveryActivityOutput:
    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(input.application_id))
        ).one()
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(input.discovery_run_id)
            )
        ).one()
        discovery_settings = session.exec(select(DiscoverySettings)).one()

        # Captured now, before any incremental commit below expires the ORM
        # object — rows are persisted as they're captured (`_persist`), not
        # batched to the end, so a crawl that outlives an Activity attempt
        # (a real site with no traversal cap, Story 2.3) never loses what it
        # already found, and the live feed (Story 2.2, AC 3) actually has
        # something to show while discovery is still running.
        discovery_run_pk = discovery_run.id
        application_pk = application.id

        page_ids_by_url: dict[str, uuid.UUID] = {}
        action_ids_by_key: dict[tuple[str, str], uuid.UUID] = {}
        page_count = 0
        login_page_url: str | None = None

        # Story 2.10 AC 7: a plain in-process dict, scoped to this Activity
        # execution (AD-16) — seeded from canonical Page rows, grown as this
        # run classifies NEW/VARIANT pages.
        state_cache = StateIdentityCache(
            threshold_same=application.state_identity_threshold_same,
            threshold_new=application.state_identity_threshold_new,
        )
        _seed_state_identity_cache(session, application_pk, state_cache)
        # Story 2.17 AC 2/3: resume past whatever's already confirmed
        # canonical, rather than re-crawling from scratch — but only for a
        # genuine resume: a deliberate `resume_discovery_run` call
        # (`input.resume`) or a Temporal retry of this same run after a
        # crash (Story 2.18's `activity.info().attempt > 1`, computed once
        # below and reused here). A plain fresh run (a brand-new
        # DiscoveryRun, first attempt) keeps Story 2.10's original design:
        # re-visit and reclassify every page against prior canonical rows,
        # never skip them outright — this flag is what actually
        # distinguishes "resume" from "re-discover".
        is_temporal_retry = activity.in_activity() and activity.info().attempt > 1
        already_confirmed_urls: frozenset[str] = frozenset()
        resume_seed: list[tuple[str, str | None]] = []
        if input.resume or is_temporal_retry:
            already_confirmed_urls, resume_seed = _seed_resume_frontier(session, application_pk)
        # Story 2.20 Task 3: loaded once here, alongside the state-identity
        # cache — an empty pool (no entries seeded) is exactly today's
        # behaviour, resolution starts at step 2 (Dev Notes).
        test_data_pool = _seed_test_data_pool(session, application_pk)
        # Story 2.10 Task 7: buffered per page URL until that page's
        # `CapturedPageComplete` signal arrives — classification needs the
        # page's *complete* action/form set, which crawler.py only knows
        # once a page's forms/buttons/tabs/frames/shadow-DOM have all been
        # exercised.
        page_buffers: dict[str, _PageBuffer] = {}
        # Story 2.16 Task 2: a DEFER on a page's own form is reached *during*
        # that page's form-processing loop — before its own Page row exists
        # (buffered above until `CapturedPageComplete`/`_classify_and_flush`
        # resolves it). `page_ids_by_url.get(url)` is therefore still `None`
        # for the very page the block just happened on, so the exploration
        # path can't be recorded yet. Held here and flushed by
        # `_classify_and_flush` once that page's `page_ids_by_url` entry is
        # finally resolved — same buffer-until-resolved pattern as
        # `page_buffers` itself, just for this one side effect.
        pending_exploration_paths: dict[str, list[tuple[uuid.UUID, str, dict]]] = {}
        # `[FIXED 2026-08-04]` Same buffer-until-resolved shape as
        # `pending_exploration_paths` above, for `CapturedTransition` items
        # whose destination page is still buffered — see `_persist_one`'s
        # own note on this branch.
        pending_transitions: dict[str, list[CapturedTransition]] = {}

        def _persist(item: CapturedItem) -> None:
            # `[FIXED 2026-07-22]` A single bad insert (any DB-level error —
            # a value too long for a column, a constraint violation, etc.)
            # used to poison this whole `Session`: SQLAlchemy refuses every
            # further `commit()` on a session with a failed transaction
            # (`psycopg.errors.InFailedSqlTransaction`) until an explicit
            # `rollback()` happens, which nothing here ever did. Observed
            # live: one bad `ApiEndpoint` capture cascaded into every
            # subsequent capture failing the same way for the rest of the
            # crawl, which eventually surfaced as an uncaught exception that
            # crashed the *entire* Activity — Temporal then retried it from
            # absolute scratch, repeatedly (visible as `discovery_run.stage`
            # regressing back to "authenticating" every ~100s, with no
            # `failure_reason` ever recorded, since the crash happened
            # trying to persist that very failure). One bad capture should
            # be skipped, not take down the whole run.
            try:
                _persist_one(item)
            except Exception:
                logger.exception(
                    "discovery_activity: failed to persist a %s capture — "
                    "rolling back and continuing",
                    type(item).__name__,
                )
                session.rollback()

        def _create_page_row(
            item: CapturedPage, variant_of_page_id: uuid.UUID | None = None
        ) -> Page:
            nonlocal page_count
            page = Page(
                application_id=application_pk,
                discovery_run_id=discovery_run_pk,
                url=item.url,
                title=item.title,
                object_storage_key=item.object_storage_key,
                heading=item.heading,
                structural_tokens=item.structural_tokens,
                variant_of_page_id=variant_of_page_id,
            )
            session.add(page)
            session.commit()
            session.refresh(page)
            page_ids_by_url[item.url] = page.id
            page_count += 1
            return page

        def _persist_one(item: CapturedItem) -> None:
            if isinstance(item, CapturedPage):
                _create_page_row(item)
            elif isinstance(item, CapturedForm):
                page_id = page_ids_by_url.get(item.page_url)
                if page_id is None:
                    return
                form = Form(
                    application_id=application_pk,
                    discovery_run_id=discovery_run_pk,
                    page_id=page_id,
                    action_url=item.action_url,
                    method=item.method,
                )
                session.add(form)
                session.commit()
                session.refresh(form)
                for captured_field in item.fields:
                    field_row = FormField(
                        form_id=form.id,
                        name=captured_field.name,
                        input_type=captured_field.input_type,
                        required=captured_field.required,
                        default_value=captured_field.default_value,
                        captured_selector=captured_field.captured_selector,
                        locator_candidates=captured_field.locator_candidates,
                    )
                    session.add(field_row)
                    session.commit()
                    session.refresh(field_row)
                    if captured_field.required:
                        session.add(
                            ValidationRule(form_field_id=field_row.id, rule_type="required")
                        )
                session.commit()
            elif isinstance(item, CapturedAction):
                page_id = page_ids_by_url.get(item.page_url)
                if page_id is None:
                    return
                action_row = Action(
                    application_id=application_pk,
                    discovery_run_id=discovery_run_pk,
                    page_id=page_id,
                    description=item.description,
                    captured_selector=item.captured_selector,
                    locator_candidates=item.locator_candidates,
                    representative=item.representative,
                )
                session.add(action_row)
                session.commit()
                session.refresh(action_row)
                action_ids_by_key[(item.page_url, item.description)] = action_row.id
            elif isinstance(item, CapturedApiCall):
                page_id = page_ids_by_url.get(item.page_url)
                if page_id is None:
                    return
                session.add(
                    ApiEndpoint(
                        application_id=application_pk,
                        discovery_run_id=discovery_run_pk,
                        page_id=page_id,
                        method=item.method,
                        path=item.path,
                        status_code=item.status_code,
                        response_summary=item.response_summary,
                    )
                )
                session.commit()
            elif isinstance(item, CapturedTransition):
                from_id = page_ids_by_url.get(item.from_url)
                to_id = page_ids_by_url.get(item.to_url)
                if from_id is not None and to_id is None:
                    # `[FIXED 2026-08-04]` The destination page's own Page
                    # row is still buffered (Story 2.10 Task 7: not resolved
                    # until that page's `CapturedPageComplete` fires), not
                    # genuinely unresolvable — this is the overwhelmingly
                    # common case for a plain BFS link-follow into a page
                    # not visited before. Dropping here permanently, as this
                    # branch used to, silently starved `PageTransition` of
                    # almost every forward-navigation edge since Task 7
                    # landed (discovered via Story 2.16's own path
                    # reconstruction depending on it) — starving Story 2.6's
                    # navigation-graph journey clustering of the same edges.
                    # Buffered for a retry once `_classify_and_flush`
                    # resolves the destination, instead of a real fix here.
                    pending_transitions.setdefault(item.to_url, []).append(item)
                    return
                if from_id is None or to_id is None:
                    # A genuinely unresolvable endpoint (e.g. a page that
                    # was never visited at all) — unrecoverable, same
                    # tolerance this branch always had.
                    return
                triggered_by_action_id = None
                if item.triggered_by_description:
                    triggered_by_action_id = action_ids_by_key.get(
                        (item.from_url, item.triggered_by_description)
                    )
                session.add(
                    PageTransition(
                        application_id=application_pk,
                        discovery_run_id=discovery_run_pk,
                        from_page_id=from_id,
                        to_page_id=to_id,
                        triggered_by_action_id=triggered_by_action_id,
                    )
                )
                session.commit()

        def _record_diagnostic(kind: str, payload: dict) -> None:
            # Story 2.22 Task 1's sink, called from crawler.py exactly like
            # `_persist` — off the event loop, same rationale as `_persist`'s
            # own docstring (a slow/failed commit here must stall only this
            # activity, and `record_diagnostic` itself never raises).
            if kind == "synthetic_data":
                # Story 2.13 Task 4: a typed row, not a generic JSONB
                # diagnostic — the "what data touched the target
                # application" report needs to query this directly. Falls
                # back to a plain diagnostic if the write itself fails, same
                # never-take-down-the-crawl guarantee as `_persist`/
                # `record_diagnostic`.
                try:
                    session.add(
                        SyntheticDataEntry(
                            application_id=application_pk,
                            discovery_run_id=discovery_run_pk,
                            page_id=page_ids_by_url.get(payload["page_url"]),
                            field_name=payload["field_name"],
                            normalized_key=payload["normalized_key"],
                            value=payload["value"],
                            source=payload["source"],
                            is_placeholder_file=payload["is_placeholder_file"],
                            outcome=payload["outcome"],
                        )
                    )
                    session.commit()
                except Exception:
                    logger.exception(
                        "_record_diagnostic: failed to persist a SyntheticDataEntry — continuing"
                    )
                    session.rollback()
                return
            if kind == "discovery_error":
                # Story 2.18 Task 1: a typed row, not a generic JSONB
                # diagnostic — Story 2.22's report reads this table directly
                # for its Errored category, same reasoning as
                # `synthetic_data` above. Falls back silently (never raises)
                # on a write failure, same guarantee as every other branch
                # here.
                try:
                    session.add(
                        DiscoveryError(
                            application_id=application_pk,
                            discovery_run_id=discovery_run_pk,
                            page_id=page_ids_by_url.get(payload.get("page_url") or ""),
                            error_code=payload["error_code"],
                            message=payload["message"],
                            retry_count=payload.get("retry_count", 0),
                        )
                    )
                    session.commit()
                except Exception:
                    logger.exception(
                        "_record_diagnostic: failed to persist a DiscoveryError — continuing"
                    )
                    session.rollback()
                return
            if kind == "execution_decision" and payload.get("action") == "DEFER":
                # Story 2.15 Task 3: attach-or-create the aggregated
                # BlockedTask alongside the plain diagnostic below (not
                # instead of it — this is a separate aggregated-state
                # entity, not a duplicate of the per-event log the way
                # `synthetic_data` replaces its own generic diagnostic).
                try:
                    blocked_task = blocked_frontier.attach_or_create(
                        session,
                        application_id=application_pk,
                        discovery_run_id=discovery_run_pk,
                        aggregation_key=payload["normalized_key"],
                        required_description=payload["label"],
                        required_type=(
                            "data"
                            if payload["deciding_specialist"] == "data_resolver"
                            else "approval"
                        ),
                    )
                    # Story 2.16 Task 2/4: the path that reached this block —
                    # extends the same BlockedTask's trail on a repeat block
                    # (AC 5), never a fresh one, since `attach_or_create`
                    # above already resolved to the same row by key.
                    current_page_id = page_ids_by_url.get(payload["url"])
                    if current_page_id is not None:
                        _record_exploration_path(
                            session,
                            blocked_task=blocked_task,
                            current_page_id=current_page_id,
                            blocking_action_description=payload["label"],
                            blocking_input_values={"requested": payload["label"]},
                        )
                    else:
                        # The blocked page's own Page row isn't persisted
                        # yet — held until `_classify_and_flush` resolves
                        # `page_ids_by_url[url]` for it (see
                        # `pending_exploration_paths`'s own docstring above).
                        pending_exploration_paths.setdefault(payload["url"], []).append(
                            (blocked_task.id, payload["label"], {"requested": payload["label"]})
                        )
                except Exception:
                    logger.exception(
                        "_record_diagnostic: failed to attach/create a BlockedTask — continuing"
                    )
                    session.rollback()
            record_diagnostic(session, discovery_run_pk, kind, payload)

        def _flush_pending_transitions(url: str) -> None:
            # `[FIXED 2026-08-04]` Called once `page_ids_by_url[url]` is
            # resolved (either branch of `_classify_and_flush`) — retries
            # whatever `CapturedTransition` items were buffered because this
            # exact page was their unresolved destination. Must run before
            # `_flush_pending_exploration_paths` below: an exploration path
            # walks `PageTransition` backward, so the edge into this page
            # needs to exist first.
            pending = pending_transitions.pop(url, None)
            if not pending:
                return
            for transition_item in pending:
                _persist_one(transition_item)

        def _flush_pending_exploration_paths(url: str) -> None:
            # Story 2.16 Task 2: called once `page_ids_by_url[url]` is
            # finally resolved (either branch of `_classify_and_flush`) —
            # writes whatever DEFERs happened during this page's own
            # form/button processing, now that its Page row (or SAME-verdict
            # alias) exists to reference.
            pending = pending_exploration_paths.pop(url, None)
            if not pending:
                return
            resolved_page_id = page_ids_by_url.get(url)
            if resolved_page_id is None:
                return
            for blocked_task_id, action_description, input_values in pending:
                blocked_task_row = session.get(BlockedTask, blocked_task_id)
                if blocked_task_row is None:
                    continue
                try:
                    _record_exploration_path(
                        session,
                        blocked_task=blocked_task_row,
                        current_page_id=resolved_page_id,
                        blocking_action_description=action_description,
                        blocking_input_values=input_values,
                    )
                except Exception:
                    logger.exception(
                        "_flush_pending_exploration_paths: failed to record a path — continuing"
                    )
                    session.rollback()

        def _get_ai_opinion(
            heading_a: str, actions_a: list[str], heading_b: str, actions_b: list[str]
        ) -> str | None:
            # Story 2.10 AC 3: called only in the ambiguous band. Best-
            # effort — a timeout/failure is a logged no-op; the engine's own
            # verdict (already decided by the caller) never changes because
            # of this. `asyncio.run` is safe here: this runs inside
            # `asyncio.to_thread`, a worker thread with no event loop of
            # its own already running.
            try:
                return asyncio.run(
                    HostedAIProvider().infer_state_similarity(
                        heading_a, actions_a, heading_b, actions_b
                    )
                )
            except Exception:
                logger.warning(
                    "state_identity: AI tiebreaker call failed — proceeding with the "
                    "engine's own verdict",
                    exc_info=True,
                )
                return None

        def _classify_and_flush(url: str) -> None:
            buf = page_buffers.pop(url, None)
            if buf is None or buf.page is None:
                # Nothing was ever buffered for this URL — e.g. the mid-
                # crawl reauth-retry early exit fired before a CapturedPage
                # was ever added for this dequeue attempt.
                return

            action_names = [a.description for a in buf.actions]
            field_names = [f.name for form_item in buf.forms for f in form_item.fields if f.name]
            fingerprint = compute_fingerprint(
                buf.page.heading, action_names, field_names, buf.page.structural_tokens or []
            )
            result = state_cache.classify(url, fingerprint)

            ai_opinion = None
            if result.ambiguous:
                matched = result.matched_fingerprint
                ai_opinion = _get_ai_opinion(
                    buf.page.heading or "",
                    action_names,
                    matched.heading if matched else "",
                    list(matched.action_names) if matched else [],
                )

            score_result = result.score_result
            _record_diagnostic(
                "state_identity",
                {
                    "url": url,
                    "route_template": result.route_template,
                    "matched_page_id": (
                        str(result.matched_page_id) if result.matched_page_id else None
                    ),
                    "verdict": result.verdict,
                    "ambiguous": result.ambiguous,
                    "widened_mode": result.widened_mode,
                    "threshold_same": state_cache.threshold_same,
                    "threshold_new": state_cache.threshold_new,
                    "heading_score": score_result.heading_score if score_result else None,
                    "action_score": score_result.action_score if score_result else None,
                    "form_score": score_result.form_score if score_result else None,
                    "structure_score": score_result.structure_score if score_result else None,
                    "composite_score": score_result.composite if score_result else None,
                    "ai_opinion": ai_opinion,
                },
            )

            if result.verdict == "SAME":
                # AC 2: write nothing, but alias so later Action/Form/
                # Transition references against this URL still resolve.
                if result.matched_page_id is not None:
                    page_ids_by_url[url] = result.matched_page_id
                _flush_pending_transitions(url)
                _flush_pending_exploration_paths(url)
                return

            page_row = _create_page_row(
                buf.page,
                variant_of_page_id=(
                    result.matched_page_id if result.verdict == "VARIANT" else None
                ),
            )
            for form_item in buf.forms:
                _persist_one(form_item)
            for action_item in buf.actions:
                _persist_one(action_item)
            for api_call_item in buf.api_calls:
                _persist_one(api_call_item)
            state_cache.register(page_row.id, url, fingerprint, result.route_template)
            _flush_pending_transitions(url)
            _flush_pending_exploration_paths(url)

        def _persist_with_classification(item: CapturedItem) -> None:
            # Story 2.10 Task 7: the main crawl's `on_capture` — buffers
            # per-page items until that page's `CapturedPageComplete`
            # signal, then classifies with the *complete* action/form set.
            # `CapturedTransition` is deliberately not buffered: it
            # references two pages independently (often one not yet even
            # visited), and the existing `page_ids_by_url` lookup already
            # tolerates "not resolved yet" by dropping the row — the same
            # tolerance this file had before this story.
            try:
                if isinstance(item, CapturedPage):
                    page_buffers.setdefault(item.url, _PageBuffer()).page = item
                elif isinstance(item, CapturedForm):
                    page_buffers.setdefault(item.page_url, _PageBuffer()).forms.append(item)
                elif isinstance(item, CapturedAction):
                    page_buffers.setdefault(item.page_url, _PageBuffer()).actions.append(item)
                elif isinstance(item, CapturedApiCall):
                    page_buffers.setdefault(item.page_url, _PageBuffer()).api_calls.append(item)
                elif isinstance(item, CapturedTransition):
                    _persist(item)
                elif isinstance(item, CapturedPageComplete):
                    _classify_and_flush(item.url)
            except Exception:
                logger.exception(
                    "discovery_activity: failed to classify/persist for a %s — "
                    "rolling back and continuing",
                    type(item).__name__,
                )
                session.rollback()

        def _persist_and_note_login_page(item: CapturedItem) -> None:
            # `establish_session` captures the login page/form (if any)
            # before `run_discovery_crawl` starts — remembering its URL here
            # lets that crawl seed its first page's `from_url` with it, so
            # the login page isn't an isolated island in the navigation
            # graph `journey_clustering.py` groups pages by (see
            # `crawler.py`'s matching `[ADDED 2026-07-23]` note).
            nonlocal login_page_url
            _persist(item)
            if login_page_url is None and isinstance(item, CapturedPage):
                login_page_url = item.url

        # Story 2.18 Task 2 (AC 1): a Temporal Activity retry (attempt > 1)
        # means the worker crashed or was killed mid-run — everything already
        # committed via `_persist`/`_persist_with_classification` above is
        # safe (AD-23: the typed-row writes already are the checkpoint), and
        # `already_confirmed_urls`/`resume_seed` above (Story 2.17) resume
        # this same run past whatever was already confirmed canonical rather
        # than re-crawling from scratch — a page that crashed mid-interaction
        # never got a canonical row committed in the first place (buffered
        # captures are lost, not partially persisted), so it's correctly
        # re-visited and re-verified, never assumed complete. This is
        # informational logging of that fact, not a new recovery mechanism.
        if is_temporal_retry:
            _record_diagnostic(
                "discovery_error",
                {
                    "error_code": "DISC-001",
                    "message": (
                        f"Engine restarted (Temporal attempt {activity.info().attempt}) — "
                        "resuming from the last confirmed page/action/form already committed "
                        "to the database; the in-flight page at crash time is re-verified, "
                        "not assumed complete."
                    ),
                    "retry_count": activity.info().attempt - 1,
                },
            )

        try:
            # Both are synchronous network clients (hvac/requests, boto3/
            # urllib3) — off the event loop so a slow Vault/S3 response
            # stalls only this activity, not the heartbeat/poll loop this
            # worker owes Temporal for every other concurrent workflow.
            vault_client = VaultSecretsClient()
            credential = await asyncio.to_thread(
                vault_client.resolve, SecretRef(path=input.secret_ref)
            )
            object_store = await asyncio.to_thread(ObjectStore)

            discovery_run.stage = "authenticating"
            session.add(discovery_run)
            session.commit()

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                context = await establish_session(
                    browser,
                    auth_method=application.auth_method,
                    credential=credential,
                    base_url=application.url,
                    login_url=application.login_url,
                    # A real cross-origin OAuth login round-trip can take
                    # long enough on its own to trip Temporal's heartbeat
                    # timeout before the crawl even starts — see session.py's
                    # `[FIXED 2026-07-22, again]` note.
                    heartbeat=activity.heartbeat if activity.in_activity() else None,
                    # `[ADDED 2026-07-23]` Captures the login page/form once,
                    # up front, so a "Sign in" journey has real Page/Form
                    # rows to be inferred from — see session.py's matching note.
                    object_store=object_store,
                    discovery_run_id=discovery_run.id,
                    on_capture=_persist_and_note_login_page,
                )

                discovery_run.stage = "discovering"
                session.add(discovery_run)
                session.commit()

                result = await run_discovery_crawl(
                    context,
                    application.url,
                    object_store,
                    discovery_run.id,
                    # Story 2.10 Task 7: classifies SAME/VARIANT/NEW once a
                    # page's full capture set is known, not at first
                    # navigation. The pre-crawl login-page capture above
                    # bypasses this entirely (`_persist_and_note_login_page`
                    # -> `_persist`, unbuffered) since it never emits a
                    # `CapturedPageComplete` signal.
                    on_capture=_persist_with_classification,
                    # `activity.heartbeat()` raises outside a real Temporal
                    # activity execution context — only true in production,
                    # not when this function is called directly (as the
                    # integration tests do).
                    heartbeat=activity.heartbeat if activity.in_activity() else None,
                    # Lets the crawler replay this same login mid-crawl if a
                    # short-lived session expires before traversal finishes
                    # (see crawler.py's `_MAX_CONSECUTIVE_REAUTH_ATTEMPTS`).
                    auth_method=application.auth_method,
                    credential=credential,
                    login_page_url=login_page_url,
                    on_diagnostic=_record_diagnostic,
                    # Story 2.9 AC 4: run-level override wins when set, then
                    # per-Application, then the global DiscoverySettings
                    # fallback (Settings page Navigation Timeout).
                    page_load_timeout_seconds=(
                        discovery_run.page_load_timeout_seconds
                        or application.page_load_timeout_seconds
                        or discovery_settings.navigation_timeout_seconds
                    ),
                    max_pages=discovery_settings.max_pages,
                    max_duration_seconds=discovery_settings.max_discovery_duration_minutes * 60,
                    interaction_level=discovery_settings.interaction_level,
                    data_resolver_pool=test_data_pool,
                    # Story 2.12 Task 3: replaces the Planner's pass-through
                    # `default_safety` — a real per-Application posture from
                    # here on.
                    safety=SafetyState(posture=application.safety_posture),
                    # Story 2.17 AC 2/3 / Story 2.18 Task 2: resume past
                    # whatever's already confirmed canonical for this
                    # Application, rather than re-crawling from scratch.
                    # Both empty for a brand-new Application — today's exact
                    # behaviour.
                    already_confirmed_urls=already_confirmed_urls or None,
                    resume_seed=resume_seed or None,
                )
                await context.close()
                await browser.close()
        except Exception as exc:
            # A genuine crash, unrelated to session expiry (AD-11 is the
            # distinct, expected case above) — this story doesn't build a
            # full error-handling framework, only ensures the run doesn't
            # stay stuck showing `running` forever. Whatever was captured
            # before the crash is already committed via `_persist` above —
            # this empty result only affects the return value below.
            # `[FIXED 2026-07-22]` This used to swallow the exception
            # entirely — no log, no `failure_reason` — leaving a "failed"
            # run with zero trace of why. Logged and recorded now so a real
            # failure is actually diagnosable instead of a dead end.
            logger.exception(
                "discovery_activity crashed for discovery_run=%s", input.discovery_run_id
            )
            result = CrawlResult()
            discovery_run.status = "failed"
            discovery_run.failure_reason = f"{type(exc).__name__}: {exc}"[:500]
        else:
            if result.session_expired:
                # This must stay a distinct code path from `complete` below —
                # AD-11 exists specifically so a session-expired run never
                # silently lands in `complete`.
                discovery_run.status = "failed"
                discovery_run.failure_reason = "session_expired"
            else:
                # Story 2.3, AD-10: exhaustive traversal is the only stop
                # condition this story implements, and this is the one and
                # only place `complete` gets written.
                discovery_run.status = "complete"

        session.add(discovery_run)
        session.commit()

        return DiscoveryActivityOutput(status=discovery_run.status, page_count=page_count)


@activity.defn(name="ApplicationModelBuilderActivity")
async def application_model_builder_activity(
    input: ApplicationModelBuilderActivityInput,
) -> ApplicationModelBuilderActivityOutput:
    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(input.discovery_run_id)
            )
        ).one()
        application = session.get(Application, discovery_run.application_id)
        assert application is not None

        component_count = build_application_model(session, application.id)
        return ApplicationModelBuilderActivityOutput(component_count=component_count)


def _get_or_create_capability(session: Session, application_id: uuid.UUID, name: str) -> Capability:
    existing = session.exec(
        select(Capability).where(
            Capability.application_id == application_id, Capability.name == name
        )
    ).first()
    if existing is not None:
        return existing
    capability = Capability(application_id=application_id, name=name)
    session.add(capability)
    session.flush()
    return capability


@activity.defn(name="InferenceActivity")
async def inference_activity(input: InferenceActivityInput) -> list[str]:
    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(input.discovery_run_id)
            )
        ).one()
        application = session.get(Application, discovery_run.application_id)
        assert application is not None

        # AC8 (CR-2): set independently of `status`, which already flipped to
        # "complete" back in discovery_activity, well before this Activity runs.
        discovery_run.stage = "analyzing"
        session.add(discovery_run)
        session.commit()

        # Canonical rows only (merged_into_id IS NULL) — never a superseded
        # row (AD-14).
        pages = list(
            session.exec(
                select(Page).where(
                    Page.application_id == application.id, Page.merged_into_id.is_(None)  # type: ignore[union-attr]
                )
            ).all()
        )
        forms = list(
            session.exec(
                select(Form).where(
                    Form.application_id == application.id, Form.merged_into_id.is_(None)  # type: ignore[union-attr]
                )
            ).all()
        )
        api_endpoints = list(
            session.exec(
                select(ApiEndpoint).where(
                    ApiEndpoint.application_id == application.id,
                    ApiEndpoint.merged_into_id.is_(None),  # type: ignore[union-attr]
                )
            ).all()
        )
        components = list(
            session.exec(select(Component).where(Component.application_id == application.id)).all()
        )
        # PageTransition has no `merged_into_id` of its own (deduped in place
        # by 2.5's ApplicationModelBuilderActivity) but its `from_page_id`/
        # `to_page_id` can still point at a since-superseded Page row, so
        # resolving through every Page (not just canonical ones) is needed to
        # find the transition's actual canonical endpoint.
        all_pages_by_id = {
            p.id: p
            for p in session.exec(
                select(Page).where(Page.application_id == application.id)
            ).all()
        }

        def _canonical_page_id(page_id: uuid.UUID) -> uuid.UUID:
            row = all_pages_by_id.get(page_id)
            return (row.merged_into_id or row.id) if row else page_id

        transitions = list(
            session.exec(
                select(PageTransition).where(PageTransition.application_id == application.id)
            ).all()
        )
        assertions = list(
            session.exec(select(Assertion).where(Assertion.application_id == application.id)).all()
        )

        forms_by_page: dict[uuid.UUID, list[Form]] = {}
        for form in forms:
            forms_by_page.setdefault(form.page_id, []).append(form)
        api_by_page: dict[uuid.UUID, list[ApiEndpoint]] = {}
        for endpoint in api_endpoints:
            api_by_page.setdefault(endpoint.page_id, []).append(endpoint)
        components_by_page: dict[uuid.UUID, list[Component]] = {}
        for component in components:
            components_by_page.setdefault(component.page_id, []).append(component)
        transitions_by_page: dict[uuid.UUID, list[Page]] = {}
        for transition in transitions:
            canonical_from = _canonical_page_id(transition.from_page_id)
            canonical_to = all_pages_by_id.get(_canonical_page_id(transition.to_page_id))
            if canonical_to is not None:
                transitions_by_page.setdefault(canonical_from, []).append(canonical_to)
        assertions_by_page: dict[uuid.UUID, list[Assertion]] = {}
        for assertion in assertions:
            assertions_by_page.setdefault(assertion.page_id, []).append(assertion)

        for page in pages:
            # Transient attributes (not mapped columns) so HostedAIProvider
            # gets the full canonical picture per page, not just a bare URL.
            # SQLModel/Pydantic rejects `page.forms = ...` outright (no such
            # declared field) — `object.__setattr__` bypasses that check to
            # attach plain, non-persisted instance data.
            object.__setattr__(page, "forms", forms_by_page.get(page.id, []))
            object.__setattr__(page, "api_endpoints", api_by_page.get(page.id, []))
            object.__setattr__(page, "components", components_by_page.get(page.id, []))
            object.__setattr__(page, "outgoing_transitions", transitions_by_page.get(page.id, []))
            object.__setattr__(page, "assertions", assertions_by_page.get(page.id, []))

        # Navigation-graph clustering (Story 2.6 rework): group pages by how
        # they're actually navigated between — free, no LLM — then bin-pack
        # those clusters into batches under a page-count budget, so no single
        # HostedAIProvider call ever has to reason over more than one
        # coherent, connected subset of the Application. Transitions must be
        # resolved to canonical page ids first, or an edge referencing a
        # since-superseded row would silently fail to connect anything.
        canonical_transitions = [
            PageTransition(
                application_id=application.id,
                discovery_run_id=discovery_run.id,
                from_page_id=_canonical_page_id(t.from_page_id),
                to_page_id=_canonical_page_id(t.to_page_id),
            )
            for t in transitions
        ]
        batches = cluster_and_batch(pages, canonical_transitions)

        pages_by_id = {page.id: page for page in pages}
        journey_external_ids: list[str] = []
        candidates_processed = 0

        for batch in batches:
            candidates = await HostedAIProvider().infer_journeys(batch)

            for candidate in candidates:
                if candidates_processed >= MAX_CANDIDATE_JOURNEYS_PER_RUN:
                    logger.warning(
                        "InferenceActivity: run-level cap (%d) reached for discovery_run=%s — "
                        "dropping candidate %r",
                        MAX_CANDIDATE_JOURNEYS_PER_RUN,
                        input.discovery_run_id,
                        candidate.name,
                    )
                    continue
                candidates_processed += 1

                supporting_pages = [
                    pages_by_id[page_id]
                    for step in candidate.steps
                    if (page_id := uuid.UUID(step.page_id)) in pages_by_id
                ]
                if not supporting_pages:
                    continue
                supporting_page_ids = {page.id for page in supporting_pages}
                supporting_api_endpoints = [
                    e for e in api_endpoints if e.page_id in supporting_page_ids
                ]
                supporting_components = [
                    c for c in components if c.page_id in supporting_page_ids
                ]

                identity_key = compute_identity_key(
                    supporting_pages, supporting_components, supporting_api_endpoints
                )

                # AD-13/AD-9: a retry (or a concurrent InferenceActivity run
                # against the same Application) that finds a matching
                # identity_key skips re-creating the Journey row.
                journey = session.exec(
                    select(Journey).where(
                        Journey.application_id == application.id,
                        Journey.identity_key == identity_key,
                    )
                ).first()

                if journey is None:
                    capability = _get_or_create_capability(
                        session, application.id, candidate.capability_name
                    )
                    journey = Journey(
                        application_id=application.id,
                        discovery_run_id=discovery_run.id,
                        capability_id=capability.id,
                        name=candidate.name,
                        description=candidate.description or None,
                        identity_key=identity_key,
                    )
                    session.add(journey)
                    try:
                        session.flush()
                    except IntegrityError:
                        # Lost the race to a concurrent InferenceActivity run
                        # — the UNIQUE(application_id, identity_key)
                        # constraint (not just this select) is what actually
                        # prevents the duplicate. Use the row the other run
                        # created instead of retrying our own insert.
                        session.rollback()
                        journey = session.exec(
                            select(Journey).where(
                                Journey.application_id == application.id,
                                Journey.identity_key == identity_key,
                            )
                        ).one()

                # Idempotent under retry: rewrite this Journey's steps from
                # scratch rather than appending, so a retry never duplicates
                # step rows or leaves stale ones from a prior attempt. The
                # deletes must be flushed before the new rows are added —
                # otherwise SQLAlchemy may order the new INSERTs before the
                # old DELETEs within the same flush, colliding with the
                # UNIQUE(journey_id, step_order) constraint on a still-live
                # old row.
                for existing_step in session.exec(
                    select(JourneyStep).where(JourneyStep.journey_id == journey.id)
                ).all():
                    session.delete(existing_step)
                session.flush()

                supporting_pages_by_id = {page.id: page for page in supporting_pages}
                for order, step in enumerate(candidate.steps, start=1):
                    step_page_id = uuid.UUID(step.page_id)
                    if step_page_id not in supporting_pages_by_id:
                        continue
                    session.add(
                        JourneyStep(
                            journey_id=journey.id,
                            page_id=step_page_id,
                            step_order=order,
                            stage_label=step.stage_label,
                        )
                    )
                session.commit()

                journey_external_ids.append(str(journey.external_id))

                # `[CORRECTED 2026-07-21]` No GenerationWorkflow start here
                # anymore — Story 4.1's 2026-07-21 correction moved that
                # trigger to the "Continue to Scenarios" endpoint (Story 4.1
                # Task 5), fired by explicit user action, not automatically
                # per candidate at discovery time.

        return journey_external_ids
