"""Validación, versiones y autorización privada de documentos."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import compare_digest, digest
from pathlib import Path
from time import time
from typing import Literal
from urllib.parse import unquote
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.orm import Session

from app.auth import Principal
from app.config import Settings
from app.db.document_models import OpportunityDocument, OpportunityDocumentContent
from app.db.models import Opportunity, utcnow
from app.documents.official import DocumentKind, OfficialReference
from app.documents.validation import (
    ALLOWED_CONTENT_TYPES,
    AntivirusScanner,
    QuarantineReason,
    ValidationResult,
    safe_filename,
    validate_upload,
)

Origin = Literal["manual", "oficial"]
TICKET_TTL = 60


class DocumentError(ValueError):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def filename_from_header(value: str) -> str:
    try:
        name = unquote(value, errors="strict").strip()
    except ValueError:
        raise DocumentError(422, "nombre_inseguro") from None
    if (
        len(name) > 200
        or not name
        or name in {".", ".."}
        or any(char in name for char in ("/", "\\", ":"))
        or not name.isprintable()
    ):
        raise DocumentError(422, "nombre_inseguro")
    sanitized = safe_filename(name)
    if not sanitized:
        raise DocumentError(422, "nombre_inseguro")
    return sanitized


def title_from_header(value: str) -> str:
    try:
        title = " ".join(unquote(value, errors="strict").split())
    except ValueError:
        raise DocumentError(422, "titulo_invalido") from None
    if not title or len(title) > 140 or not title.isprintable():
        raise DocumentError(422, "titulo_invalido")
    return title


@dataclass(frozen=True)
class IncomingDocument:
    kind: DocumentKind
    title: str
    filename: str
    data: bytes
    media_type: str | None
    official: OfficialReference | None = None

    @property
    def origin(self) -> Origin:
        return "oficial" if self.official else "manual"

    @property
    def key(self) -> str:
        identity = self.official.source_record_id if self.official else self.title.casefold()
        # Hash de identidad para mantener el índice acotado incluso con caracteres Unicode.
        return f"{self.origin}:{self.kind}:{sha256(identity.encode()).hexdigest()}"


def inspect_upload(
    data: bytes, settings: Settings, scanner: AntivirusScanner | None,
    *, filename: str, media_type: str | None,
) -> ValidationResult:
    if data.startswith(b"%PDF-") and b"%%EOF" not in data[-2048:]:
        raise DocumentError(422, "archivo_corrupto")
    result = validate_upload(
        data,
        filename=filename,
        declared_content_type=media_type,
        max_bytes=settings.document_max_bytes,
        scanner=scanner,
        require_antivirus=True,
    )
    if result.reason == QuarantineReason.TOO_LARGE:
        raise DocumentError(413, result.reason.value)
    if result.reason is not None and result.reason != QuarantineReason.ANTIVIRUS_UNAVAILABLE:
        raise DocumentError(422, result.reason.value)
    extension = Path(filename).suffix.lower()
    if ALLOWED_CONTENT_TYPES.get(result.detected_type or "") != extension:
        raise DocumentError(422, "tipo_no_coincide")
    return result


@dataclass(frozen=True)
class Dossier:
    session: Session
    opportunity: Opportunity
    principal: Principal
    settings: Settings

    @property
    def organization_id(self) -> UUID:
        return self.principal.membership.organization_id

    def items(self) -> list[OpportunityDocument]:
        return list(self.session.scalars(
            select(OpportunityDocument)
            .where(*self._scope())
            .order_by(OpportunityDocument.uploaded_at.desc(), OpportunityDocument.id)
        ))

    def _scope(self) -> tuple[ColumnElement[bool], ...]:
        return (
            OpportunityDocument.opportunity_id == self.opportunity.id,
            OpportunityDocument.organization_id == self.organization_id,
        )

    def _lock(self) -> None:
        found = self.session.scalar(
            select(Opportunity.id).where(Opportunity.id == self.opportunity.id).with_for_update()
        )
        if found is None:
            raise DocumentError(404, "oportunidad_no_encontrada")

    def find(self, document_id: UUID) -> OpportunityDocument:
        found = self.session.scalar(
            select(OpportunityDocument)
            .where(*self._scope(), OpportunityDocument.id == document_id)
        )
        if found is None:
            raise DocumentError(404, "documento_no_encontrado")
        return found

    def save(
        self, upload: IncomingDocument, scanner: AntivirusScanner | None,
    ) -> OpportunityDocument:
        inspected = inspect_upload(
            upload.data, self.settings, scanner,
            filename=upload.filename, media_type=upload.media_type,
        )
        status = "disponible" if inspected.accepted and inspected.scanned else "cuarentena"
        checksum = sha256(upload.data).hexdigest()
        now = utcnow()
        self._lock()
        latest = self.session.scalar(
            select(OpportunityDocument).where(*self._scope(),
                OpportunityDocument.document_key == upload.key)
            .order_by(OpportunityDocument.version.desc()).limit(1)
        )
        if (
            latest and latest.status != "rechazado" and latest.sha256 == checksum
            and utc(latest.retention_until) > now
        ):
            if latest.status == "cuarentena" and status == "disponible":
                latest.status = status
            self.session.commit()
            return latest
        retained = self.session.scalar(
            select(func.coalesce(func.sum(OpportunityDocument.size_bytes), 0))
            .join(OpportunityDocumentContent)
            .where(*self._scope())
        )
        if (retained or 0) + len(upload.data) > self.settings.dossier_max_bytes:
            raise DocumentError(413, "cuota_expediente")
        source = upload.official
        doc = OpportunityDocument(
            id=uuid4(),
            organization_id=self.organization_id, opportunity_id=self.opportunity.id,
            uploaded_by=self.principal.subject_id, document_key=upload.key,
            title=upload.title, kind=upload.kind, filename=upload.filename, origin=upload.origin,
            source_record_id=source.source_record_id if source else None,
            source_url=source.url if source else None,
            source_verified_at=source.verified_at if source else None,
            source_evidence=source.evidence if source else None,
            version=latest.version + 1 if latest else 1, sha256=checksum,
            size_bytes=len(upload.data), media_type=inspected.detected_type, status=status,
            under_review=False, uploaded_at=now,
            retention_until=now + timedelta(days=self.settings.document_retention_days),
        )
        self.session.add(doc)
        self.session.flush()
        self.session.add(OpportunityDocumentContent(document_id=doc.id, payload=upload.data))
        self.session.commit()
        return doc

    def mark_review(self, document_id: UUID) -> OpportunityDocument:
        self._lock()
        doc = self.find(document_id)
        self.require_ready(doc)
        self.session.execute(
            update(OpportunityDocument)
            .where(*self._scope(), OpportunityDocument.document_key == doc.document_key)
            .values(under_review=False)
        )
        doc.under_review = True
        self.session.commit()
        return doc

    def rescan(self, document_id: UUID, scanner: AntivirusScanner | None) -> OpportunityDocument:
        self._lock()
        doc = self.find(document_id)
        if doc.status != "cuarentena" or utc(doc.retention_until) <= utcnow():
            raise DocumentError(409, "documento_no_en_cuarentena")
        content = self.session.get(OpportunityDocumentContent, doc.id)
        if content is None:
            raise DocumentError(404, "documento_no_encontrado")
        result = validate_upload(
            content.payload, filename=doc.filename, declared_content_type=doc.media_type,
            max_bytes=self.settings.document_max_bytes, scanner=scanner, require_antivirus=True,
        )
        if result.accepted and result.scanned:
            doc.status = "disponible"
        elif result.reason != QuarantineReason.ANTIVIRUS_UNAVAILABLE:
            doc.status = "rechazado"
            self.session.delete(content)
        self.session.commit()
        return doc

    @staticmethod
    def require_ready(doc: OpportunityDocument) -> None:
        if utc(doc.retention_until) <= utcnow():
            raise DocumentError(410, "documento_vencido")
        if doc.status != "disponible":
            raise DocumentError(409, "documento_no_disponible")

    def _signature(self, document_id: UUID, expiration: int) -> str:
        secret = self.settings.document_download_secret
        if secret is None:
            raise DocumentError(503, "firma_no_configurada")
        claims = (
            f"{self.organization_id}:{self.principal.subject_id}:"
            f"{self.opportunity.id}:{document_id}:{expiration}"
        )
        return digest(secret.get_secret_value().encode(), claims.encode(), "sha256").hex()

    def ticket(self, doc: OpportunityDocument) -> str:
        self.require_ready(doc)
        expiration = int(time()) + TICKET_TTL
        return f"{expiration}.{self._signature(doc.id, expiration)}"

    def content(self, doc: OpportunityDocument, ticket: str) -> bytes:
        expires, separator, signature = ticket.partition(".")
        if not separator or len(expires) > 12 or not expires.isascii() or not expires.isdecimal():
            raise DocumentError(403, "firma_invalida")
        expiration = int(expires)
        now = int(time())
        if (
            not now < expiration <= now + TICKET_TTL
            or len(signature) != 64
            or not signature.isascii()
            or not compare_digest(signature, self._signature(doc.id, expiration))
        ):
            raise DocumentError(403, "firma_invalida")
        self.require_ready(doc)
        content = self.session.get(OpportunityDocumentContent, doc.id)
        if content is None:
            raise DocumentError(404, "documento_no_encontrado")
        return content.payload
