"""Extracción de requisitos de un pliego.

Contrato: dado el texto de un documento, devolver candidatos de requisito, cada
uno **con su cita textual**. Sin cita no hay verificación posible, y sin
verificación el requisito no puede sustentar nada.

Hay dos implementaciones:

- **`RuleBasedExtractor`**: reconoce requisitos por patrones del lenguaje de los
  pliegos («debe acreditar», «se exige», «mínimo de»). No requiere modelo, no
  cuesta nada y es determinista. Es lo bastante bueno para que el grafo funcione
  de extremo a extremo y para medir el resto del sistema.

- **`ModelExtractor`**: usa un modelo de lenguaje con salida estructurada. Está
  definido pero **no conectado**: requiere configurar proveedor, clave y
  presupuesto. El extractor se inyecta, así que conectarlo no toca el grafo.

Por qué empezar por reglas y no por el modelo: un extractor por patrones produce
citas que son literales del documento por construcción, de modo que el nodo de
validación tiene algo real que verificar. Empezar por el modelo daría citas
generadas y haría imposible distinguir un fallo del extractor de un fallo de la
validación.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from app.analysis.state import RequirementCandidate
from app.rag.retriever import RetrievedChunk

# Verbos y fórmulas que introducen una obligación en un pliego colombiano.
OBLIGATION_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        r"\bdebe(?:r[áa])?\s+(?:acreditar|presentar|cumplir|contar|demostrar|tener|poseer)",
        "obligacion",
    ),
    (r"\bse\s+(?:exige|requiere|solicita|deber[áa])", "obligacion"),
    (r"\bes\s+(?:requisito|obligatorio|indispensable|necesario)", "obligacion"),
    (r"\brequisitos?\s+(?:m[íi]nimos?|habilitantes?|t[ée]cnicos?)", "requisito"),
    (r"\bno\s+(?:podr[áa]|deber[áa])\s+", "prohibicion"),
)

# Categorías reconocibles por palabras del texto. La categoría orienta la
# comparación: un requisito financiero se contrasta con el perfil financiero.
CATEGORY_HINTS: tuple[tuple[str, str], ...] = (
    (r"experiencia|contratos?\s+ejecutad|interventor", "experiencia"),
    (
        r"patrimonio|capital\s+de\s+trabajo|liquidez|endeudamiento|"
        r"financier|estados?\s+financier",
        "financiero",
    ),
    (
        r"hoja\s+de\s+vida|profesional|ingenier|formaci[óo]n|t[íi]tulo|"
        r"experiencia\s+del\s+personal",
        "personal",
    ),
    (
        r"rup|registro\s+[úu]nico|c[áa]mara\s+de\s+comercio|p[óo]liza|"
        r"garant[íi]a|habilitaci[óo]n|matr[íi]cula",
        "legal",
    ),
    (
        r"equipo|maquinaria|veh[íi]culo|herramienta|capacidad\s+t[ée]cnica|"
        r"laboratorio",
        "tecnico",
    ),
)

# Cantidades y umbrales, que son la parte comparable de un requisito.
QUANTITY_PATTERN = re.compile(
    r"(?:m[íi]nimo|m[áa]ximo|no\s+menor\s+a|igual\s+o\s+superior\s+a|al\s+menos)?\s*"
    r"(\d[\d.,]*)\s*"
    r"(a[ñn]os?|meses?|salarios?\s+m[íi]nimos?|smmlv|unidades?|veh[íi]culos?|equipos?|%)",
    re.IGNORECASE,
)


class RequirementExtractor(Protocol):
    """Contrato del extractor. Se inyecta en el grafo."""

    def __call__(
        self, chunks: Sequence[RetrievedChunk]
    ) -> list[RequirementCandidate]: ...


def guess_category(text: str) -> str | None:
    """Deduce la categoría del requisito por palabras del propio texto."""

    lowered = text.lower()
    for pattern, category in CATEGORY_HINTS:
        if re.search(pattern, lowered):
            return category
    return None


def is_obligation(text: str) -> bool:
    """Indica si el texto formula una obligación."""

    lowered = text.lower()
    # La tupla lleva la etiqueta de la obligación además del patrón: se
    # desestructura para no pasar la tupla entera a `re.search`.
    return any(re.search(pattern, lowered) for pattern, _label in OBLIGATION_PATTERNS)


def split_sentences(text: str) -> list[str]:
    """Divide en frases, conservando las que son suficientemente largas.

    Los pliegos usan frases largas con incisos; se corta por punto seguido de
    mayúscula o salto, que en texto extraído de PDF es un límite fiable.
    """

    normalised = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.;:])\s+(?=[A-ZÁÉÍÓÚÑ0-9])", normalised)
    return [p.strip() for p in parts if len(p.strip()) >= 40]


class RuleBasedExtractor:
    """Extractor por patrones del lenguaje de los pliegos.

    Cada requisito que produce lleva como cita la frase completa de la que se
    extrajo, que es literal del documento. Esa literalidad es lo que hace que el
    nodo de validación tenga algo real que comprobar.
    """

    def __init__(self, *, max_requirements: int = 200) -> None:
        # Tope para no producir cientos de candidatos de un pliego muy largo y
        # disparar el coste de la comparación sin que nadie lo note.
        self._max = max_requirements

    def __call__(
        self, chunks: Sequence[RetrievedChunk]
    ) -> list[RequirementCandidate]:
        candidates: list[RequirementCandidate] = []
        seen: set[str] = set()

        for chunk in chunks:
            for sentence in split_sentences(chunk.content):
                if len(candidates) >= self._max:
                    return candidates
                if not is_obligation(sentence):
                    continue
                # Deduplicación por texto normalizado: el solapamiento entre
                # fragmentos repite frases, y sin esto el mismo requisito
                # aparecería varias veces y se compararía varias veces.
                key = re.sub(r"\s+", " ", sentence.lower())[:200]
                if key in seen:
                    continue
                seen.add(key)

                candidates.append(
                    RequirementCandidate(
                        text=sentence,
                        category=guess_category(sentence),
                        source_document_id=chunk.document_id,
                        source_locator=chunk.locator,
                        quote=sentence,
                        confidence=None,
                    )
                )
        return candidates


class ModelExtractor:
    """Extractor con modelo de lenguaje. **No conectado todavía.**

    Se deja definido para que el contrato sea estable, pero lanzar es deliberado:
    devolver una lista vacía haría creer que un pliego no tiene requisitos,
    cuando lo que ocurre es que el proveedor no está configurado. Es la misma
    regla que en el resto del sistema: un fallo se declara, no se disfraza de
    resultado vacío.
    """

    def __init__(self, *, client: object, model: str) -> None:
        self._client = client
        self._model = model

    def __call__(
        self, chunks: Sequence[RetrievedChunk]
    ) -> list[RequirementCandidate]:
        raise NotImplementedError(
            "el extractor con modelo no está conectado: requiere configurar "
            "proveedor, clave y presupuesto. Use RuleBasedExtractor mientras tanto"
        )
