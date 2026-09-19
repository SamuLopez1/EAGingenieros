"""Nodos del grafo de análisis.

Cada nodo es determinista y acotado: recibe el estado, hace una cosa y devuelve
el estado actualizado. Ninguno decide a dónde ir después —eso lo hace el grafo—
ni elige qué herramienta usar.

El nodo que justifica todo el diseño es `validate_citations`: comprueba que el
fragmento citado existe realmente en el texto fuente. Sin él, el sistema podría
afirmar que un pliego exige algo que nunca dijo, y la cita daría apariencia de
rigor a una invención. En contratación pública eso tiene consecuencias legales.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from app.analysis.state import (
    AnalysisState,
    RequirementCandidate,
    ValidatedRequirement,
)
from app.rag.retriever import RetrievedChunk

# Longitud mínima de una cita para poder verificarla. Por debajo, la coincidencia
# sería accidental: cualquier palabra aparece en cualquier documento.
MIN_QUOTE_LENGTH = 24

# Proporción mínima de palabras de la cita que deben aparecer en el fragmento.
# No se exige coincidencia exacta porque el OCR introduce erratas y el modelo
# puede normalizar espacios o tildes al copiar.
MIN_QUOTE_MATCH_RATIO = 0.75


def normalise(text: str) -> str:
    """Normaliza texto para comparar citas contra la fuente.

    Se eliminan tildes, se unifica el espaciado y se pasa a minúsculas. Sin esto,
    una cita correcta fallaría la verificación por una diferencia de acento o por
    un salto de línea, y el sistema marcaría como inventado un requisito real.

    Los guiones de partición de palabra del OCR se tratan aparte: un texto
    escaneado parte palabras al final de línea («interven-\\ntoría»), y esa
    palabra debe poder encontrarse.
    """

    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    # Unir palabras partidas por guion al final de línea, típico de OCR.
    joined = re.sub(r"-\s*\n\s*", "", without_accents)
    collapsed = re.sub(r"\s+", " ", joined)
    return collapsed.lower().strip()


def quote_matches(quote: str, source_text: str) -> bool:
    """Comprueba si una cita aparece en el texto fuente.

    Se compara por proporción de palabras en orden, no por igualdad exacta: el
    modelo puede omitir una palabra o cambiar un espacio, y eso no convierte la
    cita en inventada.
    """

    clean_quote = normalise(quote)
    if len(clean_quote) < MIN_QUOTE_LENGTH:
        return False

    words = [w for w in clean_quote.split() if len(w) > 2]
    if not words:
        return False

    haystack = normalise(source_text)
    found = sum(1 for word in words if word in haystack)
    return (found / len(words)) >= MIN_QUOTE_MATCH_RATIO


def node_validate_citations(
    candidates: Sequence[RequirementCandidate],
    chunks: Sequence[RetrievedChunk],
) -> tuple[list[ValidatedRequirement], int]:
    """Valida cada requisito contra los fragmentos realmente recuperados.

    Devuelve los requisitos validados y cuántos se rechazaron. Un requisito cuya
    cita no se encuentra queda marcado como no verificado, no se descarta: el
    analista debe poder verlo y decidir, porque puede ser un fallo del OCR o del
    extractor, no del modelo.
    """

    by_document: dict[int, str] = {}
    for chunk in chunks:
        by_document.setdefault(chunk.document_id, "")
        by_document[chunk.document_id] += f"\n{chunk.content}"

    validated: list[ValidatedRequirement] = []
    rejected = 0

    for candidate in candidates:
        quote = candidate.quote or ""
        source = by_document.get(candidate.source_document_id or -1, "")

        if not quote.strip():
            validated.append(
                ValidatedRequirement(
                    **{**candidate.__dict__},
                    citation_verified=False,
                    validation_note="el requisito no incluye cita textual",
                )
            )
            rejected += 1
            continue

        if not source:
            validated.append(
                ValidatedRequirement(
                    **{**candidate.__dict__},
                    citation_verified=False,
                    validation_note=(
                        "no hay texto del documento citado entre los fragmentos recuperados"
                    ),
                )
            )
            rejected += 1
            continue

        if quote_matches(quote, source):
            validated.append(
                ValidatedRequirement(
                    **{**candidate.__dict__},
                    citation_verified=True,
                    validation_note=None,
                )
            )
        else:
            validated.append(
                ValidatedRequirement(
                    **{**candidate.__dict__},
                    citation_verified=False,
                    validation_note=(
                        "la cita no se encontró en el documento: puede ser una "
                        "invención del modelo o un problema de extracción"
                    ),
                )
            )
            rejected += 1

    return validated, rejected


@dataclass
class MatchDecision:
    """Resultado de decidir el estado de un requisito.

    Se separa del `EvidenceMatch` porque la decisión se toma con reglas y el
    registro que se persiste es más simple.
    """

    state: str
    rationale: str
    evidence_chunk_ids: list[int]


def decide_state(
    requirement: ValidatedRequirement,
    evidence: Sequence[RetrievedChunk],
    *,
    threshold: float,
) -> MatchDecision:
    """Decide el estado de un requisito a partir de la evidencia recuperada.

    Reglas, en orden:

    1. **Sin cita verificada → revisión manual.** No se puede afirmar nada sobre
       un requisito cuya fuente no se ha podido comprobar.
    2. **Sin evidencia suficiente → revisión manual, nunca `no_cumple`.** La
       falta de información no es incumplimiento: son cosas distintas y
       confundirlas rechazaría oportunidades válidas.
    3. **Con evidencia por encima del umbral → `cumple` propuesto**, siempre
       sujeto a revisión humana.
    4. **Evidencia débil → `revision_manual`.** Es preferible pedir una lectura a
       afirmar un cumplimiento que no se sostiene.
    """

    if not requirement.citation_verified:
        return MatchDecision(
            state="revision_manual",
            rationale=(
                "el requisito no tiene una cita verificable en el documento: "
                "requiere lectura humana antes de evaluarlo"
            ),
            evidence_chunk_ids=[],
        )

    usable = [c for c in evidence if c.score >= threshold and not c.is_expired]
    if not usable:
        expired = [c for c in evidence if c.is_expired]
        if expired and len(expired) == len(evidence):
            return MatchDecision(
                state="revision_manual",
                rationale=(
                    "la única evidencia encontrada está vencida: no puede sustentar "
                    "un cumplimiento"
                ),
                evidence_chunk_ids=[],
            )
        return MatchDecision(
            state="revision_manual",
            rationale=(
                "no se encontró evidencia empresarial suficiente. La falta de "
                "información no implica incumplimiento"
            ),
            evidence_chunk_ids=[],
        )

    best = max(usable, key=lambda c: c.score)
    unverified = [c for c in usable if not c.is_verified]

    if unverified and len(unverified) == len(usable):
        return MatchDecision(
            state="revision_manual",
            rationale=(
                "la evidencia encontrada no está verificada por una persona: "
                "puede orientar, pero no sustentar un cumplimiento"
            ),
            evidence_chunk_ids=[c.chunk_id for c in usable],
        )

    return MatchDecision(
        state="cumple",
        rationale=(
            f"evidencia recuperada con relevancia {best.score:.2f} "
            f"({best.citation}). Requiere confirmación humana"
        ),
        evidence_chunk_ids=[c.chunk_id for c in usable],
    )


def build_draft_summary(state: AnalysisState) -> str:
    """Resumen legible del borrador, para mostrar antes de la revisión."""

    verified = len(state.verified_requirements)
    unverified = len(state.unverified_requirements)
    pending = sum(1 for m in state.matches if m.state == "revision_manual")
    met = sum(1 for m in state.matches if m.state == "cumple")

    lines = [
        f"Documentos leídos: {state.documents_read}",
        f"Fragmentos disponibles: {state.chunks_available}",
        f"Requisitos extraídos: {len(state.requirements)} "
        f"({verified} con cita verificada, {unverified} sin verificar)",
        f"Propuestas de cumplimiento: {met}",
        f"Pendientes de revisión manual: {pending}",
    ]
    if unverified:
        lines.append(
            f"{unverified} requisitos no tienen cita verificable y no pueden "
            "sustentar un cumplimiento"
        )
    return "\n".join(lines)
