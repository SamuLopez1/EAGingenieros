"""Cliente del conjunto público de procesos de SECOP II."""

from app.secop.client import (
    DEFAULT_ORDER,
    PROCESSES_DATASET,
    InvalidFilterError,
    OpportunityRecord,
    QuotaExceededError,
    ResponseShapeError,
    SecopClient,
    SecopError,
    SyncPage,
    UpstreamUnavailableError,
    deduplicate,
    normalise_record,
    parse_timestamp,
)

__all__ = [
    "DEFAULT_ORDER",
    "PROCESSES_DATASET",
    "InvalidFilterError",
    "OpportunityRecord",
    "QuotaExceededError",
    "ResponseShapeError",
    "SecopClient",
    "SecopError",
    "SyncPage",
    "UpstreamUnavailableError",
    "deduplicate",
    "normalise_record",
    "parse_timestamp",
]
