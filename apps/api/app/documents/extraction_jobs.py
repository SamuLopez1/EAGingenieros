"""Cola durable y resultados de extracción vinculados al documento de origen."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Literal, cast
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.document_models import OpportunityDocument, OpportunityDocumentContent
from app.db.extraction_models import DocumentExtraction
from app.db.models import utcnow
from app.documents.extraction import SUPPORTED_MEDIA, Format, Result, failed
from app.documents.service import DocumentError, Dossier, utc

MAX_ATTEMPTS = 2
JobStatus = Literal["sin_extraccion", "pendiente", "procesando", "listo", "revision", "fallido"]
RETRYABLE = frozenset({"tiempo_agotado", "worker_fallido", "limite_memoria"})


class ExtractionView(BaseModel):
    document_id: UUID
    opportunity_id: int
    version: int
    source_sha256: str
    status: JobStatus
    attempts: int
    result: Result | None
    finished_at: datetime | None


def job_for(scope: Dossier, doc: OpportunityDocument) -> DocumentExtraction | None:
    return scope.session.scalar(
        select(DocumentExtraction).where(
            DocumentExtraction.document_id == doc.id,
            DocumentExtraction.opportunity_id == scope.opportunity.id,
            DocumentExtraction.organization_id == scope.organization_id,
            DocumentExtraction.version == doc.version,
            DocumentExtraction.source_sha256 == doc.sha256,
        )
    )


def view(doc: OpportunityDocument, job: DocumentExtraction | None) -> ExtractionView:
    return ExtractionView(
        document_id=doc.id,
        opportunity_id=doc.opportunity_id,
        version=doc.version,
        source_sha256=doc.sha256,
        status=cast(JobStatus, job.status) if job else "sin_extraccion",
        attempts=job.attempts if job else 0,
        result=Result.model_validate(job.result) if job and job.result else None,
        finished_at=utc(job.finished_at) if job and job.finished_at else None,
    )


def enqueue(scope: Dossier, document_id: UUID, *, retry: bool) -> ExtractionView:
    # Serializa altas simultáneas de la misma versión antes del INSERT.
    scope.session.scalar(select(OpportunityDocument.id).where(
        OpportunityDocument.id == document_id,
        OpportunityDocument.opportunity_id == scope.opportunity.id,
        OpportunityDocument.organization_id == scope.organization_id,
    ).with_for_update())
    doc = scope.find(document_id)
    scope.require_ready(doc)
    if doc.media_type not in SUPPORTED_MEDIA:
        raise DocumentError(422, "formato_no_soportado")
    job = job_for(scope, doc)
    now = utcnow()
    if job is None:
        job = DocumentExtraction(
            document_id=doc.id, opportunity_id=doc.opportunity_id,
            organization_id=doc.organization_id, version=doc.version,
            source_sha256=doc.sha256, status="pendiente", attempts=0, queued_at=now,
        )
        scope.session.add(job)
    elif retry and job.status in {"fallido", "revision"}:
        job.status = "pendiente"
        job.attempts = 0
        job.queued_at = now
        job.started_at = None
        job.finished_at = None
        job.result = None
    scope.session.commit()
    return view(doc, job)


@dataclass(frozen=True)
class Claim:
    document_id: UUID
    token: UUID
    format: Format
    payload: bytes


def complete(job: DocumentExtraction, result: Result, *, now: datetime) -> None:
    job.status = result.status
    job.result = result.model_dump(mode="json")
    job.finished_at = now
    job.lease_token = None
    job.lease_until = None


def claim_next(session: Session, *, timeout: int, max_bytes: int) -> tuple[bool, Claim | None]:
    now = utcnow()
    selected = session.execute(
        select(DocumentExtraction, OpportunityDocument)
        .join(OpportunityDocument, OpportunityDocument.id == DocumentExtraction.document_id)
        .where(
            or_(
                DocumentExtraction.status == "pendiente",
                and_(
                    DocumentExtraction.status == "procesando",
                    DocumentExtraction.lease_until <= now,
                ),
            )
        )
        .order_by(DocumentExtraction.queued_at, DocumentExtraction.document_id)
        .limit(1)
        .with_for_update(of=DocumentExtraction, skip_locked=True)
    ).first()
    if selected is None:
        return False, None
    job, doc = selected
    format = SUPPORTED_MEDIA.get(doc.media_type)
    if job.attempts >= MAX_ATTEMPTS:
        complete(job, failed("worker_interrumpido"), now=now)
    elif doc.status != "disponible" or utc(doc.retention_until) <= now:
        complete(job, failed("documento_no_disponible"), now=now)
    elif format is None:
        complete(job, failed("formato_no_soportado"), now=now)
    elif doc.size_bytes > max_bytes:
        complete(job, failed("limite_archivo"), now=now)
    else:
        content = session.get(OpportunityDocumentContent, doc.id)
        if (
            content is not None
            and 0 < len(content.payload) == doc.size_bytes <= max_bytes
            and sha256(content.payload).hexdigest() == job.source_sha256 == doc.sha256
            and job.version == doc.version
            and job.organization_id == doc.organization_id
            and job.opportunity_id == doc.opportunity_id
        ):
            token = uuid4()
            job.status = "procesando"
            job.started_at = now
            job.attempts += 1
            job.lease_until = now + timedelta(seconds=timeout + 30)
            job.lease_token = token
            payload = content.payload
            session.commit()
            return True, Claim(doc.id, token, format, payload)
        complete(job, failed("integridad_documento"), now=now)
    session.commit()
    return True, None


def finish_claim(session: Session, claim: Claim, result: Result) -> None:
    selected = session.execute(
        select(DocumentExtraction, OpportunityDocument)
        .join(OpportunityDocument, OpportunityDocument.id == DocumentExtraction.document_id)
        .where(
            DocumentExtraction.document_id == claim.document_id,
            DocumentExtraction.lease_token == claim.token,
        ).with_for_update(of=DocumentExtraction)
    ).first()
    if selected is None:
        return
    job, doc = selected
    now = utcnow()
    if doc.status != "disponible" or utc(doc.retention_until) <= now:
        complete(job, failed("documento_no_disponible"), now=now)
    elif result.error_code in RETRYABLE and job.attempts < MAX_ATTEMPTS:
        job.status = "pendiente"
        job.queued_at = now
        job.lease_token = None
        job.lease_until = None
    else:
        complete(job, result, now=now)
    session.commit()
