"""Registro de auditoría.

Responsabilidad única: escribir eventos sin contenido sensible. La restricción
se aplica aquí, no se confía a quien llama.

Un historial de auditoría que filtra mal es peor que no tenerlo: da apariencia
de control mientras almacena lo que no debe. Por eso las claves prohibidas se
descartan en el propio escritor, en lugar de confiar en que cada llamador se
acuerde de omitirlas.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.db.models import AuditEvent

# Palabras que nunca deben aparecer en el metadata de un evento. La comprobación
# es por subcadena y en minúsculas: así «refresh_token», «Authorization» y
# «service_secret» caen todos.
FORBIDDEN_KEY_PARTS = ("password", "token", "authorization", "refresh", "secret")


class AuditLog:
    """Escribe y consulta el registro de auditoría."""

    def __init__(self, session: DbSession) -> None:
        self._db = session

    def record(
        self,
        action: str,
        *,
        actor_id: int | None = None,
        target_user_id: int | None = None,
        outcome: str = "ok",
        metadata: dict[str, object] | None = None,
    ) -> AuditEvent:
        """Registra un evento, descartando las claves prohibidas."""

        event = AuditEvent(
            action=action,
            actor_id=actor_id,
            target_user_id=target_user_id,
            outcome=outcome,
            metadata_json=self._sanitise(metadata),
        )
        self._db.add(event)
        return event

    @staticmethod
    def _sanitise(metadata: dict[str, object] | None) -> dict[str, object]:
        """Elimina del metadata cualquier clave que pueda contener un secreto."""

        safe: dict[str, object] = {}
        for key, value in (metadata or {}).items():
            if any(part in key.lower() for part in FORBIDDEN_KEY_PARTS):
                continue
            safe[key] = value
        return safe

    def recent(self, *, limit: int = 100) -> list[AuditEvent]:
        """Eventos más recientes, del más nuevo al más antiguo."""

        statement = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
        return list(self._db.execute(statement).scalars().all())
