"""Construcción del grafo de análisis con LangGraph.

El recorrido:

    cargar_documentos → extraer_requisitos → validar_citas → vincular_evidencia
                                                                      ↓
                                                            preparar_borrador
                                                                      ↓
                                                          esperar_revision (interrupción)

La interrupción final no es una pantalla: es el grafo deteniéndose. El estado
queda persistido en PostgreSQL, de modo que la revisión humana puede ocurrir
horas después y el análisis continúa donde se quedó.

Sobre los reintentos: cada nodo puede fallar por dos motivos distintos —la red o
la cuota de IA— y solo esos se reintentan. Un fallo de contenido (un documento
ilegible, una cita imposible) no mejora repitiéndolo, así que agotar reintentos
ahí solo consumiría cuota. El contador está en el estado y el grafo decide.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.analysis.nodes import (
    build_draft_summary,
    decide_state,
    node_validate_citations,
)
from app.analysis.rules import run_rules
from app.analysis.state import (
    AnalysisState,
    EvidenceMatch,
    RequirementCandidate,
    StepStatus,
)
from app.rag.retriever import RetrievedChunk


class AnalysisDependencies:
    """Recursos que los nodos necesitan, inyectados para poder probar sin red.

    Se pasan como un objeto en lugar de como estado del grafo porque no son
    serializables: el checkpointer persiste el estado, y una sesión de base de
    datos o un cliente HTTP no se pueden guardar.

    `company_values` entrega las magnitudes conocidas de la empresa —años de
    experiencia, número de vehículos, patrimonio— para que las condiciones
    objetivas se comparen con aritmética (HU-29) en lugar de por relevancia de
    recuperación. Quien lo implemente decide **qué valores incluye**: si solo
    pasa los verificados por una persona, la seguridad está en el origen y no
    hay que repetir la comprobación en cada nodo.
    """

    def __init__(
        self,
        *,
        load_chunks: Callable[[Sequence[int]], list[RetrievedChunk]],
        extract_requirements: Callable[
            [list[RetrievedChunk]], list[RequirementCandidate]
        ],
        retrieve_evidence: Callable[[str], list[RetrievedChunk]],
        threshold: float = 0.25,
        company_values: Callable[[], dict[str, Decimal]] | None = None,
    ) -> None:
        self.load_chunks = load_chunks
        self.extract_requirements = extract_requirements
        self.retrieve_evidence = retrieve_evidence
        self.threshold = threshold
        self.company_values = company_values or (lambda: {})


def build_analysis_graph(deps: AnalysisDependencies) -> Any:
    """Construye y compila el grafo.

    Devuelve un grafo compilado sin checkpointer. Quien lo use decide la
    persistencia: en pruebas basta la memoria, y en producción el checkpointer de
    PostgreSQL.
    """

    def load_documents(state: AnalysisState) -> dict[str, Any]:
        """Carga los fragmentos de los documentos indicados."""

        try:
            chunks = deps.load_chunks(state.document_ids)
        except Exception as error:  # noqa: BLE001 - el fallo debe quedar en el estado
            return {
                "error": f"no se pudieron cargar los documentos: {type(error).__name__}",
                "steps": [
                    *state.steps,
                    _step("cargar_documentos", StepStatus.FAILED, str(error)),
                ],
            }

        if not chunks:
            # Sin texto no hay nada que analizar. Se declara en lugar de
            # continuar y producir un borrador vacío que parecería un análisis.
            return {
                "chunks_available": 0,
                "documents_read": len(state.document_ids),
                "error": (
                    "los documentos no tienen texto indexado; "
                    "puede requerirse extracción o reindexación"
                ),
                "steps": [
                    *state.steps,
                    _step(
                        "cargar_documentos",
                        StepStatus.FAILED,
                        "ningún documento aportó fragmentos",
                    ),
                ],
            }

        return {
            "chunks_available": len(chunks),
            "documents_read": len({c.document_id for c in chunks}),
            "steps": [
                *state.steps,
                _step(
                    "cargar_documentos",
                    StepStatus.DONE,
                    f"{len(chunks)} fragmentos de "
                    f"{len({c.document_id for c in chunks})} documentos",
                ),
            ],
        }

    def extract_requirements(state: AnalysisState) -> dict[str, Any]:
        """Extrae requisitos del texto de los documentos.

        El extractor se inyecta: hoy puede ser una implementación por reglas y
        mañana una llamada al modelo. El grafo no cambia. Lo que sí es invariante
        es que **cada requisito debe traer su cita textual**: sin ella no se
        puede verificar y quedará en revisión manual.
        """

        chunks = deps.load_chunks(state.document_ids)
        try:
            candidates = deps.extract_requirements(chunks)
        except Exception as error:  # noqa: BLE001
            return {
                "error": f"falló la extracción de requisitos: {type(error).__name__}",
                "steps": [
                    *state.steps,
                    _step("extraer_requisitos", StepStatus.FAILED, str(error)),
                ],
            }

        if not candidates:
            # La ausencia de requisitos no significa que el pliego no tenga
            # ninguno: puede ser un fallo de extracción. Se declara.
            return {
                "requirements": [],
                "review_reason": (
                    "no se extrajo ningún requisito; conviene revisar el documento "
                    "manualmente antes de concluir que no los tiene"
                ),
                "steps": [
                    *state.steps,
                    _step(
                        "extraer_requisitos",
                        StepStatus.DONE,
                        "sin candidatos: requiere revisión humana",
                    ),
                ],
            }

        return {
            "requirements": candidates,
            "steps": [
                *state.steps,
                _step(
                    "extraer_requisitos",
                    StepStatus.DONE,
                    f"{len(candidates)} candidatos",
                ),
            ],
        }

    def validate_citations(state: AnalysisState) -> dict[str, Any]:
        """Verifica que cada cita exista en el texto fuente.

        Es el nodo que impide que una invención del modelo se convierta en una
        afirmación sobre un pliego.
        """

        from app.analysis.state import RequirementCandidate as Candidate

        candidates: list[Candidate] = [
            Candidate(
                text=r.text,
                category=r.category,
                source_document_id=r.source_document_id,
                source_locator=r.source_locator,
                quote=r.quote,
                confidence=r.confidence,
            )
            for r in state.requirements
        ]
        chunks = deps.load_chunks(state.document_ids)
        validated, rejected = node_validate_citations(candidates, chunks)

        return {
            "requirements": validated,
            "rejected_requirements": rejected,
            "steps": [
                *state.steps,
                _step(
                    "validar_citas",
                    StepStatus.DONE,
                    f"{len(validated) - rejected} citas verificadas, {rejected} sin verificar",
                ),
            ],
        }

    def match_evidence(state: AnalysisState) -> dict[str, Any]:
        """Vincula cada requisito con la evidencia empresarial recuperada.

        Las condiciones objetivas se deciden antes y por aritmética; para el
        resto se recupera evidencia semántica. La consulta de recuperación se
        omite cuando una regla ya decidió, porque pedirla sería gastar cuota para
        un resultado que no se va a usar.
        """

        known = deps.company_values()
        matches: list[EvidenceMatch] = []
        por_regla = 0

        for index, requirement in enumerate(state.requirements):
            outcome = run_rules(requirement.text, known=known)
            if outcome is not None:
                # Una condición objetiva con el dato ausente también se decide
                # aquí: dejarla caer a la recuperación reintroduciría el falso
                # cumplimiento por la puerta de atrás.
                por_regla += 1
                matches.append(
                    EvidenceMatch(
                        requirement_index=index,
                        state=outcome.state,
                        rationale=outcome.rationale,
                        evidence_chunk_ids=[],
                        decided_by="regla",
                        rule=outcome.rule,
                        inputs=outcome.inputs,
                    )
                )
                continue

            try:
                evidence = deps.retrieve_evidence(requirement.text)
            except Exception:  # noqa: BLE001 - una consulta fallida no debe abortar
                evidence = []

            decision = decide_state(requirement, evidence, threshold=deps.threshold)
            matches.append(
                EvidenceMatch(
                    requirement_index=index,
                    state=decision.state,
                    evidence_chunk_ids=decision.evidence_chunk_ids,
                    rationale=decision.rationale,
                    decided_by=decision.decided_by,
                    rule=decision.rule,
                    inputs=decision.inputs or {},
                )
            )

        propuestos = sum(1 for m in matches if m.state == "cumple")
        return {
            "matches": matches,
            "steps": [
                *state.steps,
                _step(
                    "vincular_evidencia",
                    StepStatus.DONE,
                    f"{propuestos} propuestas de cumplimiento de {len(matches)} "
                    f"requisitos ({por_regla} por reglas deterministas)",
                ),
            ],
        }

    def prepare_draft(state: AnalysisState) -> dict[str, Any]:
        """Prepara el resumen del borrador. No aprueba nada."""

        summary = build_draft_summary(state)
        return {
            "review_reason": state.review_reason or "borrador preparado para revisión humana",
            "steps": [
                *state.steps,
                _step("preparar_borrador", StepStatus.DONE, summary.splitlines()[0]),
            ],
        }

    def await_review(state: AnalysisState) -> dict[str, Any]:
        """Marca el análisis como pendiente de revisión humana.

        Este nodo no decide: declara que el grafo se detiene aquí y que nada
        puede avanzar a informe sin una aprobación explícita.
        """

        return {
            "awaiting_review": True,
            "steps": [
                *state.steps,
                _step(
                    "esperar_revision",
                    StepStatus.DONE,
                    "el análisis queda pendiente de revisión y aprobación humanas",
                ),
            ],
        }

    def after_load(state: AnalysisState) -> str:
        """Decide si continuar tras cargar los documentos."""

        if state.failed:
            return END
        return "extraer_requisitos"

    def after_extract(state: AnalysisState) -> str:
        if state.failed:
            return END
        return "validar_citas"

    graph = StateGraph(AnalysisState)
    graph.add_node("cargar_documentos", load_documents)
    graph.add_node("extraer_requisitos", extract_requirements)
    graph.add_node("validar_citas", validate_citations)
    graph.add_node("vincular_evidencia", match_evidence)
    graph.add_node("preparar_borrador", prepare_draft)
    graph.add_node("esperar_revision", await_review)

    graph.add_edge(START, "cargar_documentos")
    graph.add_conditional_edges("cargar_documentos", after_load)
    graph.add_conditional_edges("extraer_requisitos", after_extract)
    graph.add_edge("validar_citas", "vincular_evidencia")
    graph.add_edge("vincular_evidencia", "preparar_borrador")
    graph.add_edge("preparar_borrador", "esperar_revision")
    graph.add_edge("esperar_revision", END)

    return graph


def _step(node: str, status: StepStatus, detail: str | None = None):  # type: ignore[no-untyped-def]
    """Construye un registro de la traza."""

    from app.analysis.state import StepRecord

    return StepRecord(node=node, status=str(status), detail=detail)
