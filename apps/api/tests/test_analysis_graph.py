"""Pruebas del grafo de análisis.

El foco está en la validación de citas y en las reglas de decisión, que son
donde el sistema puede producir una afirmación falsa sobre un pliego. Todo
offline: los nodos reciben sus dependencias inyectadas.
"""

from __future__ import annotations

import pytest

from app.analysis.extractors import (
    ModelExtractor,
    RuleBasedExtractor,
    guess_category,
    is_obligation,
    split_sentences,
)
from app.analysis.graph import AnalysisDependencies, build_analysis_graph
from app.analysis.nodes import (
    build_draft_summary,
    decide_state,
    normalise,
    quote_matches,
)
from app.analysis.state import (
    AnalysisState,
    RequirementCandidate,
    ValidatedRequirement,
)
from app.rag.retriever import RetrievedChunk

TEXTO_PLIEGO = (
    "El proponente debe acreditar experiencia minima de cinco (5) anos en "
    "interventoria de obras de infraestructura vial, mediante certificaciones "
    "expedidas por el contratante. "
    "El proponente debe acreditar un patrimonio tecnico igual o superior a dos "
    "mil salarios minimos mensuales vigentes. "
    "Se exige presentar el RUP con fecha de expedicion no mayor a treinta dias."
)


def chunk(
    content: str,
    *,
    score: float = 0.9,
    verified: bool = True,
    expired: bool = False,
    document_id: int = 1,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=1,
        document_id=document_id,
        document_title="Pliego",
        category="oportunidad",
        content=content,
        locator="pág. 1",
        page_number=1,
        section=None,
        score=score,
        is_verified=verified,
        is_expired=expired,
    )


def requirement(
    text: str = "El proponente debe acreditar cinco anos",
    *,
    verified_citation: bool = True,
    quote: str | None = "El proponente debe acreditar cinco anos",
) -> ValidatedRequirement:
    return ValidatedRequirement(
        text=text,
        category="experiencia",
        source_document_id=1,
        source_locator="pág. 1",
        quote=quote,
        citation_verified=verified_citation,
    )


# --- Normalización ---------------------------------------------------------


def test_normalisation_ignores_accents_and_case() -> None:
    """Una cita correcta no debe fallar por una tilde distinta."""

    assert normalise("Experiencia Mínima") == normalise("experiencia minima")


def test_normalisation_joins_hyphenated_line_breaks() -> None:
    """El OCR parte palabras al final de línea: hay que poder encontrarlas."""

    assert "interventoria" in normalise("interven-\ntoria de obra")


def test_normalisation_collapses_whitespace() -> None:
    assert normalise("texto    con   espacios") == "texto con espacios"


# --- Verificación de citas -------------------------------------------------


def test_exact_quote_matches() -> None:
    quote = "El proponente debe acreditar cinco anos de experiencia"

    assert quote_matches(quote, TEXTO_PLIEGO + " " + quote)


def test_quote_with_different_accents_still_matches() -> None:
    fuente = "El proponente debe acreditar experiencia mínima de cinco años"

    assert quote_matches("El proponente debe acreditar experiencia minima de cinco anos", fuente)


def test_quote_with_minor_differences_still_matches() -> None:
    """El modelo puede omitir una palabra; eso no convierte la cita en inventada."""

    quote = "El proponente debe acreditar experiencia minima de cinco (5) anos en interventoria"

    assert quote_matches(quote, TEXTO_PLIEGO)


def test_invented_quote_does_not_match() -> None:
    """El caso que justifica todo el nodo: una cita que no está en el pliego."""

    inventada = (
        "El proponente debe acreditar certificacion ISO 14001 vigente y "
        "experiencia en energia solar fotovoltaica de gran escala"
    )

    assert not quote_matches(inventada, TEXTO_PLIEGO)


def test_very_short_quote_is_not_accepted() -> None:
    """Una cita corta coincidiría por azar en cualquier documento."""

    assert not quote_matches("debe", TEXTO_PLIEGO)


def test_empty_quote_does_not_match() -> None:
    assert not quote_matches("", TEXTO_PLIEGO)


# --- Extracción ------------------------------------------------------------


def test_detects_obligation_phrases() -> None:
    assert is_obligation("El proponente debe acreditar experiencia")
    assert is_obligation("Se exige presentar el RUP")
    assert is_obligation("Es requisito indispensable contar con equipo")


def test_does_not_flag_descriptive_text() -> None:
    assert not is_obligation("El objeto del contrato es la construcción de una vía")


def test_sentences_are_split_by_punctuation() -> None:
    sentences = split_sentences(TEXTO_PLIEGO)

    assert len(sentences) >= 3


def test_extractor_produces_requirements_with_literal_quotes() -> None:
    """La cita debe ser literal del documento: es lo que permite verificarla."""

    extractor = RuleBasedExtractor()
    candidates = extractor([chunk(TEXTO_PLIEGO)])

    assert candidates
    for candidate in candidates:
        assert candidate.quote
        assert candidate.quote in TEXTO_PLIEGO


def test_extractor_guesses_the_category() -> None:
    extractor = RuleBasedExtractor()
    candidates = extractor([chunk(TEXTO_PLIEGO)])

    categorias = {c.category for c in candidates}
    assert "experiencia" in categorias or "financiero" in categorias


def test_extractor_deduplicates_overlapping_chunks() -> None:
    """El solapamiento entre fragmentos repite frases: no deben duplicarse."""

    extractor = RuleBasedExtractor()
    candidates = extractor([chunk(TEXTO_PLIEGO), chunk(TEXTO_PLIEGO)])

    textos = [c.text for c in candidates]
    assert len(textos) == len(set(textos))


def test_extractor_respects_its_limit() -> None:
    extractor = RuleBasedExtractor(max_requirements=1)

    candidates = extractor([chunk(TEXTO_PLIEGO)])

    assert len(candidates) == 1


def test_model_extractor_declares_it_is_not_connected() -> None:
    """Devolver una lista vacía haría creer que el pliego no tiene requisitos."""

    extractor = ModelExtractor(client=object(), model="x")

    with pytest.raises(NotImplementedError):
        extractor([chunk(TEXTO_PLIEGO)])


def test_category_guessing_covers_main_areas() -> None:
    assert guess_category("acreditar patrimonio tecnico") == "financiero"
    assert guess_category("hoja de vida del profesional") == "personal"
    assert guess_category("presentar el RUP vigente") == "legal"
    assert guess_category("texto sin palabras clave") is None


# --- Reglas de decisión ----------------------------------------------------


def test_unverified_citation_leads_to_manual_review() -> None:
    """Sin cita verificable no se puede afirmar nada sobre el requisito."""

    decision = decide_state(
        requirement(verified_citation=False), [chunk(TEXTO_PLIEGO)], threshold=0.25
    )

    assert decision.state == "revision_manual"
    assert "cita verificable" in decision.rationale


def test_no_evidence_leads_to_manual_review_not_non_compliance() -> None:
    """La falta de información no es incumplimiento: son cosas distintas."""

    decision = decide_state(requirement(), [], threshold=0.25)

    assert decision.state == "revision_manual"
    assert decision.state != "no_cumple"
    assert "no implica incumplimiento" in decision.rationale


def test_weak_evidence_leads_to_manual_review() -> None:
    decision = decide_state(
        requirement(), [chunk(TEXTO_PLIEGO, score=0.10)], threshold=0.25
    )

    assert decision.state == "revision_manual"


def test_only_expired_evidence_leads_to_manual_review() -> None:
    """Un certificado vencido no puede sustentar un cumplimiento."""

    decision = decide_state(
        requirement(), [chunk(TEXTO_PLIEGO, expired=True)], threshold=0.25
    )

    assert decision.state == "revision_manual"
    assert "vencida" in decision.rationale


def test_unverified_evidence_leads_to_manual_review() -> None:
    """Adjuntar un documento no garantiza que respalde lo afirmado."""

    decision = decide_state(
        requirement(), [chunk(TEXTO_PLIEGO, verified=False)], threshold=0.25
    )

    assert decision.state == "revision_manual"
    assert "verificada" in decision.rationale or "verificar" in decision.rationale


def test_strong_verified_evidence_proposes_compliance() -> None:
    decision = decide_state(
        requirement(), [chunk(TEXTO_PLIEGO, score=0.85)], threshold=0.25
    )

    assert decision.state == "cumple"
    assert decision.evidence_chunk_ids
    assert "humana" in decision.rationale


def test_proposal_never_claims_final_approval() -> None:
    """El grafo propone; nunca aprueba."""

    decision = decide_state(
        requirement(), [chunk(TEXTO_PLIEGO, score=0.9)], threshold=0.25
    )

    assert "Requiere confirmación humana" in decision.rationale


# --- Grafo completo --------------------------------------------------------


def make_deps(
    *,
    chunks: list[RetrievedChunk] | None = None,
    evidence: list[RetrievedChunk] | None = None,
    extractor=None,  # type: ignore[no-untyped-def]
    explode_on_load: bool = False,
) -> AnalysisDependencies:
    contenido = chunks if chunks is not None else [chunk(TEXTO_PLIEGO)]

    def load(_ids):  # type: ignore[no-untyped-def]
        if explode_on_load:
            raise RuntimeError("base de datos no disponible")
        return contenido

    return AnalysisDependencies(
        load_chunks=load,
        extract_requirements=extractor or RuleBasedExtractor(),
        retrieve_evidence=lambda _q: (
            evidence if evidence is not None else [chunk(TEXTO_PLIEGO, score=0.8)]
        ),
        threshold=0.25,
    )


def run_graph(deps: AnalysisDependencies, state: AnalysisState | None = None):  # type: ignore[no-untyped-def]
    from langgraph.checkpoint.memory import MemorySaver

    graph = build_analysis_graph(deps).compile(checkpointer=MemorySaver())
    initial = state or AnalysisState(opportunity_id=1, document_ids=[1])
    return graph.invoke(
        initial, config={"configurable": {"thread_id": "test"}}, durability="sync"
    )


def test_graph_runs_end_to_end() -> None:
    result = run_graph(make_deps())

    assert result["chunks_available"] > 0
    assert result["requirements"]
    assert result["matches"]
    assert result["awaiting_review"] is True


def test_graph_records_every_step() -> None:
    """La traza permite auditar el recorrido completo."""

    result = run_graph(make_deps())

    nodos = [s.node for s in result["steps"]]
    assert "cargar_documentos" in nodos
    assert "validar_citas" in nodos
    assert "vincular_evidencia" in nodos
    assert "esperar_revision" in nodos


def test_graph_always_ends_awaiting_human_review() -> None:
    """Nada puede avanzar a informe sin aprobación explícita."""

    result = run_graph(make_deps())

    assert result["awaiting_review"] is True
    assert result["review_reason"]


def test_graph_fails_clearly_when_documents_cannot_be_loaded() -> None:
    result = run_graph(make_deps(explode_on_load=True))

    assert result["error"]
    assert "no se pudieron cargar" in result["error"]
    assert not result["requirements"]


def test_graph_fails_when_documents_have_no_text() -> None:
    """Sin texto no hay análisis: declararlo evita un borrador vacío engañoso."""

    result = run_graph(make_deps(chunks=[]))

    assert result["error"]
    assert "no tienen texto" in result["error"]


def test_graph_reports_when_no_requirements_are_found() -> None:
    """La ausencia de requisitos puede ser un fallo, no un hecho."""

    result = run_graph(make_deps(chunks=[chunk("Texto descriptivo sin obligaciones.")]))

    assert result["requirements"] == []
    assert result["review_reason"]
    assert "revisar" in result["review_reason"]


def test_graph_marks_requirements_without_verifiable_citation() -> None:
    """Una cita inventada no puede sustentar un cumplimiento."""

    def extractor_inventado(_chunks):  # type: ignore[no-untyped-def]
        return [
            RequirementCandidate(
                text="Debe acreditar certificacion ISO 14001",
                category="legal",
                source_document_id=1,
                quote="Debe acreditar certificacion ISO 14001 vigente y acreditada",
            )
        ]

    result = run_graph(make_deps(extractor=extractor_inventado))

    assert result["rejected_requirements"] == 1
    assert result["requirements"][0].citation_verified is False
    assert result["matches"][0].state == "revision_manual"


def test_graph_keeps_unverified_requirements_visible() -> None:
    """No se descartan: el analista debe poder verlos y decidir."""

    def extractor_inventado(_chunks):  # type: ignore[no-untyped-def]
        return [
            RequirementCandidate(
                text="Requisito inventado",
                source_document_id=1,
                quote="Una cita que no existe en el documento fuente en absoluto",
            )
        ]

    result = run_graph(make_deps(extractor=extractor_inventado))

    assert len(result["requirements"]) == 1
    assert result["requirements"][0].validation_note


def test_graph_is_resumable_with_a_checkpointer() -> None:
    """El estado persiste: un análisis largo no se repite desde el principio."""

    from langgraph.checkpoint.memory import MemorySaver

    graph = build_analysis_graph(make_deps()).compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "reanudable"}}

    graph.invoke(
        AnalysisState(opportunity_id=1, document_ids=[1]),
        config=config,
        durability="sync",
    )
    snapshot = graph.get_state(config)

    assert snapshot.values["awaiting_review"] is True
    assert snapshot.values["steps"]


# --- Resumen ---------------------------------------------------------------


def test_draft_summary_reports_the_counts() -> None:
    state = AnalysisState(
        opportunity_id=1,
        requirements=[
            requirement(),
            requirement(verified_citation=False),
        ],
        documents_read=1,
        chunks_available=3,
    )
    state.matches = []

    summary = build_draft_summary(state)

    assert "Documentos leídos: 1" in summary
    assert "sin verificar" in summary


def test_draft_summary_warns_about_unverifiable_requirements() -> None:
    state = AnalysisState(
        opportunity_id=1,
        requirements=[requirement(verified_citation=False)],
    )

    summary = build_draft_summary(state)

    assert "no tienen cita verificable" in summary
