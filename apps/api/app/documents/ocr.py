"""Reconocimiento óptico de caracteres sobre páginas rasterizadas.

Responsabilidad única: convertir una página escaneada en texto. No decide cuándo
activarse —eso corresponde al extractor de PDF, que mide la densidad de texto— ni
interpreta el resultado.

El DPI se fija en 200: por debajo, el reconocimiento de texto pequeño —notas al
pie, tablas— se degrada; por encima, el tiempo crece sin mejorar la precisión de
forma apreciable.
"""

from __future__ import annotations

import pytesseract  # type: ignore[import-untyped]
from pdf2image import convert_from_bytes
from pdf2image.exceptions import PDFPageCountError

from app.documents.extraction_types import ExtractionError

DEFAULT_DPI = 200
DEFAULT_LANGUAGE = "spa"


def recognise_pages(
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
