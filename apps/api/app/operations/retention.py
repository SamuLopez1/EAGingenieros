"""Purga por vencimiento y restauración con un registro externo autenticado."""

import argparse
import hashlib
import hmac
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.comparison_models import ComparisonRevision, DossierRevision
from app.db.document_models import OpportunityDocument
from app.db.extraction_models import DocumentExtraction
from app.db.margin_models import MarginVersion
from app.db.models import Opportunity
from app.db.report_models import ReportDelivery
from app.db.retention_models import RetentionTombstone
from app.db.session import create_engine_from_url
from app.db.staffing_models import StaffingCorrection
from app.documents.service import utc
from app.operations.scratch import sweep

Kind = Literal["document", "comparison", "delivery", "margin"]
MAX_LEDGER_BYTES = 8_000_000
BATCH = 250
LOCK = 13132026


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    kind: Kind
    organization_id: UUID
    opportunity_id: int = Field(gt=0)
    object_id: UUID | None = None
    revision: int | None = Field(default=None, gt=0)
    purged_at: AwareDatetime

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.kind == "comparison":
            if self.revision is None or self.object_id is not None:
                raise ValueError("Referencia de comparación inválida.")
        elif self.kind == "margin":
            if self.object_id is None or self.revision is None:
                raise ValueError("Referencia de margen inválida.")
        elif self.object_id is None or self.revision is not None:
            raise ValueError("Referencia de objeto inválida.")
        return self

    @property
    def key(self) -> str:
        identity = f"{self.organization_id}/{self.opportunity_id}"
        if self.kind == "margin":
            return f"{self.kind}/{identity}/{self.object_id}/{self.revision}"
        return f"{self.kind}/{identity}/{self.revision or self.object_id}"


class Ledger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal[1] = 1
    environment_id: UUID
    records: list[Record]


class SignedLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ledger: Ledger
    signature: str = Field(pattern="^[a-f0-9]{64}$")


def signature(value: Ledger, secret: bytes) -> str:
    return hmac.new(secret, value.model_dump_json().encode(), hashlib.sha256).hexdigest()


def read_ledger(path: Path, key: bytes, environment: UUID) -> dict[str, Record]:
    if not path.exists() and not path.is_symlink():
        raise FileNotFoundError("Falta el registro externo de purgas.")
    if (
        path.is_symlink()
        or path.is_junction()
        or not path.is_file()
        or path.stat().st_size > MAX_LEDGER_BYTES
    ):
        raise ValueError("Archivo de registro inválido.")
    signed = SignedLedger.model_validate_json(path.read_bytes())
    if signed.ledger.environment_id != environment or not hmac.compare_digest(
        signed.signature,
        signature(signed.ledger, key),
    ):
        raise ValueError("Ambiente o firma del registro inválidos.")
    entries = {event.key: event for event in signed.ledger.records}
    if len(entries) != len(signed.ledger.records):
        raise ValueError("El registro tiene referencias repetidas.")
    return entries


def write_ledger(path: Path, key: bytes, environment: UUID, records: dict[str, Record]) -> None:
    value = Ledger(environment_id=environment, records=[records[name] for name in sorted(records)])
    encoded = SignedLedger(ledger=value, signature=signature(value, key)).model_dump_json().encode()
    if len(encoded) > MAX_LEDGER_BYTES:
        raise ValueError("El registro alcanzó su límite. Escalar a Operación.")
    if path.is_symlink() or path.is_junction():
        raise ValueError("Ruta de registro inválida.")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, mode="wb", delete=False) as file:
            temporary = Path(file.name)
            file.write(encoded)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
        if os.name == "posix":
            parent = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def candidates(session: Session, now: datetime) -> list[Record]:
    docs = session.execute(
        select(
            OpportunityDocument.organization_id,
            OpportunityDocument.opportunity_id,
            OpportunityDocument.id,
        )
        .where(OpportunityDocument.retention_until <= now)
        .order_by(OpportunityDocument.retention_until, OpportunityDocument.id)
        .limit(BATCH)
    )
    comparisons = session.execute(
        select(
            ComparisonRevision.organization_id,
            ComparisonRevision.opportunity_id,
            ComparisonRevision.revision,
        )
        .where(ComparisonRevision.expires_at <= now)
        .order_by(
            ComparisonRevision.expires_at,
            ComparisonRevision.opportunity_id,
            ComparisonRevision.revision,
        )
        .limit(BATCH)
    )
    deliveries = session.execute(
        select(
            ReportDelivery.organization_id,
            ReportDelivery.opportunity_id,
            ReportDelivery.id,
        )
        .where(ReportDelivery.expires_at <= now)
        .order_by(ReportDelivery.expires_at, ReportDelivery.id)
        .limit(BATCH)
    )
    margins = session.execute(
        select(
            MarginVersion.organization_id, MarginVersion.opportunity_id,
            MarginVersion.scenario_id, MarginVersion.version,
        )
        .where(MarginVersion.expires_at <= now)
        .order_by(MarginVersion.expires_at, MarginVersion.scenario_id, MarginVersion.version)
        .limit(BATCH)
    )
    return [
        *(
            Record(
                kind="margin", organization_id=org, opportunity_id=op,
                object_id=scenario, revision=version, purged_at=now,
            )
            for org, op, scenario, version in margins
        ),
        *(
            Record(
                kind="document",
                organization_id=org,
                opportunity_id=op,
                object_id=identity,
                purged_at=now,
            )
            for org, op, identity in docs
        ),
        *(
            Record(
                kind="comparison",
                organization_id=org,
                opportunity_id=op,
                revision=revision,
                purged_at=now,
            )
            for org, op, revision in comparisons
        ),
        *(
            Record(
                kind="delivery",
                organization_id=org,
                opportunity_id=op,
                object_id=identity,
                purged_at=now,
            )
            for org, op, identity in deliveries
        ),
    ]


def database_ledger(session: Session) -> dict[str, Record]:
    return {
        item.key: Record.model_validate(
            {
                "kind": item.kind,
                "organization_id": item.organization_id,
                "opportunity_id": item.opportunity_id,
                "object_id": item.object_id,
                "revision": item.revision,
                "purged_at": utc(item.purged_at),
            }
        )
        for item in session.scalars(select(RetentionTombstone))
    }


def serialize(session: Session) -> None:
    if session.get_bind().dialect.name == "postgresql":
        result = session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": LOCK})
        if not result:
            raise RuntimeError("Otra tarea de retención está activa.")


def delete_target(session: Session, item: Record) -> bool:
    org, opportunity_id = item.organization_id, item.opportunity_id
    if item.kind == "document":
        ids = session.execute(
            delete(OpportunityDocument)
            .where(
                OpportunityDocument.organization_id == org,
                OpportunityDocument.opportunity_id == opportunity_id,
                OpportunityDocument.id == item.object_id,
            )
            .returning(OpportunityDocument.id)
        )
        return ids.first() is not None
    if item.kind == "margin":
        ids = session.execute(
            delete(MarginVersion).where(
                MarginVersion.organization_id == org,
                MarginVersion.opportunity_id == opportunity_id,
                MarginVersion.scenario_id == item.object_id,
                MarginVersion.version == item.revision,
            ).returning(MarginVersion.scenario_id)
        )
        return ids.first() is not None
    if item.kind == "comparison":
        session.execute(delete(StaffingCorrection).where(
            StaffingCorrection.organization_id == org,
            StaffingCorrection.opportunity_id == opportunity_id,
            StaffingCorrection.comparison_revision == item.revision,
        ))
        ids = session.execute(
            delete(ComparisonRevision)
            .where(
                ComparisonRevision.organization_id == org,
                ComparisonRevision.opportunity_id == opportunity_id,
                ComparisonRevision.revision == item.revision,
            )
            .returning(ComparisonRevision.revision)
        )
        return ids.first() is not None
    ids = session.execute(
        delete(ReportDelivery)
        .where(
            ReportDelivery.organization_id == org,
            ReportDelivery.opportunity_id == opportunity_id,
            ReportDelivery.id == item.object_id,
        )
        .returning(ReportDelivery.id)
    )
    return ids.first() is not None


def apply(
    session: Session,
    records: list[Record],
    known: dict[str, Record],
) -> dict[str, int]:
    # Las mutaciones de expediente, comparación y correo usan el mismo cerrojo de oportunidad.
    opportunity_ids = sorted({item.opportunity_id for item in records})
    for offset in range(0, len(opportunity_ids), BATCH):
        session.execute(
            select(Opportunity.id)
            .where(
                Opportunity.id.in_(opportunity_ids[offset : offset + BATCH]),
            )
            .order_by(Opportunity.id)
            .with_for_update()
        ).all()
    counts: Counter[str] = Counter()
    changed: set[tuple[UUID, int]] = set()
    for item in records:
        if item.key not in known:
            session.add(RetentionTombstone(key=item.key, **item.model_dump()))
        if delete_target(session, item):
            counts[item.kind] += 1
            if item.kind == "document":
                changed.add((item.organization_id, item.opportunity_id))
    for org, opportunity_id in sorted(changed):
        epoch = session.get(DossierRevision, (org, opportunity_id))
        if epoch is None:
            session.add(
                DossierRevision(
                    organization_id=org,
                    opportunity_id=opportunity_id,
                    revision=1,
                )
            )
        else:
            epoch.revision += 1
    return dict(counts)


def purge(
    session: Session,
    now: datetime,
    path: Path,
    key: bytes,
    environment: UUID,
) -> dict[str, int]:
    serialize(session)
    known = database_ledger(session)
    if path.exists() or path.is_symlink():
        external = read_ledger(path, key, environment)
    elif known:
        raise ValueError("Falta el registro externo de purgas.")
    else:
        external = {}
    if set(external) - set(known):
        raise ValueError("Reaplica el registro externo antes de purgar.")
    expired = candidates(session, now)
    merged = {**external, **known, **{event.key: event for event in expired}}
    # Primero protege los identificadores en el medio independiente. Un fallo
    # posterior al fsync deja referencias pendientes de reaplicación, no perdidas.
    write_ledger(path, key, environment, merged)
    return apply(session, expired, known)


def replay(session: Session, path: Path, key: bytes, environment: UUID) -> dict[str, int]:
    serialize(session)
    external = read_ledger(path, key, environment)
    known = database_ledger(session)
    if set(known) - set(external):
        raise ValueError("El registro externo es anterior a las purgas de la base.")
    return apply(session, list(external.values()), known)


def overview(session: Session, now: datetime) -> dict[str, int]:
    return {
        "documentos_vencidos": session.scalar(
            select(func.count())
            .select_from(
                OpportunityDocument,
            )
            .where(OpportunityDocument.retention_until <= now)
        )
        or 0,
        "comparaciones_vencidas": session.scalar(
            select(func.count())
            .select_from(
                ComparisonRevision,
            )
            .where(ComparisonRevision.expires_at <= now)
        )
        or 0,
        "envios_vencidos": session.scalar(
            select(func.count())
            .select_from(
                ReportDelivery,
            )
            .where(ReportDelivery.expires_at <= now)
        )
        or 0,
        "margenes_vencidos": session.scalar(
            select(func.count()).select_from(MarginVersion).where(MarginVersion.expires_at <= now)
        )
        or 0,
        "extracciones_fallidas": session.scalar(
            select(func.count())
            .select_from(
                DocumentExtraction,
            )
            .where(DocumentExtraction.status == "fallido")
        )
        or 0,
        "extracciones_con_reserva_vencida": session.scalar(
            select(func.count())
            .select_from(
                DocumentExtraction,
            )
            .where(DocumentExtraction.status == "procesando", DocumentExtraction.lease_until <= now)
        )
        or 0,
        "envios_por_conciliar": session.scalar(
            select(func.count())
            .select_from(
                ReportDelivery,
            )
            .where(
                or_(
                    ReportDelivery.state.in_(("incierto", "reintentar")),
                    and_(ReportDelivery.state == "en_curso", ReportDelivery.lease_until <= now),
                )
            )
        )
        or 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["dry-run", "purge", "replay"])
    parser.add_argument("--ledger", type=Path)
    args = parser.parse_args()
    try:
        settings = Settings()
        key, identity = settings.retention_ledger_secret, settings.retention_ledger_id
        if args.action != "dry-run" and (not key or not identity or args.ledger is None):
            parser.error("Configura la identidad, clave y ruta externa del registro.")
        now = datetime.now(UTC)
        engine = create_engine_from_url(settings.require_database_url())
        try:
            with Session(engine) as session, session.begin():
                if args.action == "dry-run":
                    result = overview(session, now)
                else:
                    assert key is not None and identity is not None and args.ledger is not None
                    secret = key.get_secret_value().encode()
                    if args.action == "purge":
                        result = purge(session, now, args.ledger, secret, identity)
                    else:
                        result = replay(session, args.ledger, secret, identity)
        finally:
            engine.dispose()
        if settings.extraction_scratch_root is not None:
            result["temporales"] = sweep(
                settings.extraction_scratch_root,
                now,
                remove=args.action != "dry-run",
            )
        print(json.dumps({"action": args.action, "counts": result}, sort_keys=True))
        return 0
    except Exception:
        # Excepciones SQL/validación pueden incluir URL, rutas o identificadores.
        print(
            "retencion: operación detenida. Revisa configuración y estado del registro.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
