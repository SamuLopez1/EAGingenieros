"""Informe y correo sujetos a la aprobación vigente de la comparación."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Annotated, cast
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, Path, Response
from pydantic import Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.comparison_routes import audit_entry, latest, prepare, present
from app.api.document_routes import PRIVATE, DocumentServices, DossierDep, ServicesDep
from app.api.routes import require_eag_administrator, require_eag_member
from app.comparison import Contract
from app.config import Settings
from app.db.models import utcnow
from app.db.report_models import ReportDelivery
from app.documents.service import DocumentError, Dossier, utc
from app.report_mail import Mail, MailGateway, MailState, ResendGateway, normalize_address
from app.report_pdf import ApprovedReport, render

router = APIRouter(
    prefix="/api/v1/opportunities/{opportunity_id}/reports/{revision}",
    tags=["informes"],
    dependencies=[Depends(require_eag_member)],
)
Revision = Annotated[int, Path(ge=1, le=2_147_483_647)]
ADMIN = [Depends(require_eag_administrator)]
MAX_ATTEMPTS = 3
RETRY_WINDOW = timedelta(minutes=15)
LEASE = timedelta(seconds=40)
TERMINAL = {"aceptado", "rechazado", "incierto", "bloqueado"}


class SendRequest(Contract):
    recipient: str = Field(max_length=254)

    @field_validator("recipient")
    @classmethod
    def address(cls, value: str) -> str:
        return normalize_address(value)


class Attempt(Contract):
    actor_id: UUID
    started_at: datetime
    state: MailState
    finished_at: datetime | None = None


class Delivery(Contract):
    id: UUID
    recipient: str
    revision: int
    state: MailState
    provider_id: UUID | None
    updated_at: datetime
    attempts: list[Attempt]


class Outbox(Contract):
    configured: bool
    recipients: list[str]
    deliveries: list[Delivery]


def approved(scope: Dossier, tools: DocumentServices, revision: int) -> ApprovedReport:
    inputs = prepare(scope, tools)
    last = latest(scope)
    if last is None or last.revision != revision or last.action != "aprobado":
        raise DocumentError(409, "aprobacion_no_vigente")
    result = present(scope, inputs, last)
    if result.status != "aprobado":
        raise DocumentError(409, "aprobacion_no_vigente")
    audit = audit_entry(last)
    if audit.outcomes != {row.id: row.outcome for row in result.rows} or {
        doc.id: doc for doc in audit.document_versions
    } != {doc.id: doc for doc in inputs.documents}:
        raise DocumentError(409, "aprobacion_no_vigente")
    op = scope.opportunity
    return ApprovedReport(
        opportunity_id=op.id,
        reference=op.reference or op.source_id,
        title=op.title or "Oportunidad sin título publicado",
        approval=audit,
        analysis=inputs.requirements,
        rows=result.rows,
        expires_at=utc(last.expires_at),
    )


@router.get(
    "",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}
    },
)
def pdf(
    revision: Revision, scope: DossierDep, tools: ServicesDep, download: bool = False
) -> Response:
    scope.lock()
    report = approved(scope, tools, revision)
    try:
        content = render(report, company=scope.settings.company_name)
    except Exception:
        raise DocumentError(422, "informe_no_renderizable") from None
    disposition = "attachment" if download else "inline"
    filename = f"eag-{report.opportunity_id}-r{revision}.pdf"
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Cache-Control": PRIVATE,
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'{disposition}; filename="{filename}"',
        },
    )


def mail_configured(settings: Settings) -> bool:
    return bool(
        settings.report_resend_api_key
        and settings.report_mail_sender
        and settings.report_mail_recipients
        and settings.report_portal_url
    )


def gateway(scope: DossierDep) -> Iterator[MailGateway | None]:
    secret = scope.settings.report_resend_api_key
    if not secret or not mail_configured(scope.settings):
        yield None
        return
    with httpx.Client(
        base_url="https://api.resend.com",
        headers={"Authorization": f"Bearer {secret.get_secret_value()}"},
        timeout=8,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        yield ResendGateway(client)


GatewayDep = Annotated[MailGateway | None, Depends(gateway)]


def delivery_view(item: ReportDelivery) -> Delivery:
    return Delivery(
        id=item.id,
        recipient=item.recipient,
        revision=item.revision,
        state=cast(MailState, item.state),
        provider_id=item.provider_id,
        updated_at=utc(item.updated_at),
        attempts=[Attempt.model_validate(value) for value in item.attempts],
    )


@router.get("/mail", response_model=Outbox, dependencies=ADMIN)
def outbox(revision: Revision, scope: DossierDep, response: Response) -> Outbox:
    settings = scope.settings
    now = utcnow()
    rows = scope.session.scalars(
        select(ReportDelivery)
        .where(
            ReportDelivery.organization_id == scope.organization_id,
            ReportDelivery.opportunity_id == scope.opportunity.id,
            ReportDelivery.revision == revision,
            ReportDelivery.expires_at > now,
        )
        .order_by(ReportDelivery.recipient)
    )
    response.headers["Cache-Control"] = PRIVATE
    return Outbox(
        configured=mail_configured(settings),
        recipients=settings.report_mail_recipients,
        deliveries=[delivery_view(item) for item in rows],
    )


def update_attempt(item: ReportDelivery, state: MailState, now: datetime) -> None:
    attempts = list(item.attempts)
    if attempts and attempts[-1]["state"] == "en_curso":
        attempts[-1] = {**attempts[-1], "state": state, "finished_at": now.isoformat()}
    item.attempts = attempts
    item.state = state
    item.updated_at = now
    item.lease_until = None


def reserve(item: ReportDelivery, scope: Dossier) -> bool:
    now = utcnow()
    if item.state in TERMINAL or (item.lease_until and utc(item.lease_until) > now):
        return False
    if item.state == "en_curso":
        update_attempt(item, "incierto", now)
    if len(item.attempts) >= MAX_ATTEMPTS or utc(item.created_at) + RETRY_WINDOW <= now:
        update_attempt(item, "incierto", now)
        scope.session.commit()
        return False
    item.attempts = [
        *item.attempts,
        Attempt(
            actor_id=scope.principal.subject_id,
            started_at=now,
            state="en_curso",
        ).model_dump(mode="json"),
    ]
    item.state = "en_curso"
    item.updated_at = now
    item.lease_until = now + LEASE
    try:
        scope.session.commit()
    except IntegrityError:
        scope.session.rollback()
        raise DocumentError(409, "envio_en_curso") from None
    return True


@router.post("/mail", response_model=Delivery, dependencies=ADMIN)
def send(
    revision: Revision,
    body: SendRequest,
    scope: DossierDep,
    tools: ServicesDep,
    transport: GatewayDep,
    response: Response,
) -> Delivery:
    settings = scope.settings
    if body.recipient not in settings.report_mail_recipients:
        raise DocumentError(403, "destinatario_no_autorizado")
    scope.lock()
    report = approved(scope, tools, revision)
    key = (scope.organization_id, scope.opportunity.id, revision, body.recipient)
    item = scope.session.get(ReportDelivery, key)
    response.headers["Cache-Control"] = PRIVATE
    if item is not None and item.state in TERMINAL:
        return delivery_view(item)
    sender, portal = settings.report_mail_sender, settings.report_portal_url
    secret = settings.report_resend_api_key
    if transport is None or sender is None or portal is None or not secret:
        raise DocumentError(503, "correo_no_configurado")
    params = urlencode({"opportunity": report.opportunity_id, "report_revision": revision})
    link = f"{portal}?{params}#informe-aprobado"
    credential = sha256(secret.get_secret_value().encode()).hexdigest()
    if item is None:
        now = utcnow()
        item = ReportDelivery(
            organization_id=key[0],
            opportunity_id=key[1],
            revision=revision,
            recipient=body.recipient,
            id=uuid4(),
            sender=sender,
            credential=credential,
            link=link,
            state="reintentar",
            created_at=now,
            updated_at=now,
            expires_at=report.expires_at,
            attempts=[],
        )
        scope.session.add(item)
    elif item.sender != sender or item.link != link or item.credential != credential:
        raise DocumentError(409, "configuracion_envio_cambio")
    if not reserve(item, scope):
        return delivery_view(item)

    # La reserva durable precede a la petición externa. Recomprueba la versión
    # después de confirmarla y serializa el envío con las mutaciones del expediente.
    reservation = len(item.attempts)
    scope.session.expire_all()
    scope.lock()
    if item.state != "en_curso" or len(item.attempts) != reservation:
        return delivery_view(item)
    try:
        approved(scope, tools, revision)
    except DocumentError:
        update_attempt(item, "bloqueado", utcnow())
        scope.session.commit()
        raise
    if utc(item.created_at) + RETRY_WINDOW <= utcnow():
        update_attempt(item, "incierto", utcnow())
    else:
        mail = Mail(item.sender, item.recipient, item.link, settings.company_name)
        outcome = transport.send(mail, f"report/{item.id}")
        state: MailState = outcome.state
        if (state == "reintentar" and len(item.attempts) >= MAX_ATTEMPTS) or (
            state == "rechazado" and len(item.attempts) > 1
        ):
            state = "incierto"
        update_attempt(item, state, utcnow())
        item.provider_id = outcome.provider_id
    scope.session.commit()
    return delivery_view(item)
