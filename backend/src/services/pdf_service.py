from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PAGE_WIDTH = letter[0] - 3 * cm
INK = colors.HexColor("#111827")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#CBD5E1")
SOFT_LINE = colors.HexColor("#E2E8F0")
HEADER_BG = colors.HexColor("#0F3D4C")
SECTION_BG = colors.HexColor("#E0F7FA")
TABLE_HEAD_BG = colors.HexColor("#F1F5F9")


def generar_art_pdf(registro: dict) -> bytes:
    buffer = BytesIO()
    doc = _document(buffer, f"ART {registro['id']}")
    story = []

    story.append(_header_table(
        "ART/AST DIGITAL",
        f"Registro tecnico de trabajo seguro - ART {registro['id']}",
        [
            ("Empresa", registro.get("empresa", "")),
            ("Fecha", registro.get("fecha", "")),
            ("Supervisor", registro.get("supervisor", "")),
        ],
    ))
    story.append(Spacer(1, 12))

    story.append(_section_title("Antecedentes generales"))
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
    story.append(_key_value_table(datos))
    story.append(Spacer(1, 14))

    story.append(_section_title("Checklist de Seguridad"))
    story.append(_lista(registro.get("checklist", [])))
    story.append(Spacer(1, 12))

    story.append(_section_title("Elementos de Proteccion Personal"))
    story.append(_lista(registro.get("epp", [])))
    story.append(Spacer(1, 12))

    story.append(_section_title("Riesgos y controles"))
    riesgos = registro.get("riesgos", [])
    if riesgos:
        rows = [["Secuencia", "Riesgo", "Control"]]
        for item in riesgos:
            rows.append([item.get("secuencia", ""), item.get("riesgo", ""), item.get("control", "")])
        story.append(_data_table(rows, [5.0 * cm, 5.8 * cm, 5.8 * cm]))
    else:
        story.append(_empty("Sin riesgos registrados."))
    story.append(Spacer(1, 12))

    story.append(_section_title("Observaciones"))
    story.append(_note(registro.get("observaciones") or "Sin observaciones."))
    story.append(Spacer(1, 12))

    story.append(_section_title("Revision"))
    revision = [
        ["Comentario", registro.get("comentario_supervisor") or "Sin comentario."],
        ["Revisado por", registro.get("revisado_por") or "-"],
        ["Fecha revisión", registro.get("revisado_en") or "-"],
    ]
    story.append(_key_value_table(revision))

    doc.build(story)
    return buffer.getvalue()


def generar_respuesta_trabajador_pdf(registro: dict, asignacion: dict) -> bytes:
    buffer = BytesIO()
    doc = _document(buffer, f"ART {registro['id']} - {asignacion.get('nombre', 'trabajador')}")
    story = []

    story.append(_header_table(
        "REVISION INDIVIDUAL ART",
        f"Informe tecnico del trabajador - ART {registro['id']}",
        [
            ("Empresa", registro.get("empresa", "")),
            ("Fecha", registro.get("fecha", "")),
            ("Supervisor", registro.get("supervisor", "")),
        ],
    ))
    story.append(Spacer(1, 12))

    story.append(_section_title("Antecedentes de la ART"))
    datos_art = [
        ["Empresa", registro.get("empresa", "")],
        ["Área", registro.get("area", "")],
        ["Tipo de tarea", registro.get("tipo_tarea", "")],
        ["Fecha ART", registro.get("fecha", "")],
        ["Supervisor", registro.get("supervisor", "")],
    ]
    story.append(_key_value_table(datos_art))
    story.append(Spacer(1, 14))

    story.append(_section_title("Datos del trabajador"))
    datos_trabajador = [
        ["Trabajador", asignacion.get("nombre", "")],
        ["RUT", asignacion.get("rut") or "-"],
        ["Cargo", asignacion.get("cargo") or "-"],
        ["Área", asignacion.get("area") or "-"],
        ["Correo", asignacion.get("email") or "-"],
        ["Fecha respuesta", str(asignacion.get("fecha_respuesta") or "-")],
    ]
    story.append(_key_value_table(datos_trabajador))
    story.append(Spacer(1, 12))

    respuestas = (asignacion.get("respuestas") or {}).get("preguntas") or []
    story.append(_section_title("Checklist de Seguridad"))
    if respuestas:
        for section, section_items in _group_questions(respuestas):
            story.append(_subsection_title(section))
            rows = [["Pregunta", "Respuesta", "Observación"]]
            for item in section_items:
                rows.append([
                    item.get("pregunta", ""),
                    str(item.get("respuesta", "")).upper(),
                    item.get("observacion") or "-",
                ])
            story.append(_data_table(rows, [9.1 * cm, 2.8 * cm, 5.0 * cm], alignments={1: "CENTER"}))
            story.append(Spacer(1, 8))
    else:
        story.append(_empty("Sin respuestas registradas."))
    story.append(Spacer(1, 12))

    story.append(_section_title("EPP"))
    story.append(_lista((asignacion.get("respuestas") or {}).get("epp") or []))
    story.append(Spacer(1, 12))

    story.append(_section_title("Observaciones del trabajador"))
    story.append(_note((asignacion.get("respuestas") or {}).get("observaciones") or "Sin observaciones."))
    story.append(Spacer(1, 12))

    story.append(_section_title("Firma digital"))
    firma = "Recibida" if asignacion.get("firma_valor") or asignacion.get("firma_imagen_base64") else "Pendiente"
    story.append(_key_value_table([["Estado firma", firma], ["Confirmación", asignacion.get("firma_valor") or "-"]]))
    story.append(Spacer(1, 12))

    story.append(_section_title("Resultado de revision"))
    revision = [
        ["Resultado", asignacion.get("estado_respuesta", "").upper()],
        ["Comentario supervisor", asignacion.get("comentario_revision") or "Sin comentario."],
        ["Fecha revisión", str(asignacion.get("fecha_revision") or "-")],
    ]
    story.append(_key_value_table(revision))

    doc.build(story)
    return buffer.getvalue()


def _lista(items: list[str]):
    if not items:
        return _empty("Sin registros.")
    rows = [[_p(f"• {item}")] for item in items]
    return _table(rows, [PAGE_WIDTH])


def _document(buffer: BytesIO, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title=title,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
    )


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "ReportBody",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.6,
            leading=11.5,
            textColor=INK,
            spaceAfter=0,
        ),
        "body_muted": ParagraphStyle(
            "ReportBodyMuted",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=11,
            textColor=MUTED,
        ),
        "cell_label": ParagraphStyle(
            "CellLabel",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.4,
            leading=11,
            textColor=colors.HexColor("#334155"),
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.2,
            leading=10.5,
            textColor=colors.white,
            alignment=1,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=HEADER_BG,
            spaceBefore=4,
            spaceAfter=6,
        ),
        "subsection": ParagraphStyle(
            "Subsection",
            parent=sample["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=12,
            textColor=colors.HexColor("#334155"),
            spaceBefore=2,
            spaceAfter=4,
        ),
        "title": ParagraphStyle(
            "ReportTitle",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=19,
            textColor=colors.white,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.8,
            leading=11,
            textColor=colors.HexColor("#DFF7FA"),
        ),
    }


def _p(value: object, style_name: str = "body") -> Paragraph:
    text = escape(str(value if value is not None and value != "" else "-"))
    return Paragraph(text.replace("\n", "<br/>"), _styles()[style_name])


def _section_title(text: str) -> Paragraph:
    return Paragraph(escape(text), _styles()["section"])


def _subsection_title(text: str) -> Paragraph:
    return Paragraph(escape(text or "General"), _styles()["subsection"])


def _empty(text: str) -> Paragraph:
    return _p(text, "body_muted")


def _note(text: str) -> Table:
    return _table([[_p(text)]], [PAGE_WIDTH], background=colors.HexColor("#F8FAFC"))


def _header_table(title: str, subtitle: str, meta: list[tuple[str, object]]) -> Table:
    styles = _styles()
    meta_text = "   |   ".join(f"<b>{escape(label)}:</b> {escape(str(value or '-'))}" for label, value in meta)
    rows = [
        [Paragraph(escape(title), styles["title"])],
        [Paragraph(escape(subtitle), styles["subtitle"])],
        [Paragraph(meta_text, styles["subtitle"])],
    ]
    table = Table(rows, colWidths=[PAGE_WIDTH])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HEADER_BG),
        ("BOX", (0, 0), (-1, -1), 0.8, HEADER_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (0, 0), 10),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ("TOPPADDING", (0, 1), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 2), (0, 2), 10),
    ]))
    return table


def _key_value_table(rows: list[list[object]]) -> Table:
    formatted = [[_p(label, "cell_label"), _p(value)] for label, value in rows]
    return _table(formatted, [4.2 * cm, PAGE_WIDTH - 4.2 * cm], label_column=True)


def _data_table(rows: list[list[object]], widths: list[float], alignments: dict[int, str] | None = None) -> Table:
    formatted = []
    for row_index, row in enumerate(rows):
        style_name = "table_header" if row_index == 0 else "body"
        formatted.append([_p(value, style_name) for value in row])
    return _table(formatted, widths, header=True, alignments=alignments or {})


def _table(
    rows: list[list[object]],
    widths: list[float],
    header: bool = False,
    label_column: bool = False,
    background=colors.white,
    alignments: dict[int, str] | None = None,
) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.45, SOFT_LINE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if header:
        style.extend([
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, 0), 7),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ])
    if label_column:
        style.append(("BACKGROUND", (0, 0), (0, -1), TABLE_HEAD_BG))
    for column, alignment in (alignments or {}).items():
        style.append(("ALIGN", (column, 1 if header else 0), (column, -1), alignment))
    table.setStyle(TableStyle(style))
    return table


def _group_questions(items: list[dict]) -> list[tuple[str, list[dict]]]:
    grouped: list[tuple[str, list[dict]]] = []
    by_name: dict[str, list[dict]] = {}
    for item in items:
        section = item.get("seccion") or item.get("section") or "General"
        if section not in by_name:
            by_name[section] = []
            grouped.append((section, by_name[section]))
        by_name[section].append(item)
    return grouped
