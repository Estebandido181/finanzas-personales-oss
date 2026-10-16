"""Resumen de acciones del Inicio, sobre una única lectura de los participantes."""
from typing import Protocol
from contextlib import AbstractContextManager


class DatosInicio(Protocol):
    def lectura(self) -> AbstractContextManager: ...
    def cantidades(self) -> tuple: ...


def estado(datos: DatosInicio) -> dict:
    with datos.lectura():
        cantidades = datos.cantidades()
    areas = [dict(codigo=codigo, titulo=titulo, cantidad=cantidad, href=href)
             for codigo, titulo, cantidad, href in cantidades if cantidad > 0]
    total = sum(area["cantidad"] for area in areas)
    texto = "Todo al día" if total == 0 else (
        "1 cosa por revisar" if total == 1 else f"{total} cosas por revisar"
    )
    return dict(todo_al_dia=total == 0, total_acciones=total, texto=texto, areas=areas)
