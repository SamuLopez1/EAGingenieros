"""Persistencia del MVP: modelo, repositorio y sincronización."""

from app.db.models import Base, Opportunity, SyncCursor, SyncRun
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
    "Base",
    "InMemoryOpportunityRepository",
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
