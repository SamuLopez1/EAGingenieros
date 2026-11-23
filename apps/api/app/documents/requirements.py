"""Análisis extractivo con evidencia validada fuera del adaptador."""

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, Protocol
from unicodedata import combining, normalize
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.documents.extraction import Locator

SCHEMA_VERSION = "1"
MAX_SOURCE_BYTES = 12_000
MAX_SOURCES = 80

Kind = Literal["objeto", "entregable", "plazo", "alerta", "habilitante", "evaluable", "obligacion"]
LABELS: dict[str, Kind] = {
    "objeto": "objeto",
    "objeto del contrato": "objeto",
    "objeto del proceso": "objeto",
    "entregables": "entregable",
    "plazo de ejecucion": "plazo",
    "requisitos habilitantes": "habilitante",
    "criterios evaluables": "evaluable",
    "obligaciones del contratista": "obligacion",
    "entregable": "entregable",
    "plazo": "plazo",
    "cierre": "plazo",
    "fecha de cierre": "plazo",
    "alerta": "alerta",
    "habilitante": "habilitante",
    "requisito habilitante": "habilitante",
    "evaluable": "evaluable",
    "criterio evaluable": "evaluable",
    "obligacion": "obligacion",
    "obligacion de ejecucion": "obligacion",
}

INSTRUCTION_MARKERS = (
    "ignora las instrucciones",
    "ignora todas",
    "ignore previous",
    "ignore all",
    "mensaje del sistema",
    "system prompt",
    "developer message",
)


def folded(text: str) -> str:
    return "".join(char for char in normalize("NFKD", text.lower()) if not combining(char))


def suspicious(text: str) -> bool:
    return any(marker in folded(text) for marker in INSTRUCTION_MARKERS)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(Contract):
    document_id: UUID
    version: int
    sha256: str
    title: str
    kind: Literal["pliego", "adenda"]
    locator: Locator
    text: str


class Candidate(Contract):
    kind: Kind
    source: int
    quote: str


class Proposal(Contract):
    items: list[Candidate]


class Citation(Contract):
    document_id: UUID
    version: int
    sha256: str
    title: str
    locator: Locator
    quote: str


class Finding(Contract):
    kind: Kind
    citation: Citation


class Warning(Contract):
    code: str
    documents: list[UUID] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class Analysis(Contract):
    schema_version: str = SCHEMA_VERSION
    adapter: str
    fingerprint: str
    status: Literal["revision_manual", "borrador"]
    incomplete: bool
    summary: list[Finding]
    requirements: list[Finding]
    warnings: list[Warning]


class ProviderError(RuntimeError):
    """Fallo, truncamiento o respuesta no utilizable."""


class Adapter(Protocol):
    @property
    def version(self) -> str: ...

    def propose(self, sources: list[Source]) -> Proposal: ...


@dataclass(frozen=True)
class OfflineAdapter:
    version: str = "offline-reglas-v1"

    def propose(self, sources: list[Source]) -> Proposal:
        items: list[Candidate] = []
        for index, source in enumerate(sources):
            for raw in source.text.splitlines():
                line = raw.strip()
                label, separator, content = line.partition(":")
                kind = LABELS.get(folded(label.strip()))
                if separator and kind and content.strip() and not suspicious(line):
                    items.append(Candidate(kind=kind, source=index, quote=line))
        if len(items) > MAX_SOURCES:
            raise ProviderError
        return Proposal(items=items)


def citation(source: Source, quote: str) -> Citation:
    return Citation(
        document_id=source.document_id,
        version=source.version,
        sha256=source.sha256,
        title=source.title,
        locator=source.locator,
        quote=quote,
    )


def contradictions(findings: list[tuple[Finding, Source]]) -> list[Warning]:
    grouped: dict[tuple[Kind, str], tuple[Finding, Source]] = {}
    warnings: list[Warning] = []
    for finding, source in findings:
        _, separator, value = finding.citation.quote.partition(":")
        if not separator:
            continue
        subject, qualifier, content = value.partition(":")
        if not qualifier and finding.kind not in {"plazo", "objeto"}:
            continue
        key = (finding.kind, folded(subject.strip()) if qualifier else "")
        prior = grouped.setdefault(key, (finding, source))
        old, original = prior
        if (
            original.document_id != source.document_id
            and "adenda" in {original.kind, source.kind}
            and folded(old.citation.quote) != folded(finding.citation.quote)
        ):
            warnings.append(
                Warning(
                    code="posible_contradiccion_adenda",
                    documents=[original.document_id, source.document_id],
                    citations=[old.citation, finding.citation],
                )
            )
        elif qualifier and not content.strip():
            warnings.append(Warning(code="texto_ambiguo", citations=[finding.citation]))
    return warnings


def build_analysis(
    adapter: Adapter,
    fingerprint: str,
    sources: list[Source],
    warnings: list[Warning],
) -> Analysis:
    incomplete = bool(warnings) or not sources
    safe_sources = []
    for source in sources:
        if suspicious(source.text):
            warnings.append(
                Warning(code="instruccion_documental_omitida", documents=[source.document_id])
            )
            source = source.model_copy(
                update={
                    "text": "\n".join(
                        line for line in source.text.splitlines() if not suspicious(line)
                    )
                }
            )
        safe_sources.append(source)
    findings: list[tuple[Finding, Source]] = []
    seen: set[tuple[int, str, str]] = set()
    try:
        proposed = adapter.propose(safe_sources) if safe_sources else Proposal(items=[])
        if len(proposed.items) > MAX_SOURCES:
            raise ProviderError
        for item in proposed.items:
            if (
                not 0 <= item.source < len(safe_sources)
                or not item.quote.strip()
                or len(item.quote) > 1200
                or item.quote not in safe_sources[item.source].text
            ):
                warnings.append(Warning(code="cita_invalida"))
                continue
            source = sources[item.source]
            if item.quote not in source.text or suspicious(item.quote):
                warnings.append(Warning(code="cita_invalida"))
                continue
            key = (item.source, item.kind, item.quote)
            if key not in seen:
                seen.add(key)
                findings.append(
                    (Finding(kind=item.kind, citation=citation(source, item.quote)), source)
                )
    except ProviderError, ValidationError:
        warnings.append(Warning(code="adaptador_sin_resultado"))
    warnings.extend(contradictions(findings))
    supported = {source.document_id for _, source in findings}
    for doc in sorted({source.document_id for source in sources} - supported):
        warnings.append(Warning(code="documento_sin_hallazgos", documents=[doc]))
    if any(source.kind == "adenda" for source in sources):
        warnings.append(Warning(code="revisar_precedencia_adendas"))
    summary = [
        item for item, _ in findings if item.kind in {"objeto", "entregable", "plazo", "alerta"}
    ]
    requirements = [
        item for item, _ in findings if item.kind in {"habilitante", "evaluable", "obligacion"}
    ]
    for kind in ("objeto", "entregable", "plazo"):
        if not any(item.kind == kind for item in summary):
            warnings.append(Warning(code=f"sin_{kind}_confirmado"))
    if not requirements:
        warnings.append(Warning(code="sin_requisitos_confirmados"))
    return Analysis(
        adapter=adapter.version,
        fingerprint=fingerprint,
        status="revision_manual" if warnings else "borrador",
        incomplete=incomplete,
        summary=summary,
        requirements=requirements,
        warnings=warnings,
    )


def fingerprint_for(scope: str, sources: list[Source], warnings: list[Warning]) -> str:
    data = "\n".join(
        [
            scope,
            SCHEMA_VERSION,
            *(source.model_dump_json() for source in sources),
            *(warning.model_dump_json() for warning in warnings),
        ]
    )
    return sha256(data.encode()).hexdigest()
