from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UsuarioCreate(BaseModel):
    username: str
    password: str
    rol: str = "user"
    nombre: str = ""
    email: str = ""
    rut: str = ""
    telefono: str = ""
    cargo: str = ""
    empresa: str = ""
    area: str = ""


class UsuarioResponse(BaseModel):
    id: int
    username: str
    rol: str
    nombre: Optional[str] = ""
    email: Optional[str] = ""
    rut: Optional[str] = ""
    telefono: Optional[str] = ""
    cargo: Optional[str] = ""
    empresa: Optional[str] = ""
    area: Optional[str] = ""
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
