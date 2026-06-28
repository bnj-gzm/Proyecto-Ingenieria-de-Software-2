fa-solid-900.ttf
================

Font Awesome 6 Free — estilo Solid (versión 6.5.2).
Fuente: https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/webfonts/fa-solid-900.ttf

Se usa para dibujar los iconos de "Reglas que Salvan la Vida" (Paso 3) en el PDF
generado por backend/src/services/pdf_service.py (registrada con reportlab TTFont).
La web usa el CSS de Font Awesome por CDN (ver frontend/templates/base.html).

Los codepoints de cada icono están en backend/src/constants.py (campo icon_glyph) y
fueron derivados de la metadata de esta misma versión 6.5.2. Si se actualiza esta
fuente, re-derivar los codepoints para mantener la consistencia.

Licencia del archivo de fuente: SIL OFL 1.1 (Font Awesome Free).
https://fontawesome.com/license/free
