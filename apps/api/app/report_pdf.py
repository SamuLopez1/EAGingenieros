"""Render privado del informe de comparación aprobado."""

from dataclasses import dataclass
from datetime import datetime
from html import escape
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo

from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib.styles import ParagraphStyle  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

from app.comparison import Audit, Row
from app.documents.extraction import Locator
from app.documents.requirements import Analysis, Citation

INK = colors.HexColor("#16354a")
LIGHT = colors.HexColor("#e8f2f5")
BORDER = colors.HexColor("#d5e1e5")
LABELS: dict[str, str] = {
    "objeto": "Objeto",
    "entregable": "Entregable",
    "plazo": "Plazo",
    "alerta": "Alerta",
    "habilitante": "Habilitante",
    "evaluable": "Evaluable",
    "obligacion": "Obligación",
    "cumple": "Cumple",
    "cumple_parcialmente": "Cumple parcialmente",
    "no_cumple": "No cumple",
    "revision_manual": "Revisión manual",
}
WARNINGS: dict[str, str] = {
    "sin_pliego_seleccionado": "Falta seleccionar un pliego disponible.",
    "documentos_sin_seleccionar": "Hay documentos fuera de la selección.",
    "referencia_oficial_sin_seleccionar": "Hay referencias oficiales fuera de la selección.",
    "version_mas_reciente_disponible": "Hay una versión documental más reciente.",
    "documento_no_disponible": "Un documento de la selección no está disponible.",
    "extraccion_incompleta": "La extracción de uno o más documentos es incompleta.",
    "posible_contradiccion_adenda": "Posible contradicción entre el pliego y una adenda.",
    "revisar_precedencia_adendas": "Confirma la precedencia de las adendas.",
    "limite_documentos": "La cantidad de documentos supera el límite de análisis.",
    "limite_texto_fuente": "Se alcanzó el límite de texto de origen.",
    "sin_objeto_confirmado": "Objeto pendiente de confirmar.",
    "sin_entregable_confirmado": "Entregables pendientes de confirmar.",
    "sin_plazo_confirmado": "Plazos pendientes de confirmar.",
    "sin_requisitos_confirmados": "Requisitos pendientes de confirmar.",
    "documento_sin_hallazgos": "Un documento no produjo hallazgos citables.",
}


@dataclass(frozen=True)
class ApprovedReport:
    opportunity_id: int
    reference: str
    title: str
    approval: Audit
    analysis: Analysis
    rows: list[Row]
    expires_at: datetime


def clean(text: str) -> str:
    return "".join(char for char in text if char.isprintable() or char in "\n\t")


def where(locator: Locator) -> str:
    if locator.page is not None:
        return f"página {locator.page}"
    if locator.sheet is not None:
        return f"hoja {locator.sheet}" + (f", {locator.cell}" if locator.cell else "")
    parts = [
        f"sección {locator.section}" if locator.section else "",
        f"párrafo {locator.paragraph}" if locator.paragraph else "",
        f"tabla {locator.table}" if locator.table else "",
        f"fila {locator.row}" if locator.row else "",
        f"columna {locator.column}" if locator.column else "",
    ]
    return ", ".join(filter(None, parts)) or "localizador pendiente"


def source(cite: Citation) -> str:
    location = " ".join(where(cite.locator).split())
    quote = " ".join(cite.quote.split())
    return f"{cite.title} | v{cite.version} | {location}\n{quote}"


def footer(canvas: Canvas, _document: Any, *, company: str) -> None:
    canvas.saveState()
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(40, 26, f"{company}  |  Informe privado")
    canvas.drawRightString(A4[0] - 40, 26, f"Página {canvas.getPageNumber()}")
    canvas.restoreState()


def render(report: ApprovedReport, *, company: str = "EAG Ingenieros") -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=44,
        bottomMargin=46,
        title=f"{company} | Informe aprobado",
        author=company,
    )
    body = ParagraphStyle("Body", fontName="Helvetica", fontSize=9, leading=13, textColor=INK)
    tiny = ParagraphStyle("TableBody", parent=body, fontSize=8, leading=11, splitLongWords=True)
    h1 = ParagraphStyle("Header", parent=body, fontName="Helvetica-Bold", fontSize=24, leading=28)
    h2 = ParagraphStyle(
        "Section",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        spaceBefore=13,
        spaceAfter=5,
        keepWithNext=True,
    )

    def paragraph(text: str, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(escape(clean(text), quote=False).replace("\n", "<br/>"), style)

    approval = report.approval
    when = approval.created_at.astimezone(ZoneInfo("America/Bogota"))
    story: list[Any] = [
        paragraph(company.upper()),
        Spacer(1, 7),
        paragraph("Informe de comparación aprobado", h1),
        Spacer(1, 8),
        paragraph(report.title),
        paragraph(f"Oportunidad {report.opportunity_id}  |  Referencia {report.reference}"),
        paragraph(
            f"Revisión {approval.revision}  |  Perfil v{approval.profile_version}  |  "
            f"Aprobación {when:%Y-%m-%d %H:%M} (Colombia)"
        ),
        paragraph(f"Aprobador: {approval.actor_id}"),
        paragraph(f"Huella de la comparación: {approval.fingerprint}"),
    ]
    if approval.reason:
        story.append(paragraph(f"Nota de aprobación: {approval.reason}"))
    story.append(paragraph("Resumen documentado", h2))
    for finding in report.analysis.summary:
        story.append(paragraph(f"{LABELS[finding.kind]}: {source(finding.citation)}"))
    if not report.analysis.summary:
        story.append(paragraph("Resumen pendiente de confirmar con el expediente."))
    story.append(paragraph("Limitaciones y revisión", h2))
    if report.analysis.incomplete:
        story.append(paragraph("El expediente tiene cobertura incompleta."))
    for warning in report.analysis.warnings:
        story.append(paragraph(WARNINGS.get(warning.code, "Dato pendiente de comprobación.")))
        for cite in warning.citations:
            story.append(paragraph(source(cite), tiny))
    story.append(paragraph("La aprobación registra la revisión humana de esta matriz."))
    matrix_heading = ParagraphStyle("MatrixHeader", parent=h2, keepWithNext=False)
    story.append(paragraph("Matriz de requisitos y evidencias", matrix_heading))
    cells = [
        [
            paragraph(title, tiny)
            for title in ("Resultado", "Cita del expediente", f"Respaldo de {company}")
        ]
    ]
    for index, row in enumerate(report.rows, 1):
        findings = [
            f"{' '.join(entry.title.split())}\n"
            f"{' '.join(item.locator.split())} | documento {item.document_id}"
            for entry in row.profile_sources
            for item in entry.evidence
        ]
        outcome = f"{LABELS[row.kind]}\n{LABELS[row.outcome]}\n" + " ".join(row.reason.split())
        cells.append(
            [
                paragraph(outcome, tiny),
                paragraph(source(row.citation), tiny),
                paragraph("\n\n".join(findings[:2]) or "Evidencia empresarial pendiente.", tiny),
            ]
        )
        for offset in range(2, len(findings), 2):
            cells.append(
                [
                    paragraph(f"Requisito {index} (continuación)", tiny),
                    paragraph("", tiny),
                    paragraph("\n\n".join(findings[offset : offset + 2]), tiny),
                ]
            )
    grid = LongTable(
        cells,
        colWidths=[102, 204, doc.width - 318],
        repeatRows=1,
        splitByRow=1,
        hAlign="LEFT",
    )
    grid.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
            ]
        )
    )
    story.extend((grid, paragraph("Versiones del expediente", h2)))
    for version in approval.document_versions:
        story.append(
            paragraph(f"{version.id}  |  v{version.version}\nSHA-256 {version.sha256}", tiny)
        )
    def company_footer(canvas: Canvas, document: Any) -> None:
        footer(canvas, document, company=company)

    doc.build(story, onFirstPage=company_footer, onLaterPages=company_footer)
    return output.getvalue()
