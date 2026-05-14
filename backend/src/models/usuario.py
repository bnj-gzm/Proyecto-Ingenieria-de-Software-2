from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UsuarioCreate(BaseModel):
    username: str
    password: str
    rol: str


class UsuarioResponse(BaseModel):
    id: int
    username: str
    rol: str
    nombre: Optional[str] = ""
    email: Optional[str] = ""
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
