"""Constantes compartidas del dominio ART.

Se aíslan aquí (sin dependencias) para poder importarlas tanto desde las rutas
como desde los servicios (p. ej. el generador de PDF) sin riesgo de imports
circulares.
"""
from __future__ import annotations

# Paso 3 del formato oficial: "Reglas que Salvan la Vida".
# Cada regla tiene un `id` estable (se persiste en art_records.reglas_vida_json),
# un `nombre` visible y un icono Font Awesome 6 Free Solid:
#   - `icon_class`: clase CSS para la web (CDN de Font Awesome), p. ej. "fa-truck".
#   - `icon_glyph`: codepoint Unicode del mismo icono para el PDF (fuente fa-solid-900.ttf).
# Los `icon_glyph` se derivaron de la metadata de Font Awesome 6.5.2 y se verificaron contra
# el .ttf vendorizado; si cambia la versión de la fuente hay que re-derivarlos.
# Iconos genéricos aproximados (no pictogramas oficiales de seguridad).
# REEMPLAZAR la lista por el formato exacto de la empresa cuando se entregue.
REGLAS_QUE_SALVAN_LA_VIDA: list[dict[str, str]] = [
    {"id": "trabajos_altura", "nombre": "Trabajos en altura", "icon_class": "fa-person-falling", "icon_glyph": ""},
    {"id": "bloqueo_energias", "nombre": "Aislamiento y bloqueo de energías", "icon_class": "fa-lock", "icon_glyph": ""},
    {"id": "espacios_confinados", "nombre": "Espacios confinados", "icon_class": "fa-door-closed", "icon_glyph": ""},
    {"id": "izaje_cargas", "nombre": "Izaje de cargas", "icon_class": "fa-weight-hanging", "icon_glyph": ""},
    {"id": "vehiculos_equipos_moviles", "nombre": "Vehículos y equipos móviles", "icon_class": "fa-truck", "icon_glyph": ""},
    {"id": "excavaciones", "nombre": "Excavaciones y zanjas", "icon_class": "fa-person-digging", "icon_glyph": ""},
    {"id": "sustancias_peligrosas", "nombre": "Sustancias peligrosas", "icon_class": "fa-skull-crossbones", "icon_glyph": ""},
    {"id": "materiales_fundidos", "nombre": "Materiales fundidos / alta temperatura", "icon_class": "fa-temperature-high", "icon_glyph": ""},
    {"id": "guardas_maquinas", "nombre": "Protección de máquinas y partes en movimiento", "icon_class": "fa-gears", "icon_glyph": ""},
    {"id": "conduccion", "nombre": "Conducción de vehículos", "icon_class": "fa-car", "icon_glyph": ""},
    {"id": "trabajos_caliente", "nombre": "Trabajos en caliente", "icon_class": "fa-fire", "icon_glyph": ""},
    {"id": "energia_electrica", "nombre": "Energía eléctrica / líneas energizadas", "icon_class": "fa-bolt", "icon_glyph": ""},
]

# Conjunto de ids válidos para validar lo que llega de los formularios.
REGLAS_VIDA_IDS: set[str] = {regla["id"] for regla in REGLAS_QUE_SALVAN_LA_VIDA}


# Declaración de condiciones físicas y psicológicas que el supervisor responde al
# crear/editar la ART (mismas que la sección homónima del cuestionario del trabajador).
# Todas deben responderse "Sí" para poder crear la ART.
CONDICIONES_SUPERVISOR: list[dict[str, str]] = [
    {"id": "condicion_fisica_psicologica", "text": "¿Me encuentro en condiciones físicas y psicológicas aptas para realizar la actividad?"},
    {"id": "descansado", "text": "¿Me siento descansado y en condiciones de ejecutar el trabajo?"},
    {"id": "sin_sustancias", "text": "¿No me encuentro bajo efectos de alcohol, drogas o medicamentos que afecten mi desempeño?"},
    {"id": "comprendi_tarea", "text": "¿Comprendí claramente la tarea que debo realizar?"},
]

# Ids válidos de la declaración del supervisor.
CONDICIONES_SUPERVISOR_IDS: list[str] = [c["id"] for c in CONDICIONES_SUPERVISOR]
