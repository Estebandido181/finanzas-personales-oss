"""Contrato HTTP: inicio."""
from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, Field


class AreaRevisionInicio(BaseModel):
    codigo: Literal["sin_categoria", "no_reconocidos", "sincronizacion_fallida", "preguntas", "no_en_banco"]
    titulo: str
    cantidad: Annotated[int, Field(ge=1)]
    href: Literal["/movimientos?vista=sin-categorizar", "/no-reconocidos", "/", "/conciliacion/preguntas", "/conciliacion/no-esta-en-el-banco"]


class EstadoInicio(BaseModel):
    todo_al_dia: bool
    total_acciones: Annotated[int, Field(ge=0)]
    texto: str
    areas: list[AreaRevisionInicio]
