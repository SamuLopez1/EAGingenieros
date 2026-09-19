"""Base de conocimiento, indice vectorial y registro de consultas.

Revision ID: 20260918000003
Revises: 20260917000002

Separa el material permanente de la empresa (certificados, contratos, hojas de
vida) del expediente temporal de una oportunidad. Mezclarlos haria que la purga
de 30 dias borrara evidencia empresarial que debe durar, o que un certificado
vencido siguiera sustentando cumplimientos.

Decisiones que se reflejan en el esquema:

  * Cada fragmento guarda el modelo que lo genero. Mezclar vectores de modelos
    distintos en una consulta devuelve resultados sin sentido y sin error
    visible: la distancia entre espacios vectoriales diferentes no significa
    nada. La busqueda filtra por modelo.
  * El indice HNSW se construye con la metrica coseno explicita, porque el
    operador de la consulta debe coincidir con el de construccion o el
    planificador lo ignora.
  * Los documentos se versionan en lugar de sobrescribirse: un analisis ya
    aprobado debe seguir apuntando a la evidencia que uso.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260918000003"
down_revision: str | None = "20260917000002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMENSIONS = 1024


def upgrade() -> None:
    # Extension necesaria para el tipo vectorial. Si ya existe, no falla.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("category", sa.String(length=48), nullable=False),
        sa.Column("original_filename", sa.String(length=300), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("verification_status", sa.String(length=24), nullable=False),
        # Un documento vencido no debe sustentar un cumple.
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("index_status", sa.String(length=16), nullable=False),
        sa.Column("index_error", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("replaced_by_id", sa.BigInteger(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("uploaded_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"], ["knowledge_documents.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_documents_category", "knowledge_documents", ["category"])
    op.create_index("ix_knowledge_documents_is_current", "knowledge_documents", ["is_current"])
    op.create_index("ix_knowledge_documents_hash", "knowledge_documents", ["content_hash"])

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # Localizador verificable: sin el, una cita no se puede comprobar.
        sa.Column("locator", sa.String(length=200), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(length=300), nullable=True),
        sa.Column("token_estimate", sa.Integer(), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_chunk_document_ordinal"),
    )
    op.create_index("ix_knowledge_chunks_document", "knowledge_chunks", ["document_id"])
    op.create_index("ix_knowledge_chunks_model", "knowledge_chunks", ["embedding_model"])
    # Indice aproximado por similitud coseno. HNSW da mejor recall que IVFFlat
    # sin necesidad de entrenar con datos preexistentes.
    op.execute(
        "CREATE INDEX ix_chunk_embedding_hnsw ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )

    op.create_table(
        "rag_query_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("chunks_retrieved", sa.Integer(), nullable=False),
        sa.Column("chunks_used", sa.Integer(), nullable=False),
        sa.Column("had_evidence", sa.Boolean(), nullable=False),
        sa.Column("top_score", sa.Float(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rag_query_log_occurred_at", "rag_query_log", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_rag_query_log_occurred_at", table_name="rag_query_log")
    op.drop_table("rag_query_log")
    op.execute("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw")
    op.drop_index("ix_knowledge_chunks_model", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_document", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_documents_hash", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_is_current", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_category", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
