"""Reporte mensual (ítem 06): cuánto se gastó en un mes y en qué.

Recibe servicios prestados y una frontera de lectura consistente; no conoce
SQL ni construye participantes. Los montos son enteros en
centavos; solo la web los convierte a pesos.

Qué es gasto: lo mismo que ``saldo.gasto_entre`` (solo ``compra`` y
``transferencia``). Los ingresos y los ajustes aparecen en la lista de
movimientos del mes, marcados como "no es gasto", pero nunca en el total ni
en el gasto por categoría. Desde el ítem 15 los ingresos también tienen
categoría (de clase ingreso), que se muestra en la lista; los ajustes no.

Ingresos del mes (ítem 13): lo mismo que ``saldo.ingresos_entre`` (solo
``ingreso``, de Gmail y manuales). Los ajustes no son ingreso ni gasto.

Mes: desde las 00:00:00 del día 1 (incluido) hasta las 00:00:00 del día 1
del mes siguiente (excluido), en hora de Colombia, igual que las fechas
guardadas.

Exactitud: la suma de ``por_categoria`` es **exactamente** el total (ambos
son sumas de enteros sobre el mismo conjunto de filas). Todas las consultas se
hacen dentro de una misma transacción de lectura, así una sincronización que
guarde algo entre ellas no puede descuadrarlas. Los porcentajes son solo
para mostrar: se redondean a un decimal y pueden no sumar 100,0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from typing import Protocol
from contextlib import AbstractContextManager

from finanzas.compartido import hora
from finanzas.modulos.saldo.publico import ServicioSaldo
from finanzas.modulos.movimientos.publico import RegistroNormalizado
from finanzas.modulos.categorias.publico import (
    SIN_CATEGORIA_NO_CATEGORIZABLE,
    SIN_CATEGORIZAR,
    es_categorizable,
    es_pendiente,
)
from finanzas.modulos.saldo.publico import TIPOS_GASTO

# "—": lo que no se categoriza (los ajustes). Nombre de antes del ítem 15.
SIN_CATEGORIA_NO_GASTO = SIN_CATEGORIA_NO_CATEGORIZABLE
ANIO_MINIMO = 2000
ANIO_MAXIMO = 2099
MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
MENSAJE_MES_INVALIDO = (
    f"Mes no válido. Usa el formato AAAA-MM, con un año entre {ANIO_MINIMO} y "
    f"{ANIO_MAXIMO} (por ejemplo 2026-09)."
)
_MES = re.compile(r"(?P<anio>[0-9]{4})-(?P<mes>[0-9]{2})")


class ErrorReporte(Exception):
    """Mes no válido. El mensaje es para el dueño."""


@dataclass(frozen=True)
class GastoCategoria:
    nombre: str
    centavos: int
    porcentaje: float  # solo para mostrar, redondeado a un decimal
    # Ítem 15: la categoría (None en "Sin categorizar"), con su color e ícono.
    categoria_id: int | None = None
    color: str | None = None
    icono: str | None = None


@dataclass(frozen=True)
class MovimientoReporte:
    id: int
    fecha_hora: str
    tipo: str
    descripcion: str
    categoria: str  # nombre, "Sin categorizar" o "—" (ajustes)
    monto_centavos: int
    es_gasto: bool
    # Para la API (ítem 10): id de la categoría (None si no tiene o no se
    # categoriza) y origen ("gmail" o "manual"). Ítem 15: clase, color e
    # ícono de la categoría (None si no tiene).
    categoria_id: int | None = None
    origen: str = ""
    categoria_clase: str | None = None
    categoria_color: str | None = None
    categoria_icono: str | None = None
    # Ítem 14: cómo se categorizó ("manual", "regla" o None: sin categoría o
    # categorizado antes de la migración 0004) y la regla, si aún existe.
    origen_categoria: str | None = None
    regla_id: int | None = None
    regla_campo: str | None = None
    regla_texto: str | None = None
    regla_monto_centavos: int | None = None  # ítem 17
    regla_modo_texto: str = "exacta"
    regla_origen_regla: str = "todos"
    regla_texto_visible: str | None = None

    @property
    def pendiente(self) -> bool:
        """Va en la bandeja "Sin categorizar" (``categorizacion.es_pendiente``)."""
        return es_pendiente(self.tipo, self.categoria_id)


@dataclass(frozen=True)
class ReporteMensual:
    anio: int
    mes: int
    total_gasto_centavos: int
    total_ingresos_centavos: int  # solo tipo ingreso; los ajustes no cuentan
    por_categoria: list[GastoCategoria]
    movimientos: list[MovimientoReporte]


# --- Meses ---------------------------------------------------------------------------

def _validar_mes(anio: object, mes: object) -> tuple[int, int]:
    for valor in (anio, mes):
        if not isinstance(valor, int) or isinstance(valor, bool):
            raise ErrorReporte(MENSAJE_MES_INVALIDO)
    if not ANIO_MINIMO <= anio <= ANIO_MAXIMO or not 1 <= mes <= 12:
        raise ErrorReporte(MENSAJE_MES_INVALIDO)
    return anio, mes


def mes_siguiente(anio: int, mes: int) -> tuple[int, int]:
    """El mes que sigue; diciembre pasa a enero del año siguiente."""
    return (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def mes_anterior(anio: int, mes: int) -> tuple[int, int]:
    """El mes anterior; enero pasa a diciembre del año anterior."""
    return (anio - 1, 12) if mes == 1 else (anio, mes - 1)


def en_rango(anio: int, mes: int) -> bool:
    """``True`` si el mes está entre 2000-01 y 2099-12 (lo que acepta ``leer_mes``)."""
    return ANIO_MINIMO <= anio <= ANIO_MAXIMO and 1 <= mes <= 12


def limites_del_mes(anio: int, mes: int) -> tuple[datetime, datetime]:
    """``(desde, hasta)``: 00:00 del día 1 y 00:00 del día 1 del mes siguiente.

    ``desde`` se incluye y ``hasta`` no (``desde <= fecha_hora < hasta``).
    """
    anio, mes = _validar_mes(anio, mes)
    return datetime(anio, mes, 1), datetime(*mes_siguiente(anio, mes), 1)


def mes_actual() -> tuple[int, int]:
    """``(año, mes)`` de hoy en Colombia."""
    hoy = hora.hoy_colombia()
    return hoy.year, hoy.month


def leer_mes(texto: object) -> tuple[int, int]:
    """``"AAAA-MM"`` (lo que envía ``<input type="month">``) a ``(año, mes)``.

    Estricto: exactamente 4 cifras ASCII, guion y 2 cifras; sin espacios. Año
    entre 2000 y 2099 y mes entre 01 y 12. Si no, lanza ``ErrorReporte``.
    """
    if not isinstance(texto, str):
        raise ErrorReporte(MENSAJE_MES_INVALIDO)
    coincidencia = _MES.fullmatch(texto)
    if coincidencia is None:
        raise ErrorReporte(MENSAJE_MES_INVALIDO)
    return _validar_mes(int(coincidencia.group("anio")), int(coincidencia.group("mes")))


def texto_mes(anio: int, mes: int) -> str:
    """``(2026, 9)`` -> ``"2026-09"`` (para enlaces y el ``<input type="month">``)."""
    return f"{anio:04d}-{mes:02d}"


def nombre_mes(anio: int, mes: int) -> str:
    """``(2026, 9)`` -> ``"septiembre de 2026"``, con una tabla propia (sin ``locale``)."""
    return f"{MESES[mes - 1]} de {anio}"


# --- Reporte -------------------------------------------------------------------------

# Transacción de solo lectura: todas las consultas ven la misma foto de la
# base. Vive en ``db`` (depende del motor); se mantiene este nombre.
class DatosReporte(Protocol):
    saldo: ServicioSaldo
    movimientos: RegistroNormalizado

    def lectura(self) -> AbstractContextManager[None]: ...


def es_gasto(tipo: str) -> bool:
    """``True`` si el tipo cuenta como gasto (compras y transferencias)."""
    return tipo in TIPOS_GASTO


def _porcentaje(centavos: int, total: int) -> float:
    """Porcentaje con un decimal, redondeando la mitad hacia arriba, con enteros."""
    decimas = (centavos * 2000 + total) // (2 * total)
    return decimas / 10


def reporte_mensual(datos: DatosReporte, anio: int, mes: int) -> ReporteMensual:
    """Total gastado, total de ingresos, gasto por categoría y movimientos del mes."""
    desde, hasta = limites_del_mes(anio, mes)
    with datos.lectura():
        total = datos.saldo.gasto_entre(desde, hasta)
        ingresos = datos.saldo.ingresos_entre(desde, hasta)
        filas_categoria, filas_movimientos = datos.movimientos.filas_del_periodo(desde, hasta)

    por_categoria = [
        GastoCategoria(
            nombre=fila["nombre"] if fila["nombre"] is not None else SIN_CATEGORIZAR,
            centavos=int(fila["centavos"]),
            porcentaje=_porcentaje(int(fila["centavos"]), total),
            categoria_id=None if fila["id"] is None else int(fila["id"]),
            color=fila["color"],
            icono=fila["icono"],
        )
        for fila in filas_categoria
        if fila["centavos"]
    ]
    # De mayor a menor; a igual monto, por nombre (orden estable entre recargas).
    por_categoria.sort(key=lambda g: (-g.centavos, g.nombre))

    movimientos = []
    for fila in filas_movimientos:
        gasto = es_gasto(fila["tipo"])
        categorizable = es_categorizable(fila["tipo"])
        if not categorizable:
            categoria = SIN_CATEGORIA_NO_GASTO
        else:
            categoria = fila["categoria"] if fila["categoria"] is not None else SIN_CATEGORIZAR
        # Un ajuste nunca muestra categoría (aunque una base vieja tuviera una).
        con_categoria = categorizable and fila["categoria"] is not None
        movimientos.append(
            MovimientoReporte(
                id=int(fila["id"]),
                fecha_hora=str(fila["fecha_hora"]),
                tipo=str(fila["tipo"]),
                descripcion=str(fila["descripcion"]),
                categoria=categoria,
                monto_centavos=int(fila["monto_centavos"]),
                es_gasto=gasto,
                categoria_id=int(fila["categoria_id"]) if con_categoria else None,
                origen=str(fila["origen"]),
                categoria_clase=fila["categoria_clase"] if con_categoria else None,
                categoria_color=fila["categoria_color"] if con_categoria else None,
                categoria_icono=fila["categoria_icono"] if con_categoria else None,
                origen_categoria=fila["origen_categoria"] if con_categoria else None,
                regla_id=(
                    int(fila["regla_id"])
                    if con_categoria and fila["regla_id"] is not None
                    else None
                ),
                regla_campo=fila["regla_campo"] if con_categoria else None,
                regla_texto=fila["regla_texto"] if con_categoria else None,
                regla_monto_centavos=fila["regla_monto_centavos"] if con_categoria else None,
                regla_modo_texto=fila["regla_modo_texto"] or "exacta",
                regla_origen_regla=fila["regla_origen_regla"] or "todos",
                regla_texto_visible=fila["regla_texto_visible"],
            )
        )

    return ReporteMensual(
        anio=anio,
        mes=mes,
        total_gasto_centavos=total,
        total_ingresos_centavos=ingresos,
        por_categoria=por_categoria,
        movimientos=movimientos,
    )


# --- Filtros de la lista de movimientos (ítem 14) ----------------------------------------

# "gasto" agrupa los tipos que cuentan como gasto (``saldo.TIPOS_GASTO``):
# así el frontend no decide qué es un gasto.
FILTRO_GASTO = "gasto"
TIPOS_FILTRO = (FILTRO_GASTO, "compra", "transferencia", "ingreso", "ajuste")


def filtrar_movimientos(
    movimientos: list[MovimientoReporte],
    tipo: str | None = None,
    categoria_id: int | None = None,
    sin_categoria: bool = False,
) -> list[MovimientoReporte]:
    """Los movimientos que pasan todos los filtros, en el mismo orden.

    * ``tipo``: uno de ``TIPOS_FILTRO``; ``"gasto"`` son las compras y las
      transferencias (lo que cuenta como gasto).
    * ``categoria_id``: solo los movimientos con esa categoría (gastos o ingresos).
    * ``sin_categoria``: solo los pendientes del mes (``categorizacion.es_pendiente``).

    ``categoria_id`` y ``sin_categoria`` juntos se contradicen: lanza
    ``ErrorReporte``; también si ``tipo`` no es válido.
    """
    if tipo is not None and tipo not in TIPOS_FILTRO:
        raise ErrorReporte("El tipo de movimiento no es válido.")
    if categoria_id is not None and sin_categoria:
        raise ErrorReporte("No se puede filtrar a la vez por una categoría y por sin categoría.")
    salida = []
    for mov in movimientos:
        if tipo == FILTRO_GASTO and not mov.es_gasto:
            continue
        if tipo not in (None, FILTRO_GASTO) and mov.tipo != tipo:
            continue
        if categoria_id is not None and mov.categoria_id != categoria_id:
            continue
        if sin_categoria and not mov.pendiente:
            continue
        salida.append(mov)
    return salida
