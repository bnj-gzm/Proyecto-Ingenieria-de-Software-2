from pydantic import BaseModel
from typing import Optional, List


class ARTCreate(BaseModel):
    empresa: str
    trabajador: str
    area: str
    fecha: str
    tipo_tarea: str
    descripcion: str
    supervisor: str
    checklist: Optional[List[str]] = []
    epp: Optional[List[str]] = []
    riesgos: Optional[List[str]] = []
    observaciones: Optional[str] = ""


class ARTResponse(ARTCreate):
    id: str
    evidencia: List[str] = []
    estado: str = "pendiente"
    creado_en: str
