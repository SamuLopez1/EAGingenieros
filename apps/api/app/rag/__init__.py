"""Recuperación aumentada sobre la base de conocimiento de la empresa."""

from app.rag.answering import (
    NO_EVIDENCE_MESSAGE,
    RagAnswer,
    SupportedClaim,
    assemble_answer,
    build_prompt,
    detect_embedded_instructions,
    parse_and_verify,
)
from app.rag.chunking import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP, Chunk, chunk_text
from app.rag.ingestion import (
    IngestionError,
    IngestionOutcome,
    IngestionService,
    content_hash,
)
from app.rag.retriever import (
    Embedder,
    KnowledgeUnavailableError,
    RetrievalResult,
    RetrievedChunk,
    Retriever,
)

__all__ = [
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_OVERLAP",
    "NO_EVIDENCE_MESSAGE",
    "Chunk",
    "Embedder",
    "IngestionError",
    "IngestionOutcome",
    "IngestionService",
    "content_hash",
    "KnowledgeUnavailableError",
    "RagAnswer",
    "RetrievalResult",
    "RetrievedChunk",
    "Retriever",
    "SupportedClaim",
    "assemble_answer",
    "build_prompt",
    "chunk_text",
    "detect_embedded_instructions",
    "parse_and_verify",
]
