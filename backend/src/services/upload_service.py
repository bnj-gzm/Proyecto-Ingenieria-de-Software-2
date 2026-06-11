from __future__ import annotations

import base64
import io
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image

MAX_ART_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
MIME_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def _extension_from_filename(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def _format_max_mb(size_bytes: int) -> int:
    return max(1, round(size_bytes / (1024 * 1024)))


async def save_art_image(upload_dir: Path, archivo: UploadFile, max_bytes: int = MAX_ART_IMAGE_BYTES) -> dict[str, str]:
    """Validate and encode an ART image for database storage."""
    extension = _extension_from_filename(archivo.filename or "")
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Solo se permiten imágenes JPG, PNG o WEBP")

    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="La imagen adjunta está vacía")
    if len(contenido) > max_bytes:
        raise HTTPException(status_code=400, detail=f"Cada imagen debe pesar máximo {_format_max_mb(max_bytes)} MB")

    try:
        image = Image.open(io.BytesIO(contenido))
        image.verify()
        if image.format != ALLOWED_IMAGE_EXTENSIONS[extension]:
            raise HTTPException(status_code=400, detail="El contenido de la imagen no coincide con su extensión")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="El archivo adjunto no es una imagen válida") from exc

    image_data = base64.b64encode(contenido).decode("ascii")
    image_format = image.format or ALLOWED_IMAGE_EXTENSIONS[extension]
    mime_type = MIME_TYPES.get(image_format, f"image/{image_format.lower()}")
    filename = Path(archivo.filename or f"{uuid.uuid4().hex}{extension}").name
    return {
        "filename": filename,
        "mime_type": mime_type,
        "data": image_data,
        "src": f"data:{mime_type};base64,{image_data}",
    }
