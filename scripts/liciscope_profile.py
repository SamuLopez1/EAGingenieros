"""Datos empresariales ficticios para el entorno de grabación de Liciscope."""

from datetime import date
from io import BytesIO
from textwrap import wrap
from uuid import UUID

from app.profile import Entry, EvidenceReference
from reportlab.pdfgen import canvas


def profile_pack(document_id: UUID) -> tuple[list[Entry], bytes]:
    """Genera fichas ficticias y un PDF con un localizador estable por registro."""
    period_start, period_end = date(2026, 12, 1), date(2027, 3, 31)
    service = "Interventoría"
    entries = [
        Entry(
            category="experiencia",
            title="Adecuaciones escolares · caso sintético",
            service_line=service,
            amount=10,
            unit="meses",
            starts_on=date(2025, 2, 1),
            ends_on=date(2025, 11, 30),
            description="Seguimiento de reparación de cubiertas, redes y acabados. "
            "La ficha ficticia contempla actas de avance, informes de visita "
            "y cierre de observaciones técnicas.",
        ),
        Entry(
            category="experiencia",
            title="Mantenimiento de sedes educativas · caso sintético",
            service_line=service,
            amount=7,
            unit="meses",
            starts_on=date(2025, 4, 1),
            ends_on=date(2025, 10, 31),
            description="Control de cantidades, revisión de cronograma y seguimiento de "
            "la seguridad en obra durante adecuaciones de infraestructura educativa.",
        ),
        Entry(
            category="capacidad",
            title="Seguimiento de obra pública · capacidad sintética",
            service_line=service,
            description="Procedimiento de visitas, verificación de cantidades de obra, "
            "control técnico, administrativo, financiero y ambiental, y seguimiento "
            "de hallazgos hasta su cierre.",
        ),
        Entry(
            category="equipo",
            title="Equipos para inspección de obra · inventario sintético",
            service_line=service,
            amount=2,
            unit="kits",
            description="Dos kits ficticios con medidor láser, cámara, elementos de protección "
            "personal y formatos de inspección. Disponibilidad sujeta a reserva interna.",
        ),
        Entry(
            category="disponibilidad",
            title="Dirección de interventoría · disponibilidad sintética",
            service_line=service,
            role="Director de interventoría",
            dedication_percent=50,
            starts_on=period_start,
            ends_on=period_end,
            description=(
                "Reserva ficticia para revisión de informes, comités y control contractual."
            ),
        ),
        Entry(
            category="disponibilidad",
            title="Residencia de interventoría · disponibilidad sintética",
            service_line=service,
            role="Residente de interventoría",
            dedication_percent=100,
            starts_on=period_start,
            ends_on=period_end,
            description="Reserva ficticia para visitas, control de ejecución y bitácora de obra.",
        ),
        Entry(
            category="disponibilidad",
            title="Apoyo ambiental · disponibilidad sintética",
            service_line=service,
            role="Especialista ambiental",
            dedication_percent=25,
            starts_on=period_start,
            ends_on=period_end,
            description="Proyección ficticia pendiente de asignación. Evaluar reasignación o "
            "contratación para cubrir visitas y seguimiento del plan ambiental.",
        ),
        Entry(
            category="financiero",
            title="Capital de trabajo · supuesto sintético",
            amount=80_000_000,
            unit="COP",
            description="Importe ilustrativo para la demostración. Debe validarse con Finanzas "
            "antes de usarlo en un escenario o frente a un indicador del pliego.",
        ),
    ]
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, invariant=True)
    pdf.setTitle("Liciscope | Perfil de demostración y evidencias sintéticas")
    pdf.setAuthor("Liciscope")
    for page, entry in enumerate(entries, 1):
        status = "verificado" if page <= 6 else "pendiente"
        entries[page - 1] = Entry.model_validate(
            {
                **entry.model_dump(),
                "status": status,
                "evidence": [EvidenceReference(document_id=document_id, locator=f"Página {page}")],
            }
        )
        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawString(48, 778, "Liciscope | EVIDENCIA SINTÉTICA")
        pdf.setFont("Helvetica", 11)
        lines = [
            "Ejercicio académico. Datos ficticios sin valor probatorio.",
            entry.title,
            entry.description,
        ]
        if entry.amount is not None:
            lines.append(f"Valor de demostración: {entry.amount} {entry.unit}.")
        if entry.role:
            lines.append(f"Cargo: {entry.role}. Dedicación: {entry.dedication_percent} %.")
        if entry.starts_on and entry.ends_on:
            lines.append(f"Periodo: {entry.starts_on} a {entry.ends_on}.")
        lines.append(f"Revisión del dato dentro del ejercicio: {status}.")
        y = 744
        for paragraph in lines:
            for line in wrap(paragraph, width=92):
                pdf.drawString(48, y, line)
                y -= 17
            y -= 9
        pdf.drawString(48, 48, f"Perfil privado de demostración · Página {page}")
        pdf.showPage()
    pdf.save()
    return entries, buffer.getvalue()
