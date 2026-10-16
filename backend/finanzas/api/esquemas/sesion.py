"""Contrato HTTP: sesion."""
from __future__ import annotations
from typing import Annotated
from pydantic import BaseModel, Field, StrictStr
from .comunes import Entrada


class Usuario(BaseModel):
    """El usuario de la sesión (D20). Hoy siempre el dueño."""

    id: str
    nombre: str


class LoginEntrada(Entrada):
    contrasena: Annotated[StrictStr, Field(max_length=1024)]


class Sesion(BaseModel):
    """Sesión iniciada. ``csrf_token`` va en el encabezado ``X-CSRF-Token`` de todo lo que cambia datos."""

    usuario: Usuario
    csrf_token: str
