from __future__ import annotations

import base64
import logging
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.src.constants import REGLAS_QUE_SALVAN_LA_VIDA

logger = logging.getLogger("dart.pdf")

PAGE_WIDTH = letter[0] - 3 * cm
INK = colors.HexColor("#111827")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#CBD5E1")
SOFT_LINE = colors.HexColor("#E2E8F0")
HEADER_BG = colors.HexColor("#0F3D4C")
SECTION_BG = colors.HexColor("#E0F7FA")
TABLE_HEAD_BG = colors.HexColor("#F1F5F9")

# Metadatos del formato oficial (caja del encabezado). Ajustar si cambia el documento.
DOC_NUMERO = "SGCI-r-009"
DOC_REVISION = "05"
DOC_VIGENCIA = "26/07/2024"

# frontend/static (para resolver rutas /static/... de logo y evidencia)
_STATIC_DIR = Path(__file__).resolve().parents[3] / "frontend" / "static"

# Fuente de iconos Font Awesome 6 Free Solid (Paso 3). Registro guardado; si el .ttf
# no está disponible, el PDF se genera igual sin iconos (_FA_FONT_OK = False).
_FA_FONT_NAME = "fa-solid"
try:
    pdfmetrics.registerFont(TTFont(_FA_FONT_NAME, str(_STATIC_DIR / "fonts" / "fa-solid-900.ttf")))
    _FA_FONT_OK = True
except Exception:
    logger.warning("No se pudo registrar la fuente Font Awesome para el PDF", exc_info=True)
    _FA_FONT_OK = False


def generar_art_pdf(registro: dict, asignaciones: list[dict] | None = None) -> bytes:
    # obtener_registro ya incrusta las asignaciones en registro["asignaciones"];
    # se acepta el parámetro explícito por compatibilidad y se usa como respaldo.
    if asignaciones is None:
        asignaciones = registro.get("asignaciones") or []
    respondieron = [a for a in asignaciones if (a.get("respuestas") or {}).get("preguntas")]

    buffer = BytesIO()
    doc = _document(buffer, f"ART {registro['id']}")
    story: list = []

    # Encabezado tipo formato oficial (logo + título + caja de documento)
    story.append(_official_header(registro))
    story.append(Spacer(1, 12))

    # Paso 1 — Antecedentes del trabajo realizado
    story.append(_section_title("Paso 1 — Antecedentes del trabajo realizado"))
    antecedentes = [
        ["Empresa", registro.get("empresa") or "PENDIENTE"],
        ["Fecha", registro.get("fecha") or "PENDIENTE"],
        ["Gerencia", registro.get("gerencia") or "PENDIENTE"],
        ["Área", registro.get("area") or "PENDIENTE"],
        ["Horario inicio", registro.get("hora_inicio") or "PENDIENTE"],
        ["Horario término", registro.get("hora_termino") or "PENDIENTE"],
        ["Lugar", registro.get("lugar") or "PENDIENTE"],
        ["Tipo de tarea", registro.get("tipo_tarea") or "PENDIENTE"],
        ["Supervisor", registro.get("supervisor") or "PENDIENTE"],
    ]
    story.append(_key_value_table(antecedentes))
    story.append(Spacer(1, 6))
    story.append(_subsection_title("Actividad a realizar"))
    story.append(_note(registro.get("descripcion") or "PENDIENTE"))
    story.append(Spacer(1, 14))

    # Declaración del supervisor — Condiciones físicas y psicológicas
    story.append(_section_title("Declaración del supervisor — Condiciones físicas y psicológicas"))
    condiciones = registro.get("supervisor_condiciones") or []
    if condiciones:
        rows = [["Condición", "Sí", "No"]]
        for item in condiciones:
            resp = str(item.get("respuesta", "")).strip().lower()
            rows.append([
                item.get("pregunta", ""),
                "X" if resp == "si" else "",
                "X" if resp == "no" else "",
            ])
        story.append(_data_table(rows, [13.0 * cm, 1.8 * cm, 1.8 * cm], alignments={1: "CENTER", 2: "CENTER"}))
    else:
        story.append(_empty("Sin declaración del supervisor registrada."))
    story.append(Spacer(1, 14))

    # Paso 2 — Análisis de riesgos (por trabajador)
    story.append(_section_title("Paso 2 — Análisis de riesgos"))
    if respondieron:
        for asignacion in respondieron:
            story.extend(_worker_analysis_block(asignacion))
    else:
        story.append(_empty("SIN RESPONDER"))
    story.append(Spacer(1, 12))

    # Verificación — Controles de Supervisión (derivado de las respuestas "No")
    story.append(_section_title("Verificación — Controles de Supervisión"))
    novedades = _recopilar_no(respondieron)
    if novedades:
        rows = [["Trabajador", "Condición observada (No)", "Observación"]]
        rows.extend(novedades)
        story.append(_data_table(rows, [4.0 * cm, 7.6 * cm, 5.0 * cm]))
    else:
        story.append(_empty("Sin observaciones: ningún trabajador marcó 'No'."))
    story.append(Spacer(1, 14))

    # Riesgos y controles
    story.append(_section_title("Riesgos y controles"))
    riesgos = registro.get("riesgos", [])
    if riesgos:
        rows = [["Secuencia", "Riesgo", "Control"]]
        for item in riesgos:
            rows.append([item.get("secuencia", ""), item.get("riesgo", ""), item.get("control", "")])
        story.append(_data_table(rows, [5.0 * cm, 5.8 * cm, 5.8 * cm]))
    else:
        story.append(_empty("Sin riesgos registrados."))
    story.append(Spacer(1, 14))

    # Paso 3 — Reglas que Salvan la Vida
    story.append(_section_title("Paso 3 — Reglas que Salvan la Vida"))
    story.append(_p("Reglas que aplican a la tarea (marcadas con X):", "body_muted"))
    story.append(Spacer(1, 4))
    story.append(_reglas_grid(registro.get("reglas_vida", [])))
    story.append(Spacer(1, 6))
    story.append(_subsection_title("Observaciones / medidas de control implementadas"))
    story.append(_note(registro.get("observaciones") or "Sin observaciones."))
    story.append(Spacer(1, 14))

    # Aprobación — Firmas
    story.append(_section_title("Aprobación — Firmas"))
    story.extend(_firmas_block(asignaciones, registro))
    story.append(Spacer(1, 14))

    # Resolución del supervisor
    story.append(_section_title("Resolución del supervisor"))
    revision = [
        ["Estado", str(registro.get("estado") or "PENDIENTE").upper()],
        ["Comentario", registro.get("comentario_supervisor") or "PENDIENTE"],
        ["Revisado por", registro.get("revisado_por") or "PENDIENTE"],
        ["Fecha revisión", registro.get("revisado_en") or "PENDIENTE"],
    ]
    story.append(_key_value_table(revision))

    # Evidencia fotográfica de la ART — al final
    evidencia = registro.get("evidencia", [])
    if evidencia:
        story.append(PageBreak())
        story.append(_section_title("Evidencia fotográfica de la ART"))
        story.append(_evidencia_grid(evidencia))

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


def _load_image_bytes(src: str) -> bytes | None:
    """Devuelve los bytes de una imagen desde un data-URI base64 o una ruta /static/..."""
    if not src:
        return None
    src = str(src).strip()
    if src.startswith("data:"):
        try:
            _, b64 = src.split(",", 1)
            return base64.b64decode(b64)
        except Exception:
            return None
    rel = src.replace("\\", "/")
    if rel.startswith("/static/"):
        rel = rel[len("/static/"):]
    elif rel.startswith("static/"):
        rel = rel[len("static/"):]
    else:
        return None
    try:
        path = (_STATIC_DIR / rel).resolve()
        path.relative_to(_STATIC_DIR.resolve())  # evita path traversal
        if path.exists():
            return path.read_bytes()
    except Exception:
        return None
    return None


def _pdf_image(
    src: str,
    max_width: float,
    max_height: float,
    keep_transparency: bool = False,
) -> Image | None:
    """Convierte una imagen (base64 o /static) a un flowable Image escalado al recuadro dado.

    Por defecto compone sobre blanco y re-codifica a JPEG (PDF liviano). Con
    ``keep_transparency`` (p. ej. el logo sobre el encabezado oscuro) conserva el canal alfa.
    """
    raw = _load_image_bytes(src)
    if not raw:
        return None
    try:
        from PIL import Image as PILImage

        pil = PILImage.open(BytesIO(raw))
        pil.load()
        if keep_transparency:
            if pil.mode != "RGBA":
                pil = pil.convert("RGBA")
            fmt = "PNG"
        else:
            # Componer transparencias sobre blanco (preserva firmas con fondo transparente)
            if pil.mode in ("RGBA", "LA") or (pil.mode == "P" and "transparency" in pil.info):
                fondo = PILImage.new("RGB", pil.size, (255, 255, 255))
                fondo.paste(pil.convert("RGBA"), mask=pil.convert("RGBA").split()[-1])
                pil = fondo
            elif pil.mode != "RGB":
                pil = pil.convert("RGB")
            fmt = "JPEG"
        # Redimensionar acorde al recuadro de salida (~3x px/pt para nitidez de impresión)
        objetivo = max(64, min(int(max(max_width, max_height) * 3), 1600))
        pil.thumbnail((objetivo, objetivo))
        ancho, alto = pil.size
        if ancho <= 0 or alto <= 0:
            return None
        out = BytesIO()
        if fmt == "JPEG":
            pil.save(out, format="JPEG", quality=80, optimize=True)
        else:
            pil.save(out, format="PNG", optimize=True)
        out.seek(0)
    except Exception:
        logger.warning("No se pudo procesar una imagen para el PDF", exc_info=True)
        return None
    escala = min(max_width / ancho, max_height / alto)
    return Image(out, width=ancho * escala, height=alto * escala)


def _official_header(registro: dict) -> Table:
    styles = _styles()
    logo = _pdf_image("/static/img/logo-dart.png", 2.2 * cm, 1.8 * cm, keep_transparency=True)
    logo_cell = logo if logo is not None else Paragraph("ART", styles["title"])
    titulo_cell = [
        Paragraph("ART", styles["title"]),
        Paragraph("Utilicemos las Reglas que Salvan la Vida", styles["subtitle"]),
    ]
    meta = (
        f"<b>N° Doc:</b> {escape(DOC_NUMERO)}<br/>"
        f"<b>Rev:</b> {escape(DOC_REVISION)}<br/>"
        f"<b>Vigencia:</b> {escape(DOC_VIGENCIA)}<br/>"
        f"<b>ART:</b> {escape(str(registro.get('id', '')))}"
    )
    meta_cell = Paragraph(meta, styles["subtitle"])
    table = Table(
        [[logo_cell, titulo_cell, meta_cell]],
        colWidths=[2.8 * cm, PAGE_WIDTH - 2.8 * cm - 5.2 * cm, 5.2 * cm],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HEADER_BG),
        ("BOX", (0, 0), (-1, -1), 0.8, HEADER_BG),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return table


def _worker_analysis_block(asignacion: dict) -> list:
    elems: list = [
        _subsection_title(
            f"Trabajador: {asignacion.get('nombre', '-')} "
            f"({asignacion.get('cargo') or 'Sin cargo'})"
        )
    ]
    respuestas = (asignacion.get("respuestas") or {}).get("preguntas") or []
    if not respuestas:
        elems.append(_empty("Sin respuestas registradas."))
        return elems
    for section, items in _group_questions(respuestas):
        rows = [["Pregunta", "Sí", "No", "Observación"]]
        for item in items:
            resp = str(item.get("respuesta", "")).strip().lower()
            rows.append([
                item.get("pregunta", ""),
                "X" if resp == "si" else "",
                "X" if resp == "no" else "",
                item.get("observacion") or "-",
            ])
        bloque = [
            _p(section, "cell_label"),
            _data_table(rows, [8.8 * cm, 1.1 * cm, 1.1 * cm, 4.6 * cm], alignments={1: "CENTER", 2: "CENTER"}),
            Spacer(1, 6),
        ]
        elems.append(KeepTogether(bloque))
    elems.append(Spacer(1, 4))
    return elems


def _recopilar_no(asignaciones: list[dict]) -> list[list[str]]:
    filas: list[list[str]] = []
    for asignacion in asignaciones:
        nombre = asignacion.get("nombre", "-")
        for item in (asignacion.get("respuestas") or {}).get("preguntas") or []:
            if str(item.get("respuesta", "")).strip().lower() == "no":
                filas.append([nombre, item.get("pregunta", ""), item.get("observacion") or "-"])
    return filas


def _reglas_grid(seleccionadas: list[str] | None) -> Table:
    seleccion = set(seleccionadas or [])
    style = _styles()["body"]
    sep = "  "  # espacios no separables entre icono / casilla / nombre
    celdas = []
    for regla in REGLAS_QUE_SALVAN_LA_VIDA:
        marca = "X" if regla["id"] in seleccion else " "
        glyph = regla.get("icon_glyph") or ""
        icono = (
            f'<font name="{_FA_FONT_NAME}" color="#0F3D4C">{glyph}</font>{sep}'
            if _FA_FONT_OK and glyph
            else ""
        )
        celdas.append(Paragraph(f"{icono}[{marca}]{sep}{escape(regla['nombre'])}", style))
    rows = []
    for i in range(0, len(celdas), 2):
        pareja = celdas[i:i + 2]
        if len(pareja) == 1:
            pareja.append(_p(""))
        rows.append(pareja)
    return _table(rows, [PAGE_WIDTH / 2, PAGE_WIDTH / 2])


def _firma_cell(nombre: str, firma_b64: str | None, firma_valor: str | None) -> list:
    contenido: list = [_p(nombre, "cell_label")]
    img = None
    if firma_b64:
        src = firma_b64 if str(firma_b64).startswith("data:") else f"data:image/png;base64,{firma_b64}"
        img = _pdf_image(src, PAGE_WIDTH / 2 - 1.4 * cm, 2.0 * cm)
    if img is not None:
        contenido.append(img)
    elif firma_valor:
        contenido.append(_p(f"Firma: {firma_valor}"))
    else:
        contenido.append(_p("Firma: SIN RESPONDER", "body_muted"))
    return contenido


def _firmas_block(asignaciones: list[dict], registro: dict) -> list:
    elems: list = []
    celdas = [
        _firma_cell(a.get("nombre", "-"), a.get("firma_imagen_base64"), a.get("firma_valor"))
        for a in asignaciones
    ]
    if celdas:
        rows = []
        for i in range(0, len(celdas), 2):
            pareja = celdas[i:i + 2]
            if len(pareja) == 1:
                pareja.append("")
            rows.append(pareja)
        elems.append(_table(rows, [PAGE_WIDTH / 2, PAGE_WIDTH / 2]))
    else:
        elems.append(_empty("Sin firmas de trabajadores registradas."))
    elems.append(Spacer(1, 8))
    elems.append(_table(
        [[_firma_cell(
            f"Supervisor a cargo: {registro.get('supervisor') or '-'}",
            None,
            registro.get("revisado_por"),
        )]],
        [PAGE_WIDTH],
    ))
    return elems


def _evidencia_grid(evidencia: list[dict]) -> Table | Paragraph:
    box_w = PAGE_WIDTH / 2 - 0.4 * cm
    celdas = []
    for item in evidencia:
        img = _pdf_image(item.get("src", ""), box_w, 7.0 * cm)
        if img is None:
            continue
        celdas.append([img, _p(item.get("filename", ""), "body_muted")])
    if not celdas:
        return _empty("Sin evidencia adjunta.")
    rows = []
    for i in range(0, len(celdas), 2):
        pareja = celdas[i:i + 2]
        if len(pareja) == 1:
            pareja.append("")
        rows.append(pareja)
    return _table(rows, [PAGE_WIDTH / 2, PAGE_WIDTH / 2])


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
