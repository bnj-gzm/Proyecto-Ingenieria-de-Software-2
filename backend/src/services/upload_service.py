from __future__ import annotations

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


def _extension_from_filename(filename: str) -> str:
    return Path(filename or "").suffix.lower()


async def save_art_image(upload_dir: Path, archivo: UploadFile) -> str:
    """Store an ART image locally for the prototype.

    The returned path is relative to frontend/static. This keeps Railway/local URLs
    stable and leaves a narrow swap point for future S3, Cloudinary or GCS storage.
    """
    extension = _extension_from_filename(archivo.filename or "")
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Solo se permiten imágenes JPG, PNG o WEBP")

    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="La imagen adjunta está vacía")
    if len(contenido) > MAX_ART_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Cada imagen debe pesar máximo 5 MB")

    try:
        image = Image.open(io.BytesIO(contenido))
        image.verify()
        if image.format != ALLOWED_IMAGE_EXTENSIONS[extension]:
            raise HTTPException(status_code=400, detail="El contenido de la imagen no coincide con su extensión")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="El archivo adjunto no es una imagen válida") from exc

    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{extension}"
    (upload_dir / filename).write_bytes(contenido)
    return f"uploads/art/{filename}"
