"""Domain whitelist — which hosts an Application may be onboarded on.

Admins manage the list (Settings → Approved domains). Onboarding
(`require_approved_domain`, called from the application-creation routes in
`main`) and the Applications list's `domain_approved` flag both read it. A URL
is approved when its host equals an entry or is a subdomain of one.
"""

import ipaddress
import uuid
from urllib.parse import urlsplit

from domain import Application, ApprovedDomain
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api.activity import record_activity
from api.auth import CurrentAdminDep, CurrentOrgIdDep, SessionDep

router = APIRouter()

DOMAIN_NOT_APPROVED = "DOMAIN_NOT_APPROVED"
DOMAIN_IN_USE = "DOMAIN_IN_USE"


def host_of(url: str) -> str | None:
    """Lowercase hostname of a URL (scheme optional), or None if it has none."""
    raw = url.strip()
    if not raw:
        return None
    try:
        host = urlsplit(raw if "://" in raw else f"//{raw}").hostname
    except ValueError:
        return None
    return host.lower().rstrip(".") if host else None


def normalize_domain(raw: str) -> str:
    """A bare domain from admin input — 422 for anything that isn't one."""
    value = raw.strip().lower()
    host = host_of(value)
    # Only a host (optionally a pasted scheme/port) is accepted, never a path.
    if host is None or "*" in value or " " in value or "/" in value.split("://")[-1].rstrip("/"):
        raise HTTPException(status_code=422, detail="Enter a domain like the host part of the URL, without a path.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        # ponytail: single-label hosts are rejected (so `com` can't approve a
        # whole TLD) but multi-label public suffixes (`co.uk`, `github.io`)
        # aren't — a fuller version would check the public-suffix list.
        if "." not in host and host != "localhost":
            raise HTTPException(status_code=422, detail="Enter a full domain, e.g. the app's own host name.") from None
    return host


def _matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def approved_hosts(session: Session, organization_id: uuid.UUID) -> list[str]:
    return list(
        session.exec(select(ApprovedDomain.host).where(ApprovedDomain.organization_id == organization_id)).all()
    )


def url_is_approved(url: str, domains: list[str]) -> bool:
    host = host_of(url)
    return host is not None and any(_matches(host, d) for d in domains)


def require_approved_domain(session: Session, organization_id: uuid.UUID, url: str) -> None:
    if not url_is_approved(url, approved_hosts(session, organization_id)):
        raise HTTPException(status_code=403, detail=DOMAIN_NOT_APPROVED)


class DomainApplicationRead(BaseModel):
    id: uuid.UUID
    name: str


class DomainRead(BaseModel):
    id: uuid.UUID
    host: str
    created_by: str
    # Applications whose URL falls under this domain — the in-use warning.
    applications: list[DomainApplicationRead]


class DomainPayload(BaseModel):
    host: str


class DomainCheckPayload(BaseModel):
    url: str


class DomainCheckRead(BaseModel):
    allowed: bool
    host: str | None


def applications_using(domain: str, all_domains: list[str], applications: list[Application]) -> list[Application]:
    """Applications that depend on `domain`: under it, and not also covered by
    another approved domain (removing `app.example.com` is harmless while
    `example.com` stays)."""
    others = [d for d in all_domains if d != domain]
    return [
        a
        for a in applications
        if (h := host_of(a.url)) is not None
        and _matches(h, domain)
        and not any(_matches(h, other) for other in others)
    ]


def _read(domain: ApprovedDomain, all_domains: list[str], applications: list[Application]) -> DomainRead:
    return DomainRead(
        id=domain.external_id,
        host=domain.host,
        created_by=domain.created_by_name,
        applications=[
            DomainApplicationRead(id=a.external_id, name=a.name)
            for a in applications_using(domain.host, all_domains, applications)
        ],
    )


def _org_applications(session: Session, organization_id: uuid.UUID) -> list[Application]:
    return list(
        session.exec(
            select(Application).where(
                Application.organization_id == organization_id,
                Application.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        ).all()
    )


def _get_domain(session: Session, organization_id: uuid.UUID, external_id: uuid.UUID) -> ApprovedDomain:
    domain = session.exec(
        select(ApprovedDomain).where(
            ApprovedDomain.external_id == external_id, ApprovedDomain.organization_id == organization_id
        )
    ).first()
    if domain is None:
        raise HTTPException(status_code=404, detail="domain not found")
    return domain


def _duplicate() -> HTTPException:
    return HTTPException(status_code=409, detail="That domain is already in the list.")


@router.get("/domains", response_model=list[DomainRead])
def list_domains(session: SessionDep, organization_id: CurrentOrgIdDep) -> list[DomainRead]:
    domains = session.exec(
        select(ApprovedDomain).where(ApprovedDomain.organization_id == organization_id).order_by(ApprovedDomain.host)
    ).all()
    applications = _org_applications(session, organization_id)
    hosts = [d.host for d in domains]
    return [_read(d, hosts, applications) for d in domains]


@router.post("/domains", response_model=DomainRead, status_code=201)
def add_domain(payload: DomainPayload, session: SessionDep, admin: CurrentAdminDep) -> DomainRead:
    host = normalize_domain(payload.host)
    if host in approved_hosts(session, admin.organization_id):
        raise _duplicate()
    domain = ApprovedDomain(organization_id=admin.organization_id, host=host, created_by_name=admin.name)
    session.add(domain)
    record_activity(session, admin, "settings", f"Approved domain {host}")
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise _duplicate() from None
    return _read(
        domain, approved_hosts(session, admin.organization_id), _org_applications(session, admin.organization_id)
    )


@router.delete("/domains/{external_id}", status_code=204)
def delete_domain(external_id: uuid.UUID, session: SessionDep, admin: CurrentAdminDep) -> None:
    domain = _get_domain(session, admin.organization_id, external_id)
    # Server-enforced (the UI warns first): a domain applications still depend
    # on can't be removed — delete those applications, then retry.
    if applications_using(
        domain.host,
        approved_hosts(session, admin.organization_id),
        _org_applications(session, admin.organization_id),
    ):
        raise HTTPException(status_code=409, detail=DOMAIN_IN_USE)
    record_activity(session, admin, "settings", f"Removed approved domain {domain.host}")
    session.delete(domain)
    session.commit()


@router.post("/domains/check", response_model=DomainCheckRead)
def check_domain(
    payload: DomainCheckPayload, session: SessionDep, organization_id: CurrentOrgIdDep
) -> DomainCheckRead:
    return DomainCheckRead(
        allowed=url_is_approved(payload.url, approved_hosts(session, organization_id)),
        host=host_of(payload.url),
    )
