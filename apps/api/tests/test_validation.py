"""Pruebas de validación y cuarentena de archivos.

Se construyen archivos reales —PDF, DOCX, ZIP con contenido peligroso— en lugar
de simular las comprobaciones. Lo que puede fallar aquí es precisamente la
interacción con el formato.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.documents.antivirus import AntivirusUnavailableError
from app.documents.archive_inspector import inspect_archive
from app.documents.content_inspector import (
    detect_content_type,
    detect_dangerous_signature,
)
from app.documents.filenames import safe_filename
from app.documents.validation import validate_upload
from app.documents.validation_types import QuarantineReason

# --- Generadores -----------------------------------------------------------


def make_pdf() -> bytes:
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(60, 760, "Contenido de un pliego de condiciones valido.")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.read()


def make_docx(with_macros: bool = False) -> bytes:
    import docx

    document = docx.Document()
    document.add_paragraph("Certificado de experiencia con contenido suficiente.")
    buffer = io.BytesIO()
    document.save(buffer)
    data = buffer.getvalue()

    if with_macros:
        # Añadir un vbaProject.bin, que es lo que delata un documento con macros.
        source = zipfile.ZipFile(io.BytesIO(data))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as target:
            for item in source.infolist():
                target.writestr(item, source.read(item.filename))
            target.writestr("word/vbaProject.bin", b"\x00macros")
        return out.getvalue()
    return data


def make_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    buffer.seek(0)
    return buffer.read()


class FakeScanner:
    """Antivirus de prueba."""

    def __init__(
        self, *, available: bool = True, clean: bool = True, threat: str = "Eicar-Test"
    ) -> None:
        self._available = available
        self._clean = clean
        self._threat = threat
        self.scanned: list[bytes] = []

    @property
    def available(self) -> bool:
        return self._available

    @property
    def engine(self) -> str:
        return "fake-antivirus"

    def scan(self, data: bytes) -> tuple[bool, str | None]:
        if not self._available:
            raise AntivirusUnavailableError("no responde")
        self.scanned.append(data)
        return (self._clean, None if self._clean else self._threat)


# --- Nombres ---------------------------------------------------------------


@pytest.mark.parametrize(
    "peligroso",
    ["../../../etc/passwd.pdf", "..\\..\\windows\\x.pdf", "a\x00.pdf", "/abs/ruta.pdf"],
)
def test_dangerous_filenames_are_neutralised(peligroso: str) -> None:
    resultado = safe_filename(peligroso)

    assert resultado is not None
    assert "/" not in resultado
    assert "\\" not in resultado
    assert "\x00" not in resultado
    assert ".." not in resultado


def test_normal_filename_is_preserved() -> None:
    assert safe_filename("pliego_2026.pdf") == "pliego_2026.pdf"


def test_unsafe_name_is_neutralised_not_merely_flagged() -> None:
    """Lo que importa es que el nombre resultante no pueda escapar."""

    saneado = safe_filename("../../etc/passwd")

    assert saneado is not None
    assert "/" not in saneado and ".." not in saneado


# --- Tipo por contenido ----------------------------------------------------


def test_pdf_is_detected_by_content() -> None:
    assert detect_content_type(make_pdf()) == "application/pdf"


def test_docx_is_detected_by_internal_structure() -> None:
    assert "wordprocessingml" in (detect_content_type(make_docx()) or "")


def test_xlsx_is_detected_by_internal_structure() -> None:
    import openpyxl

    workbook = openpyxl.Workbook()
    workbook.active.append(["a", "b"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    assert "spreadsheetml" in (detect_content_type(buffer.getvalue()) or "")


def test_unknown_content_has_no_type() -> None:
    assert detect_content_type(b"texto plano cualquiera") is None


def test_renamed_executable_is_not_a_pdf() -> None:
    """La extensión la controla quien sube: hay que mirar el contenido."""

    assert detect_content_type(b"MZ\x90\x00" + b"\x00" * 100) is None


# --- Firmas peligrosas -----------------------------------------------------


@pytest.mark.parametrize(
    "firma",
    [b"MZ\x90\x00", b"\x7fELF", b"#!", b"<?php echo 1;"],
)
def test_dangerous_signatures_are_detected(firma: bytes) -> None:
    assert detect_dangerous_signature(firma) is not None


def test_pdf_is_not_a_dangerous_signature() -> None:
    assert detect_dangerous_signature(make_pdf()) is None


def test_executable_disguised_as_pdf_is_rejected() -> None:
    """El caso que justifica mirar el contenido y no la extensión."""

    resultado = validate_upload(b"MZ\x90\x00" + b"\x00" * 500, filename="pliego.pdf")

    assert not resultado.accepted
    assert resultado.reason is QuarantineReason.DANGEROUS_TYPE


def test_shebang_script_is_rejected() -> None:
    resultado = validate_upload(b"#!/bin/sh\nrm -rf /", filename="nota.pdf")

    assert not resultado.accepted
    assert resultado.reason is QuarantineReason.DANGEROUS_TYPE


# --- Coherencia de tipos ---------------------------------------------------


def test_declared_type_mismatch_is_rejected() -> None:
    resultado = validate_upload(
        make_docx(),
        filename="pliego.pdf",
        declared_content_type="application/pdf",
    )

    assert not resultado.accepted
    assert resultado.reason is QuarantineReason.TYPE_MISMATCH
    assert "wordprocessingml" in (resultado.detail or "")


def test_generic_octet_stream_is_tolerated() -> None:
    """Los navegadores envían este tipo con frecuencia; no contradice nada."""

    resultado = validate_upload(
        make_pdf(), filename="p.pdf", declared_content_type="application/octet-stream"
    )

    assert resultado.accepted


def test_valid_pdf_with_matching_type_is_accepted() -> None:
    resultado = validate_upload(
        make_pdf(), filename="p.pdf", declared_content_type="application/pdf"
    )

    assert resultado.accepted
    assert resultado.detected_type == "application/pdf"


# --- Tamaño ----------------------------------------------------------------


def test_empty_file_is_rejected() -> None:
    resultado = validate_upload(b"", filename="vacio.pdf")

    assert not resultado.accepted
    assert resultado.reason is QuarantineReason.EMPTY


def test_oversized_file_is_rejected() -> None:
    resultado = validate_upload(b"%PDF-" + b"x" * 100, filename="p.pdf", max_bytes=50)

    assert not resultado.accepted
    assert resultado.reason is QuarantineReason.TOO_LARGE


# --- Estructura ZIP --------------------------------------------------------


def test_zip_slip_is_detected() -> None:
    """Una entrada con `../` escribiría fuera del directorio al descomprimir."""

    data = make_zip({"../../etc/passwd": b"contenido"})

    reason, detail = inspect_archive(data)

    assert reason is QuarantineReason.ZIP_SLIP
    assert "intenta salir" in (detail or "")


def test_absolute_path_in_zip_is_detected() -> None:
    data = make_zip({"/etc/passwd": b"contenido"})

    reason, _ = inspect_archive(data)

    assert reason is QuarantineReason.ZIP_SLIP


def test_compression_bomb_is_detected() -> None:
    """Un archivo que descomprime a gigabytes no es un documento."""

    data = make_zip({"grande.txt": b"\x00" * (5 * 1024 * 1024)})

    reason, detail = inspect_archive(data)

    assert reason is QuarantineReason.ZIP_BOMB


def test_macros_in_docx_are_detected() -> None:
    """Un documento con macros puede ejecutar código al abrirse."""

    data = make_docx(with_macros=True)

    reason, detail = inspect_archive(data)

    assert reason is QuarantineReason.MACROS
    assert "macros" in (detail or "")


def test_executable_inside_zip_is_detected() -> None:
    data = make_zip({"payload.exe": b"MZ\x90\x00"})

    reason, _ = inspect_archive(data)

    assert reason is QuarantineReason.DANGEROUS_TYPE


def test_normal_zip_passes_inspection() -> None:
    data = make_zip({"documento.txt": b"contenido normal"})

    reason, _ = inspect_archive(data)

    assert reason is None


def test_corrupt_zip_is_detected() -> None:
    reason, _ = inspect_archive(b"PK\x03\x04datos corruptos")

    assert reason is QuarantineReason.CORRUPT


# --- Antivirus -------------------------------------------------------------


def test_clean_file_passes_the_scanner() -> None:
    scanner = FakeScanner(clean=True)

    resultado = validate_upload(make_pdf(), filename="p.pdf", scanner=scanner)

    assert resultado.accepted
    assert resultado.scanned
    assert resultado.scan_engine == "fake-antivirus"
    assert scanner.scanned, "el antivirus debía analizar el archivo"


def test_malware_is_rejected() -> None:
    scanner = FakeScanner(clean=False, threat="Trojan.Generic")

    resultado = validate_upload(make_pdf(), filename="p.pdf", scanner=scanner)

    assert not resultado.accepted
    assert resultado.reason is QuarantineReason.MALWARE
    assert "Trojan.Generic" in (resultado.detail or "")


def test_unavailable_antivirus_does_not_approve_when_required() -> None:
    """El defecto más común y más grave: tratar una caída como aprobación.

    Si el antivirus no responde, el archivo no está limpio: está sin analizar.
    """

    scanner = FakeScanner(available=False)

    resultado = validate_upload(
        make_pdf(), filename="p.pdf", scanner=scanner, require_antivirus=True
    )

    assert not resultado.accepted
    assert resultado.reason is QuarantineReason.ANTIVIRUS_UNAVAILABLE
    assert not resultado.scanned


def test_unavailable_antivirus_is_declared_when_not_required() -> None:
    """Sin exigirlo, se acepta pero se declara que no se analizó."""

    scanner = FakeScanner(available=False)

    resultado = validate_upload(
        make_pdf(), filename="p.pdf", scanner=scanner, require_antivirus=False
    )

    assert resultado.accepted
    assert not resultado.scanned
    assert any("no está disponible" in w for w in resultado.warnings)


def test_no_scanner_is_declared_as_warning() -> None:
    resultado = validate_upload(make_pdf(), filename="p.pdf", scanner=None)

    assert resultado.accepted
    assert not resultado.scanned
    assert any("no hay antivirus configurado" in w for w in resultado.warnings)


def test_scanner_error_is_treated_as_unavailable() -> None:
    """Un fallo del motor no debe convertirse en aprobación."""

    class BrokenScanner:
        available = True

        @property
        def engine(self) -> str:
            return "roto"

        def scan(self, data: bytes) -> tuple[bool, str | None]:
            raise AntivirusUnavailableError("el motor falló a mitad del análisis")

    resultado = validate_upload(
        make_pdf(), filename="p.pdf", scanner=BrokenScanner(), require_antivirus=True
    )

    assert not resultado.accepted
    assert resultado.reason is QuarantineReason.ANTIVIRUS_UNAVAILABLE


def test_dangerous_type_is_rejected_before_reaching_the_scanner() -> None:
    """Las comprobaciones baratas van primero: no se gasta análisis en un ejecutable."""

    scanner = FakeScanner()

    resultado = validate_upload(b"MZ\x90\x00" + b"\x00" * 100, filename="x.pdf", scanner=scanner)

    assert not resultado.accepted
    assert scanner.scanned == []


# --- Resultado -------------------------------------------------------------


def test_validation_result_reports_quarantine() -> None:
    resultado = validate_upload(b"", filename="x.pdf")

    assert resultado.quarantined
    assert not resultado.accepted


def test_accepted_result_is_not_quarantined() -> None:
    resultado = validate_upload(make_pdf(), filename="p.pdf")

    assert not resultado.quarantined


# --- XML interno de los documentos de oficina ------------------------------


def test_xml_entity_bomb_is_rejected() -> None:
    """Un XML con entidades anidadas puede agotar la memoria al parsearlo.

    Es el ataque «billion laughs»: cada entidad expande a varias anteriores, de
    modo que un archivo de pocos kilobytes descomprime a gigabytes. Los DOCX y
    XLSX llevan XML dentro, así que la revisión se hace sobre el contenido real.
    """

    bomb = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
]>
<lolz>&lol2;</lolz>"""

    data = make_zip({"[Content_Types].xml": b"<Types/>", "word/document.xml": bomb})

    reason, detail = inspect_archive(data)

    assert reason is QuarantineReason.DANGEROUS_TYPE
    assert "prohibidas" in (detail or "") or "xml" in (detail or "").lower()


def test_valid_docx_xml_passes_inspection() -> None:
    """Un documento normal no debe verse afectado por la revisión de XML."""

    reason, _ = inspect_archive(make_docx())

    assert reason is None


def test_invalid_xml_does_not_reject_the_document() -> None:
    """Un XML que no parsea no es peligroso; el documento se procesa igual."""

    data = make_zip({"[Content_Types].xml": b"<Types/>", "word/document.xml": b"<roto"})

    reason, _ = inspect_archive(data)

    assert reason is None
