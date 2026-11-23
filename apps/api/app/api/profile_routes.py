"""Operaciones autenticadas del perfil empresarial y sus evidencias."""

from hashlib import sha256
from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.document_routes import PRIVATE, ServicesDep, read_upload
from app.api.filter_routes import Database
from app.api.routes import Administrator, EagMember, require_eag_administrator, require_eag_member
from app.config import Settings
from app.db.models import utcnow
from app.db.profile_models import ProfileEvidence, ProfileVersion
from app.documents.service import (
    DocumentError,
    filename_from_header,
    inspect_upload,
    utc,
)
from app.profile import Entry, EvidenceView, ProfileView, ProfileWrite, VersionSummary

router = APIRouter(
    prefix="/api/v1/company-profile", tags=["perfil empresarial"],
    dependencies=[Depends(require_eag_member)],
)
admin_only = [Depends(require_eag_administrator)]


def current(session: Database, organization_id: UUID) -> ProfileVersion | None:
    return session.scalar(select(ProfileVersion).where(
        ProfileVersion.organization_id == organization_id,
    ).order_by(ProfileVersion.version.desc()).limit(1))


def view(row: ProfileVersion | None) -> ProfileView:
    entries = [Entry.model_validate(entry) for entry in row.entries] if row else []
    availability = [item for item in entries if item.category == "disponibilidad"]
    return ProfileView(
        version=row.version if row else 0,
        author_id=row.author_id if row else None,
        created_at=utc(row.created_at) if row else None,
        availability_status="verificado" if availability and all(
            item.status == "verificado" for item in availability
        ) else "pendiente",
        entries=entries,
    )


@router.get("", response_model=ProfileView)
def get_profile(member: EagMember, session: Database, response: Response) -> ProfileView:
    response.headers["Cache-Control"] = PRIVATE
    return view(current(session, member.membership.organization_id))


@router.get("/versions", response_model=list[VersionSummary])
def history(
    member: EagMember, session: Database, response: Response,
    before: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None,
) -> list[VersionSummary]:
    response.headers["Cache-Control"] = PRIVATE
    org = member.membership.organization_id
    statement = select(ProfileVersion.version, ProfileVersion.author_id, ProfileVersion.created_at)
    statement = statement.where(ProfileVersion.organization_id == org)
    if before is not None:
        statement = statement.where(ProfileVersion.version < before)
    return [
        VersionSummary(version=version, author_id=author_id, created_at=utc(created_at))
        for version, author_id, created_at in session.execute(
            statement.order_by(ProfileVersion.version.desc()).limit(50)
        )
    ]


@router.get("/versions/{version}", response_model=ProfileView)
def get_version(
    version: Annotated[int, Path(ge=1, le=2_147_483_647)],
    member: EagMember, session: Database, response: Response,
) -> ProfileView:
    item = session.get(ProfileVersion, (member.membership.organization_id, version))
    if item is None:
        raise DocumentError(404, "version_no_encontrada")
    response.headers["Cache-Control"] = PRIVATE
    return view(item)


@router.put("", response_model=ProfileView, status_code=201, dependencies=admin_only)
def save_profile(
    administrator: Administrator, session: Database, body: ProfileWrite, response: Response,
) -> ProfileView:
    org = administrator.membership.organization_id
    latest = current(session, org)
    if (latest.version if latest else 0) != body.base_version:
        raise DocumentError(409, "version_desactualizada")
    references = {ref.document_id for entry in body.entries for ref in entry.evidence}
    if references:
        matching = set(session.scalars(select(ProfileEvidence.id).where(
            ProfileEvidence.organization_id == org, ProfileEvidence.id.in_(references),
        )))
        if matching != references:
            raise DocumentError(422, "evidencia_no_disponible")
    item = ProfileVersion(
        organization_id=org, version=body.base_version + 1,
        author_id=administrator.subject_id, created_at=utcnow(),
        entries=[entry.model_dump(mode="json") for entry in body.entries],
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise DocumentError(409, "version_desactualizada") from None
    response.headers["Cache-Control"] = PRIVATE
    return view(item)


async def evidence_payload(request: Request) -> bytes:
    settings = cast(Settings, request.app.state.opportunity_settings)
    return await read_upload(request, settings.document_max_bytes)


@router.post("/evidence", response_model=EvidenceView, status_code=201, dependencies=admin_only)
def upload_evidence(
    administrator: Administrator, session: Database, request: Request, response: Response,
    tools: ServicesDep, payload: Annotated[bytes, Depends(evidence_payload)],
    name: Annotated[str, Header(alias="X-Document-Name", max_length=2400)],
) -> ProfileEvidence:
    org = administrator.membership.organization_id
    digest = sha256(payload).hexdigest()
    lookup = select(ProfileEvidence).where(
        ProfileEvidence.organization_id == org, ProfileEvidence.sha256 == digest,
    )
    filename = filename_from_header(name)
    settings = cast(Settings, request.app.state.opportunity_settings)
    result = inspect_upload(
        payload, settings, tools.scanner, filename=filename,
        media_type=request.headers.get("content-type"),
    )
    if result.quarantined:
        raise DocumentError(503, "antivirus_no_disponible")
    response.headers["Cache-Control"] = PRIVATE
    existing = session.scalar(lookup)
    if existing is not None:
        return existing
    item = ProfileEvidence(
        id=uuid4(), organization_id=org, author_id=administrator.subject_id,
        created_at=utcnow(), filename=filename, sha256=digest, payload=payload,
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(lookup)
        if existing is None:
            raise
        return existing
    return item


@router.get("/evidence/{document_id}", response_class=Response)
def download_evidence(document_id: UUID, member: EagMember, session: Database) -> Response:
    item = session.scalar(select(ProfileEvidence).where(
        ProfileEvidence.id == document_id,
        ProfileEvidence.organization_id == member.membership.organization_id,
    ))
    if item is None:
        raise DocumentError(404, "evidencia_no_disponible")
    return Response(item.payload, media_type="application/octet-stream", headers={
        "Cache-Control": PRIVATE, "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="{item.filename}"',
    })
