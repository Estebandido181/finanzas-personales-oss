"""Contrato HTTP: movimientos."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel
from .categorias import Categoria, OpcionRegla, ReglaAplicada, ReglaPosible
from .comunes import ClaseCategoria, FechaHora, Mes, OrigenCategoria, OrigenMovimiento, TipoMovimiento, TipoRegla


class Movimiento(BaseModel):
    """Un movimiento del mes.

    ``categoria`` es ``null`` si no tiene (pendiente, o ajuste, que no se
    categoriza). Desde el ítem 15 los ingresos también tienen categoría,
    de clase ``ingreso``; ``es_gasto`` sigue diciendo si cuenta como gasto.

    ``origen_categoria`` (ítem 14), solo si tiene ``categoria`` (si no, ``null``):
    ``manual`` (la puso o corrigió el dueño), ``regla`` (una regla recordada)
    o ``desconocido`` (ya estaba categorizado cuando se empezó a guardar este
    dato). ``regla``: la regla que lo categorizó; ``null`` si no fue por
    regla o si esa regla ya se borró (el origen sigue siendo ``regla``).

    Reglas de negocio decididas aquí, no en el frontend: ``pendiente`` (va
    en la bandeja "Sin categorizar"), ``categorizable`` (se le puede asignar
    categoría), ``clase_categoria`` (de qué clase son las categorías que
    acepta; ``null`` si no se categoriza), ``regla_posible`` (la regla por
    texto que crearía ``recordar``, o ``null`` si no se puede crear) y
    ``reglas_posibles`` (ítem 17: las reglas que se ofrecen crear, en orden;
    vacía si ninguna). Las transferencias ofrecen por texto, por monto y las
    dos cosas juntas, igual que los ingresos; las compras, solo por texto.
    """

    id: int
    fecha_hora: FechaHora
    tipo: TipoMovimiento
    descripcion: str
    monto_centavos: int  # ajustes con signo; el resto, positivo
    es_gasto: bool
    categoria: Categoria | None
    origen: OrigenMovimiento
    origen_categoria: OrigenCategoria | None
    regla: ReglaAplicada | None
    pendiente: bool
    categorizable: bool
    clase_categoria: ClaseCategoria | None
    regla_posible: ReglaPosible | None
    reglas_posibles: list[OpcionRegla]
    descartado: bool = False
    puede_descartar: bool = False
    motivo_no_descartar: str | None = None
    puede_restaurar: bool = False
    motivo_no_restaurar: str | None = None


class MovimientosDelMes(BaseModel):
    mes: Mes
    movimientos: list[Movimiento]


class GrupoPendientes(BaseModel):
    """Pendientes iguales que se categorizan juntos (ítem 38), calculado en el servidor.

    "Iguales": mismo tipo y misma descripción normalizada, lo mismo que
    alcanza la regla por texto (``regla``). Nunca mezcla gastos con ingresos;
    siempre son 2 o más. ``clave`` se envía tal cual a ``POST
    /api/movimientos/categorizar-grupo`` con los ``ids``. ``descripcion``: la del
    más reciente. ``suma_centavos``: la suma de sus montos (todos gastos o
    todos ingresos). ``ids``: del más reciente al más antiguo; también están
    en ``movimientos``.
    """

    clave: str
    tipo: TipoRegla
    descripcion: str
    clase_categoria: ClaseCategoria
    es_gasto: bool
    cuantos: int
    suma_centavos: int
    ids: list[int]
    regla: OpcionRegla


class SinCategorizar(BaseModel):
    """Bandeja "Sin categorizar": los pendientes de **todos** los meses.

    Misma forma que la lista del mes (``Movimiento``); todos traen
    ``pendiente: true``. ``grupos`` (ítem 38): los pendientes iguales, del
    grupo más numeroso al menos.
    """

    total: int
    movimientos: list[Movimiento]
    grupos: list[GrupoPendientes]


class EstadoDescarte(BaseModel):
    descartado: bool
    puede_descartar: bool
    motivo_no_descartar: str | None
    puede_restaurar: bool
    motivo_no_restaurar: str | None


class ResultadoDescarte(EstadoDescarte):
    movimiento_id: int
    monto_centavos: int
    saldo_antes_centavos: int | None
    saldo_despues_centavos: int | None


class MovimientoDescartado(EstadoDescarte):
    id: int
    descarte_id: int
    fecha_hora: FechaHora
    tipo: Literal["compra", "transferencia", "ingreso"]
    descripcion: str
    monto_centavos: int
    origen: Literal["gmail", "extracto"]
    referencia: str | None
    descartado_en: FechaHora


class MovimientosDescartados(BaseModel):
    movimientos: list[MovimientoDescartado]
