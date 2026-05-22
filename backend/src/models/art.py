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
    asignado_a: str = ""
    supervisor_asignado: str = ""
    checklist: Optional[List[str]] = []
    epp: Optional[List[str]] = []
    riesgos: Optional[List[str]] = []
    observaciones: Optional[str] = ""


class ARTResponse(ARTCreate):
    id: str
    evidencia: List[str] = []
    estado: str = "pendiente"
    comentario_supervisor: str = ""
    revisado_por: str = ""
    revisado_en: str = ""
    creado_en: str
