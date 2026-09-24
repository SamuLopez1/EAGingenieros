"""Persistencia del MVP: modelo, repositorio y sincronización."""

# Estas importaciones son necesarias aunque no se usen los nombres: registran sus
# tablas en `Base.metadata`. Sin ellas, `create_all` no las crea y las consultas
# fallan con "no such table" solo en los entornos que construyen el esquema desde
# el modelo en lugar de con Alembic —es decir, en las pruebas y no en producción,
# que es la peor combinación posible—. `profile_models` faltaba aquí y solo se
# registraba de rebote, al importar el servicio de perfil.
from app.db import (  # noqa: F401
    ai_models,
    analysis_models,
    knowledge_models,
    profile_models,
)
from app.db.ai_models import AiCache, AiUsage
from app.db.analysis_models import (
    AnalysisApproval,
    AnalysisMatch,
    AnalysisRequirement,
    AnalysisReview,
    AnalysisRun,
)
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
    "AiCache",
    "AiUsage",
    "AnalysisApproval",
    "AnalysisMatch",
    "AnalysisRequirement",
    "AnalysisReview",
    "AnalysisRun",
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
