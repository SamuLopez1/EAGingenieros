"""Persistencia del MVP: modelo, repositorio y sincronización."""

# La importación de `knowledge_models` es necesaria aunque no se use el nombre:
# registra sus tablas en `Base.metadata`. Sin ella, `create_all` no las crea y
# la ingesta falla con "no such table" solo en los entornos que crean el esquema
# desde el modelo en lugar de con Alembic.
from app.db import knowledge_models  # noqa: F401
from app.db.knowledge_models import KnowledgeChunk, KnowledgeDocument, RagQueryLog
from app.db.models import (
    AuditEvent,
    Base,
    Opportunity,
    Session,
    SyncCursor,
    SyncRun,
    User,
)
from app.db.repository import (
    InMemoryOpportunityRepository,
    OpportunityRepository,
    SqlOpportunityRepository,
    SyncOutcome,
    SyncRunTracker,
    UpsertResult,
)
from app.db.sync_service import SyncRequest, SyncService

__all__ = [
    "AuditEvent",
    "Base",
    "InMemoryOpportunityRepository",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "RagQueryLog",
    "Session",
    "User",
    "Opportunity",
    "OpportunityRepository",
    "SqlOpportunityRepository",
    "SyncCursor",
    "SyncOutcome",
    "SyncRequest",
    "SyncRun",
    "SyncRunTracker",
    "SyncService",
    "UpsertResult",
]
