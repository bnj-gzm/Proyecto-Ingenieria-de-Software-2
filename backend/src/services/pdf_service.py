from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generar_art_pdf(registro: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title=f"ART {registro['id']}")
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"ART/AST Digital N° {registro['id']}", styles["Title"]))
    story.append(Paragraph(registro.get("descripcion") or "Sin descripción", styles["Heading2"]))
    story.append(Spacer(1, 12))

    datos = [
        ["Empresa", registro.get("empresa", "")],
        ["Trabajador", registro.get("trabajador", "")],
        ["Área", registro.get("area", "")],
        ["Fecha", registro.get("fecha", "")],
        ["Tipo de tarea", registro.get("tipo_tarea", "")],
        ["Supervisor", registro.get("supervisor", "")],
        ["Estado", registro.get("estado", "")],
        ["Creado", registro.get("creado_en", "")],
    ]
    story.append(_tabla(datos, [120, 360]))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Checklist", styles["Heading2"]))
    story.append(_lista(registro.get("checklist", [])))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Elementos de protección personal", styles["Heading2"]))
    story.append(_lista(registro.get("epp", [])))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Riesgos y controles", styles["Heading2"]))
    riesgos = registro.get("riesgos", [])
    if riesgos:
        rows = [["Secuencia", "Riesgo", "Control"]]
        for item in riesgos:
            rows.append([item.get("secuencia", ""), item.get("riesgo", ""), item.get("control", "")])
        story.append(_tabla(rows, [150, 165, 165], header=True))
    else:
        story.append(Paragraph("Sin riesgos registrados.", styles["BodyText"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Observaciones", styles["Heading2"]))
    story.append(Paragraph(registro.get("observaciones") or "Sin observaciones.", styles["BodyText"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Revisión", styles["Heading2"]))
    revision = [
        ["Comentario", registro.get("comentario_supervisor") or "Sin comentario."],
        ["Revisado por", registro.get("revisado_por") or "-"],
        ["Fecha revisión", registro.get("revisado_en") or "-"],
    ]
    story.append(_tabla(revision, [120, 360]))

    doc.build(story)
    return buffer.getvalue()


def _lista(items: list[str]):
    styles = getSampleStyleSheet()
    if not items:
        return Paragraph("Sin registros.", styles["BodyText"])
    rows = [[Paragraph(f"• {item}", styles["BodyText"])] for item in items]
    return _tabla(rows, [480])


def _tabla(rows: list[list[str]], widths: list[int], header: bool = False) -> Table:
    table = Table(rows, colWidths=widths)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9") if header else colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold" if header else "Helvetica"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]
    table.setStyle(TableStyle(style))
    return table
