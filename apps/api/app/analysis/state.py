"""Grafo de análisis de una oportunidad.

Convierte los documentos de un proceso en requisitos estructurados con evidencia
verificable, y se detiene antes de cualquier aprobación.

Por qué un grafo y no una secuencia de funciones:

- **El estado sobrevive.** Un análisis de un pliego de 200 páginas puede tardar
  minutos y consumir cuota de IA. Si el proceso muere, el checkpointer permite
  reanudar en el último nodo completado en lugar de repetir todo.
- **La revisión humana es una interrupción, no una pantalla aparte.** El grafo
  se detiene pidiendo aprobación y el estado queda persistido; cuando el analista
  responde, continúa. Sin esto habría que inventar un mecanismo paralelo para
  guardar dónde se quedó.
- **El camino es explícito.** Cada nodo declara qué recibe y qué produce, y el
  recorrido completo queda auditable.

Los nodos son deterministas y sin autonomía: no deciden qué hacer a continuación
ni eligen herramientas. El grafo decide el orden; el modelo solo interpreta texto
dentro de un nodo acotado.

La regla que gobierna cada nodo: **ninguna afirmación sin cita verificada**. Un
requisito cuya cita no se encuentra en el texto fuente se marca para revisión en
lugar de darse por válido (HU-26).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class NodeName(StrEnum):
    """Nombres de los nodos. Se usan como claves en el grafo y en la traza."""

    LOAD = "cargar_documentos"
    EXTRACT = "extraer_requisitos"
    VALIDATE = "validar_citas"
    MATCH = "vincular_evidencia"
    DRAFT = "preparar_borrador"
    AWAIT_REVIEW = "esperar_revision"


class StepStatus(StrEnum):
    PENDING = "pendiente"
    RUNNING = "en_curso"
    DONE = "completado"
    FAILED = "fallido"
    SKIPPED = "omitido"


@dataclass
class RequirementCandidate:
    """Requisito extraído, antes de validar su cita."""

    text: str
    category: str | None = None
    source_document_id: int | None = None
    source_locator: str | None = None
    quote: str | None = None
    confidence: float | None = None


@dataclass
class ValidatedRequirement(RequirementCandidate):
    """Requisito cuya cita se comprobó contra el texto fuente.

    ``citation_verified`` es lo que separa un requisito real de una invención del
    modelo. Un requisito sin cita verificada no puede sustentar un cumplimiento.
    """

    citation_verified: bool = False
    validation_note: str | None = None


@dataclass
class EvidenceMatch:
    """Evidencia empresarial propuesta para un requisito.

    ``state`` usa los cuatro estados del producto. Se propone aquí y lo confirma
    una persona: el grafo nunca aprueba.
    """

    requirement_index: int
    state: str
    evidence_chunk_ids: list[int] = field(default_factory=list)
    rationale: str | None = None


@dataclass
class StepRecord:
    """Traza de un nodo ejecutado."""

    node: str
    status: str
    detail: str | None = None
    duration_ms: int | None = None


@dataclass
class AnalysisState:
    """Estado que viaja por el grafo.

    Es deliberadamente plano y serializable: el checkpointer lo persiste en
    PostgreSQL, y un objeto con referencias a sesiones o clientes no se podría
    guardar ni reanudar.
    """

    # Entrada
    opportunity_id: int
    document_ids: list[int] = field(default_factory=list)
    actor_id: int | None = None

    # Progreso
    current_node: str | None = None
    steps: list[StepRecord] = field(default_factory=list)
    error: str | None = None
    # Cuántas veces se ha reintentado el nodo actual. Evita reintentos infinitos
    # cuando el fallo es del contenido, no de la red.
    attempts: int = 0
    max_attempts: int = 2

    # Resultados
    requirements: list[ValidatedRequirement] = field(default_factory=list)
    matches: list[EvidenceMatch] = field(default_factory=list)
    documents_read: int = 0
    chunks_available: int = 0
    rejected_requirements: int = 0

    # Revisión humana
    awaiting_review: bool = False
    review_reason: str | None = None

    def record(self, node: str, status: str, detail: str | None = None) -> None:
        self.steps.append(StepRecord(node=node, status=str(status), detail=detail))
        self.current_node = node

    @property
    def failed(self) -> bool:
        return self.error is not None

    @property
    def verified_requirements(self) -> list[ValidatedRequirement]:
        return [r for r in self.requirements if r.citation_verified]

    @property
    def unverified_requirements(self) -> list[ValidatedRequirement]:
        return [r for r in self.requirements if not r.citation_verified]


class AnalysisError(RuntimeError):
    """Fallo del análisis que debe quedar visible y ser reanudable."""
