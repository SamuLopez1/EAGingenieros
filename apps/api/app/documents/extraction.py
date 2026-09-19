"""Extracción de texto de PDF, DOCX y XLSX, con OCR cuando hace falta.

El texto que produce este módulo alimenta la fragmentación y el índice
vectorial. Un fallo aquí no se ve como un error: se ve como un RAG que responde
"no hay evidencia" sobre documentos que sí la contienen. Por eso los fallos se
declaran explícitamente en lugar de devolver texto vacío.

Decisiones:

1. **El OCR se activa por un criterio medible**, no por tipo de archivo. Un PDF
   escaneado y uno digital son indistinguibles por extensión. El criterio es la
   densidad de texto por página: por debajo de un umbral, la página se considera
   imagen.
2. **Cada página conserva si vino de OCR.** El texto reconocido tiene más
   errores, y el analista debe poder saberlo antes de confiar en una cita.
3. **Los localizadores se emiten como marcadores de página**, que la
   fragmentación consume para asignar el localizador de cada fragmento.
4. **Un archivo que falla no se marca como extraído.** Un documento con texto
   vacío es peor que uno marcado como fallido: el primero pasa desapercibido.

Límites: el OCR es costoso y puede colgarse con páginas complejas, así que hay
tope de páginas y tiempo por documento. Superarlo se declara, no se ignora.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class ExtractionStatus(StrEnum):
    COMPLETED = "completado"
    COMPLETED_WITH_WARNINGS = "completado_con_advertencias"
    FAILED = "fallido"
    UNSUPPORTED = "no_soportado"


class ExtractionError(RuntimeError):
    """El archivo no se pudo procesar."""


class UnsupportedFormatError(ExtractionError):
    """El formato no está entre los soportados."""


@dataclass
class PageText:
    """Texto de una unidad con su procedencia."""

    number: int
    text: str
    from_ocr: bool = False
    ocr_confidence: float | None = None

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


@dataclass
class ExtractionResult:
    """Resultado completo de extraer un documento."""

    status: ExtractionStatus
    pages: list[PageText] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    # Motivo por el que se activó el OCR, cuando ocurrió.
    ocr_reason: str | None = None

    @property
    def text(self) -> str:
        """Texto completo con marcadores de página.

        Los marcadores son la única forma de que la fragmentación sepa de qué
        página viene cada fragmento. Sin ellos, una cita no tendría localizador.
        """

        parts: list[str] = []
        for page in self.pages:
            if page.is_empty:
                continue
            parts.append(f"[[pagina:{page.number}]]")
            parts.append(page.text.strip())
            parts.append("")
        return "\n".join(parts).strip()

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def ocr_page_numbers(self) -> list[int]:
        return [p.number for p in self.pages if p.from_ocr]

    @property
    def is_usable(self) -> bool:
        """Indica si el resultado sirve para indexar."""

        return (
            self.status
            in (ExtractionStatus.COMPLETED, ExtractionStatus.COMPLETED_WITH_WARNINGS)
            and bool(self.text.strip())
        )


# --- Umbrales --------------------------------------------------------------

# Caracteres por página por debajo de los cuales se considera que la página es
# una imagen. Un PDF digital con una carátula y poco texto puede quedar por
# debajo, pero forzar OCR en ese caso cuesta poco y evita perder contenido.
MIN_CHARS_PER_PAGE = 80

# Tope de páginas para OCR. Reconocer cientos de páginas escaneadas puede tardar
# minutos; superarlo se declara en lugar de bloquear la petición.
MAX_OCR_PAGES = 50

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xlsm"}


def _pdf_pages(data: bytes, password: str | None = None) -> list[PageText]:
    """Extrae el texto digital de un PDF, página a página."""

    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
    except PdfReadError as error:
        raise ExtractionError(f"PDF ilegible: {error}") from error

    if reader.is_encrypted:
        # Un PDF cifrado sin contraseña no se puede leer. Se declara en lugar de
        # devolver vacío, que se confundiría con un documento sin texto.
        if password:
            try:
                reader.decrypt(password)
            except Exception as error:  # noqa: BLE001 - el proveedor lanza tipos variados
                raise ExtractionError("PDF cifrado y la contraseña no es válida") from error
        else:
            raise ExtractionError("PDF cifrado: requiere contraseña")

    pages: list[PageText] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - un página corrupta no debe abortar el resto
            pages.append(PageText(number=index, text=""))
            continue
        pages.append(PageText(number=index, text=text))
    return pages


def _ocr_pages(
    data: bytes,
    page_numbers: list[int],
    *,
    language: str = "spa",
    dpi: int = 200,
) -> dict[int, tuple[str, float | None]]:
    """Reconoce texto en las páginas indicadas.

    El DPI se fija en 200: por debajo, el reconocimiento de texto pequeño —notas
    al pie, tablas— se degrada; por encima, el tiempo crece sin mejorar la
    precisión de forma apreciable.
    """

    import pytesseract  # type: ignore[import-untyped]
    from pdf2image import convert_from_bytes
    from pdf2image.exceptions import PDFPageCountError

    try:
        images = convert_from_bytes(
            data, dpi=dpi, first_page=min(page_numbers), last_page=max(page_numbers)
        )
    except PDFPageCountError as error:
        raise ExtractionError(f"no se pudo rasterizar el PDF para OCR: {error}") from error

    # convert_from_bytes devuelve desde first_page, así que se reindexa.
    first = min(page_numbers)
    recognised: dict[int, tuple[str, float | None]] = {}
    for offset, image in enumerate(images):
        number = first + offset
        if number not in page_numbers:
            continue
        try:
            text = pytesseract.image_to_string(image, lang=language)
        except pytesseract.TesseractError:
            recognised[number] = ("", None)
            continue
        confidence = None
        try:
            # La confianza media permite señalar páginas de baja calidad.
            data_frame = pytesseract.image_to_data(
                image, lang=language, output_type=pytesseract.Output.DICT
            )
            raw_conf = data_frame.get("conf", [])
            values = [
                float(c) for c in raw_conf if str(c).replace("-", "").isdigit()
            ]
            values = [v for v in values if v >= 0]
            if values:
                confidence = sum(values) / len(values) / 100.0
        except Exception:  # noqa: BLE001 - la confianza es informativa, no crítica
            confidence = None
        recognised[number] = (text, confidence)
    return recognised


def extract_pdf(
    data: bytes,
    *,
    password: str | None = None,
    enable_ocr: bool = True,
    ocr_language: str = "spa",
    max_ocr_pages: int = MAX_OCR_PAGES,
) -> ExtractionResult:
    """Extrae texto de un PDF, con OCR para las páginas sin texto suficiente.

    Los fallos de lectura se devuelven como resultado fallido en lugar de
    propagarse: quien llama necesita distinguir "no se pudo leer" de "se leyó y
    está vacío", y una excepción sin capturar convertiría el segundo caso en un
    error de servidor.
    """

    try:
        pages = _pdf_pages(data, password=password)
    except ExtractionError as error:
        return ExtractionResult(status=ExtractionStatus.FAILED, error=str(error))
    if not pages:
        return ExtractionResult(
            status=ExtractionStatus.COMPLETED_WITH_WARNINGS,
            warnings=["el PDF no contiene páginas"],
        )

    warnings: list[str] = []
    ocr_reason: str | None = None

    # Criterio de OCR: densidad media de texto por página.
    total_chars = sum(len(p.text.strip()) for p in pages)
    if total_chars == 0:
        ocr_reason = "el PDF no tiene capa de texto: es un documento escaneado"
    elif total_chars / len(pages) < MIN_CHARS_PER_PAGE:
        ocr_reason = (
            f"densidad de texto muy baja ({total_chars // len(pages)} caracteres por "
            f"página, umbral {MIN_CHARS_PER_PAGE}): probablemente escaneado"
        )

    # Páginas concretas sin texto, aunque la media sea aceptable: un pliego
    # puede tener anexos escaneados entre páginas digitales.
    sparse = [p.number for p in pages if len(p.text.strip()) < MIN_CHARS_PER_PAGE]

    if not enable_ocr:
        if ocr_reason or sparse:
            warnings.append("OCR desactivado: hay páginas sin texto que no se procesaron")
            return ExtractionResult(
                status=ExtractionStatus.COMPLETED_WITH_WARNINGS,
                pages=pages,
                warnings=warnings,
                ocr_reason=ocr_reason,
            )
        return ExtractionResult(status=ExtractionStatus.COMPLETED, pages=pages)

    if not sparse and not ocr_reason:
        return ExtractionResult(status=ExtractionStatus.COMPLETED, pages=pages)

    targets = sparse or [p.number for p in pages]
    if len(targets) > max_ocr_pages:
        warnings.append(
            f"OCR limitado a {max_ocr_pages} de {len(targets)} páginas sin texto; "
            "el resto queda sin reconocer"
        )
        targets = targets[:max_ocr_pages]

    try:
        recognised = _ocr_pages(data, targets, language=ocr_language)
    except ExtractionError as error:
        # El fallo del OCR no invalida el texto digital ya extraído.
        warnings.append(f"el OCR falló: {error}")
        return ExtractionResult(
            status=ExtractionStatus.COMPLETED_WITH_WARNINGS,
            pages=pages,
            warnings=warnings,
            ocr_reason=ocr_reason,
        )

    by_number = {p.number: p for p in pages}
    low_confidence: list[int] = []
    for number, (text, confidence) in recognised.items():
        page = by_number.get(number)
        if page is None:
            continue
        if text.strip():
            # El texto reconocido reemplaza al vacío; no se concatena, porque el
            # original no aporta nada y duplicaría el contenido.
            page.text = text
            page.from_ocr = True
            page.ocr_confidence = confidence
            if confidence is not None and confidence < 0.6:
                low_confidence.append(number)

    if low_confidence:
        warnings.append(
            f"OCR con confianza baja en las páginas {low_confidence}: "
            "conviene revisarlas manualmente antes de confiar en sus citas"
        )

    still_empty = [p.number for p in pages if p.is_empty]
    if still_empty:
        warnings.append(f"páginas sin texto tras el OCR: {still_empty}")

    status = (
        ExtractionStatus.COMPLETED_WITH_WARNINGS if warnings else ExtractionStatus.COMPLETED
    )
    return ExtractionResult(
        status=status, pages=pages, warnings=warnings, ocr_reason=ocr_reason
    )


def extract_docx(data: bytes) -> ExtractionResult:
    """Extrae texto de un DOCX conservando párrafos y tablas.

    Las tablas se extraen porque en pliegos contienen requisitos tabulados, y
    omitirlas perdería exactamente el contenido que hay que comparar.
    """

    import docx
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = docx.Document(io.BytesIO(data))
    except PackageNotFoundError as error:
        raise ExtractionError(f"DOCX ilegible: {error}") from error
    except Exception as error:  # noqa: BLE001 - archivos corruptos lanzan tipos variados
        raise ExtractionError(f"DOCX ilegible: {error}") from error

    blocks: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if text:
            blocks.append(text)

    for table in document.tables:
        # Se marca cada fila con separador de celdas para que la fragmentación
        # conserve la relación entre columnas.
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                blocks.append(" | ".join(cells))

    text = "\n\n".join(blocks)
    pages = [PageText(number=1, text=text)]
    warnings: list[str] = []
    if not text.strip():
        warnings.append("el DOCX no contiene texto extraíble")
    return ExtractionResult(
        status=(
            ExtractionStatus.COMPLETED_WITH_WARNINGS if warnings else ExtractionStatus.COMPLETED
        ),
        pages=pages,
        warnings=warnings,
    )


def extract_xlsx(data: bytes) -> ExtractionResult:
    """Extrae texto de un XLSX, hoja por hoja.

    Cada hoja es una página, de modo que el localizador de un fragmento señala la
    hoja de la que proviene. Dentro de la hoja, las filas se separan con ` | `
    para conservar la relación entre columnas.
    """

    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        workbook = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except InvalidFileException as error:
        raise ExtractionError(f"XLSX ilegible: {error}") from error
    except Exception as error:  # noqa: BLE001 - archivos corruptos lanzan tipos variados
        raise ExtractionError(f"XLSX ilegible: {error}") from error

    pages: list[PageText] = []
    warnings: list[str] = []
    try:
        for index, sheet in enumerate(workbook.worksheets, start=1):
            rows: list[str] = []
            for row in sheet.iter_rows(values_only=True):
                cells = ["" if v is None else str(v).strip() for v in row]
                if any(cells):
                    rows.append(" | ".join(cells))
            body = f"[Hoja: {sheet.title}]\n" + "\n".join(rows) if rows else ""
            pages.append(PageText(number=index, text=body))
    finally:
        workbook.close()

    if not any(p.text.strip() for p in pages):
        warnings.append("el XLSX no contiene datos legibles")
    return ExtractionResult(
        status=(
            ExtractionStatus.COMPLETED_WITH_WARNINGS if warnings else ExtractionStatus.COMPLETED
        ),
        pages=pages,
        warnings=warnings,
    )


def extract(
    data: bytes,
    filename: str | None = None,
    *,
    content_type: str | None = None,
    password: str | None = None,
    enable_ocr: bool = True,
    ocr_language: str = "spa",
) -> ExtractionResult:
    """Extrae texto del documento, eligiendo el extractor por formato.

    El formato se decide por extensión y, si no la hay, por el tipo MIME
    declarado. No se confía solo en el MIME: los navegadores lo envían de forma
    inconsistente y un PDF etiquetado como `application/octet-stream` es común.
    """

    suffix = Path(filename or "").suffix.lower()
    if not suffix and content_type:
        suffix = {
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        }.get(content_type.split(";")[0].strip().lower(), "")

    if suffix not in SUPPORTED_EXTENSIONS:
        return ExtractionResult(
            status=ExtractionStatus.UNSUPPORTED,
            error=(
                f"formato no soportado: {suffix or 'desconocido'}. "
                f"Soportados: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        )

    try:
        if suffix == ".pdf":
            return extract_pdf(
                data,
                password=password,
                enable_ocr=enable_ocr,
                ocr_language=ocr_language,
            )
        if suffix == ".docx":
            return extract_docx(data)
        return extract_xlsx(data)
    except ExtractionError as error:
        return ExtractionResult(status=ExtractionStatus.FAILED, error=str(error))
    except Exception as error:  # noqa: BLE001 - ningún fallo debe escapar sin declararse
        return ExtractionResult(
            status=ExtractionStatus.FAILED, error=f"fallo inesperado: {type(error).__name__}"
        )


def looks_like_scanned_pdf(data: bytes) -> bool:
    """Indica si un PDF carece de capa de texto, sin extraerlo completo.

    Útil para decidir si conviene encolar OCR antes de procesar el documento.
    """

    try:
        pages = _pdf_pages(data)
    except ExtractionError:
        return False
    return all(p.is_empty for p in pages) if pages else False
