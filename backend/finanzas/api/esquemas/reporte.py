"""Contrato HTTP: reporte."""
from __future__ import annotations
from pydantic import BaseModel
from .categorias import Categoria
from .comunes import Mes


class GastoCategoria(BaseModel):
    """Gasto de una categoría en el mes.

    ``nombre`` puede ser "Sin categorizar"; entonces ``categoria`` es ``null``.
    """

    nombre: str
    centavos: int
    porcentaje: float  # solo para mostrar, con un decimal; pueden no sumar 100,0
    categoria: Categoria | None  # null en "Sin categorizar" (ítem 15)


class Reporte(BaseModel):
    """Resumen del mes. ``mes_anterior``/``mes_siguiente`` son ``null`` fuera del rango admitido."""

    mes: Mes
    nombre_mes: str
    es_mes_actual: bool
    mes_anterior: Mes | None
    mes_siguiente: Mes | None
    total_gasto_centavos: int
    # Ingresos del mes (tipo ingreso, de Gmail y manuales). Los ajustes no
    # cuentan ni aquí ni en el gasto.
    total_ingresos_centavos: int
    por_categoria: list[GastoCategoria]
    # La bandeja "Sin categorizar" de **todos** los meses, no solo el mes
    # pedido. ``pendientes``: cuántos, gastos e ingresos (ítem 15). Los
    # montos van aparte y nunca se suman entre sí: ``pendientes_centavos``,
    # solo compras y transferencias; ``pendientes_ingresos_centavos``, solo
    # ingresos.
    pendientes: int
    pendientes_centavos: int
    pendientes_ingresos_centavos: int
    saldo_centavos: int | None  # null si el saldo no está configurado
