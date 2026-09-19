"""Fragmentación de documentos en unidades recuperables.

La fragmentación decide la calidad de todo el RAG. Un fragmento demasiado
grande diluye la señal y hace que la búsqueda devuelva el documento entero; uno
demasiado pequeño parte una cláusula y devuelve una condición sin su contexto,
lo que produce citas técnicamente correctas pero engañosas.

Decisiones:

1. **Cortar por estructura antes que por longitud.** Se intenta respetar
   párrafos y saltos naturales. Un límite de caracteres es el último recurso,
   no el primero.
2. **Solapamiento entre fragmentos contiguos.** Sin él, una cláusula que cae a
   caballo entre dos fragmentos se pierde para la búsqueda: cada mitad queda
   incompleta y ninguna se recupera.
3. **Los localizadores se conservan.** Cada fragmento sabe de qué página o
   sección viene, porque una cita sin localizador no es verificable.
4. **Sin solapamiento entre documentos distintos.** El solapamiento es dentro de
   un mismo documento; mezclar el final de uno con el inicio de otro produciría
   citas falsas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Tamaño objetivo en caracteres. Se usa caracteres y no tokens para no depender
# del tokenizador de un modelo concreto, que cambiaría el resultado al cambiar
# de proveedor. La equivalencia aproximada es 4 caracteres por token.
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_OVERLAP = 180

# Un fragmento por debajo de esto no aporta contexto suficiente para sustentar
# una afirmación, así que se fusiona con el siguiente si es posible.
MIN_CHUNK_SIZE = 240


@dataclass(frozen=True)
class Chunk:
    """Un fragmento con su texto y su localizador verificable."""

    ordinal: int
    content: str
    locator: str | None
    page_number: int | None
    section: str | None

    @property
    def token_estimate(self) -> int:
        return max(1, len(self.content) // 4)


# Marcadores de página que dejan los extractores de PDF. Se reconocen para
# poder asignar un localizador real a cada fragmento en lugar de uno genérico.
_PAGE_MARKER = re.compile(r"^\[\[pagina:(\d+)\]\]$", re.IGNORECASE)
# Encabezados numerados habituales en pliegos: "3.1 Requisitos", "ARTÍCULO 5".
_SECTION_HEADING = re.compile(
    r"^\s*(?:(?:\d+(?:\.\d+)*)|(?:ART[IÍ]CULO|CLAUSULA|CLÁUSULA|CAP[IÍ]TULO|SECCI[OÓ]N|ANEXO))\b[^\n]{0,120}$",
    re.IGNORECASE,
)


def _split_paragraphs(text: str) -> list[str]:
    """Divide por límites naturales, conservando los que aportan estructura."""

    # Se normalizan los finales de línea y se corta por línea en blanco, que es
    # el separador de párrafo más fiable en texto extraído.
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"\n\s*\n", normalised)
    return [p.strip() for p in parts if p.strip()]


def _hard_split(text: str, size: int, overlap: int) -> list[str]:
    """Corte por longitud para párrafos que exceden el tamaño objetivo.

    Intenta cortar en un final de frase antes que a mitad de palabra, porque un
    corte a mitad de palabra degrada la representación vectorial del fragmento.
    """

    pieces: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + size, length)
        if end < length:
            # Buscar el último final de frase dentro de la ventana.
            window = text[start:end]
            for separator in (". ", "; ", ", "):
                cut = window.rfind(separator)
                if cut > size // 2:
                    end = start + cut + len(separator)
                    break
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= length:
            break
        # El siguiente fragmento empieza antes para no perder el contexto que
        # quedo a caballo entre ambos. El retroceso debe caer en un limite de
        # palabra: retroceder N caracteres sin mas produce fragmentos que
        # empiezan a mitad de palabra ("ONDICIONES" en vez de "CONDICIONES"),
        # lo que degrada la representacion vectorial y muestra al analista una
        # cita mutilada. Se busca el limite hacia ADELANTE desde el retroceso,
        # nunca hacia atras, para no solapar mas de lo pedido.
        back = max(end - overlap, start + 1)
        if back > start + 1:
            boundary = text.find(" ", back, end)
            if boundary != -1:
                back = boundary + 1
        start = back
    return pieces


def chunk_text(
    text: str,
    *,
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Fragmenta un texto plano en unidades recuperables.

    Los marcadores de página del extractor se consumen aquí: no forman parte del
    contenido —no deben aparecer en una cita— y solo sirven para asignar el
    localizador.
    """

    if not text or not text.strip():
        return []
    if overlap >= size:
        raise ValueError("el solapamiento debe ser menor que el tamaño del fragmento")

    chunks: list[Chunk] = []
    current_page: int | None = None
    current_section: str | None = None
    buffer: list[str] = []
    buffer_len = 0
    ordinal = 0
    pending_page = current_page
    pending_section = current_section

    def flush() -> None:
        nonlocal buffer, buffer_len, ordinal, pending_page, pending_section
        if not buffer:
            return
        content = "\n\n".join(buffer).strip()
        if not content:
            buffer, buffer_len = [], 0
            return
        chunks.append(
            Chunk(
                ordinal=ordinal,
                content=content,
                locator=_format_locator(pending_page, pending_section),
                page_number=pending_page,
                section=pending_section,
            )
        )
        ordinal += 1
        # El solapamiento se toma del final del fragmento emitido, para que una
        # clausula partida aparezca completa en al menos uno de los dos.
        #
        # Reglas, aprendidas de un defecto real:
        #   - el solapamiento nunca puede ser mayor que el fragmento, o el
        #     siguiente fragmento empezaria con el anterior entero duplicado;
        #   - el corte debe caer en un limite de palabra, o el fragmento empieza
        #     a mitad de palabra ("ONDICIONES" en vez de "CONDICIONES"), lo que
        #     degrada la representacion vectorial y muestra al analista una cita
        #     mutilada.
        tail = ""
        effective_overlap = min(overlap, len(content) // 3)
        if effective_overlap >= 20:
            # El candidato empieza necesariamente a mitad de palabra, porque se
            # toma por numero de caracteres. Lo correcto es **descartar** el
            # principio del candidato hasta el primer limite limpio, no buscar
            # un limite y cortar ahi: eso agravaria el problema.
            candidate = content[-effective_overlap:]
            sentence = candidate.find(". ")
            space = candidate.find(" ")
            if sentence >= 0:
                # Empezar en la frase siguiente: el texto queda completo.
                tail = candidate[sentence + 2 :]
            elif space >= 0:
                tail = candidate[space + 1 :]
            else:
                # Sin ningun espacio: es una sola palabra larguisima. Se omite
                # el solapamiento en lugar de duplicar texto mutilado.
                tail = ""
        buffer = [tail] if tail.strip() else []
        pending_page = current_page
        pending_section = current_section

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        page_match = _PAGE_MARKER.match(line.strip())
        if page_match:
            # El marcador cierra la página anterior y abre la siguiente.
            flush()
            current_page = int(page_match.group(1))
            pending_page = current_page
            continue

        if _SECTION_HEADING.match(line) and line.strip():
            # Un encabezado es un buen punto de corte: empezar un fragmento con
            # la sección a la que pertenece el texto mejora la recuperación.
            flush()
            current_section = line.strip()[:300]
            pending_section = current_section

        # Una linea que por si sola excede el objetivo se corta antes de
        # acumularla. Sin esto, un texto sin saltos de linea —frecuente en
        # extracciones de PDF— produce un unico fragmento enorme: la busqueda
        # devolveria el documento entero y la cita perderia precision.
        if len(line) > size:
            flush()
            for piece in _hard_split(line, size, overlap):
                ordinal_local = len(chunks)
                chunks.append(
                    Chunk(
                        ordinal=ordinal_local,
                        content=piece,
                        locator=_format_locator(pending_page, pending_section),
                        page_number=pending_page,
                        section=pending_section,
                    )
                )
            pending_page = current_page
            pending_section = current_section
            continue

        buffer.append(line)
        buffer_len += len(line) + 1

        if buffer_len >= size:
            flush()

    flush()

    # Los fragmentos diminutos del final se fusionan con el anterior: solos no
    # aportan contexto y ocupan un lugar en el índice.
    merged: list[Chunk] = []
    for chunk in chunks:
        if (
            merged
            and len(chunk.content.strip()) < MIN_CHUNK_SIZE
            and merged[-1].page_number == chunk.page_number
        ):
            previous = merged[-1]
            merged[-1] = Chunk(
                ordinal=previous.ordinal,
                content=f"{previous.content}\n\n{chunk.content}".strip(),
                locator=previous.locator,
                page_number=previous.page_number,
                section=previous.section,
            )
        else:
            merged.append(chunk)

    return [
        Chunk(
            ordinal=index,
            content=chunk.content,
            locator=chunk.locator,
            page_number=chunk.page_number,
            section=chunk.section,
        )
        for index, chunk in enumerate(merged)
    ]


def _format_locator(page: int | None, section: str | None) -> str | None:
    """Construye el localizador legible que acompaña a cada fragmento."""

    parts: list[str] = []
    if page is not None:
        parts.append(f"pág. {page}")
    if section:
        parts.append(section)
    return " · ".join(parts) if parts else None


def split_oversized(
    text: str,
    *,
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Corta un párrafo que excede el tamaño objetivo.

    Expuesto aparte para poder probarlo sin construir documentos completos.
    """

    if len(text) <= size:
        return [text]
    return _hard_split(text, size, overlap)
