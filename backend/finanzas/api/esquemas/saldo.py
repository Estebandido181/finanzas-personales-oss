"""Contrato HTTP: saldo."""
from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, Field, StrictStr
from .comunes import CentavosNoNegativos, CentavosPositivos, Entrada, Fecha, FechaHora, Mes, OrigenMovimiento
from .deshacer import Deshacer


class ConfiguracionSaldo(BaseModel):
    saldo_inicial_centavos: int
    fecha_inicio: Fecha


class ConfigurarSaldoEntrada(Entrada):
    saldo_inicial_centavos: CentavosNoNegativos
    fecha_inicio: Annotated[StrictStr, Field(max_length=10, json_schema_extra={"format": "date"})]


class IngresoOAjuste(BaseModel):
    id: int
    fecha_hora: FechaHora
    tipo: Literal["ingreso", "ajuste"]
    descripcion: str
    monto_centavos: int


class DesgloseSaldo(BaseModel):
    """"Ver cómo se calcula": ``saldo_centavos = saldo_inicial + ingresos − gastos + ajustes``.

    Todo desde la fecha de inicio. ``gastos_centavos`` es positivo (compras y
    transferencias); ``ajustes_centavos`` lleva su signo.
    """

    saldo_inicial_centavos: int
    ingresos_centavos: int
    gastos_centavos: int
    ajustes_centavos: int


class IngresoOAjusteDelMes(IngresoOAjuste):
    """Fila de "Ingresos y ajustes del mes".

    ``se_puede_borrar`` lo decide el backend (ingreso manual sin ningún ajuste
    posterior); el frontend solo muestra el botón "Borrar ingreso" si es ``true``.
    """

    origen: OrigenMovimiento
    se_puede_borrar: bool


class AjustesDelMes(BaseModel):
    """"Total de ajustes del mes": suma con signo y cuántos son."""

    total_centavos: int
    cantidad: int


class IngresoBorrado(BaseModel):
    """Resultado de borrar un ingreso: el saldo bajó exactamente ``monto_centavos``.

    ``saldo_centavos`` es el saldo justo después (``null`` solo si no hay saldo configurado).
    """

    id: int
    monto_centavos: int
    saldo_centavos: int | None
    deshacer: Deshacer


class Saldo(BaseModel):
    """Pantalla de saldo.

    Sin configurar, solo ``configuracion`` (``null``), ``hoy``, ``mes``,
    ``nombre_mes`` y ``maximo_descripcion`` tienen sentido (las listas van
    vacías y lo demás en ``null``). ``token_ingreso`` es de un solo uso: se
    envía al registrar un ingreso (evita registrarlo dos veces) y cada
    lectura emite uno nuevo.

    Ítem 16: ``desglose`` (cómo se calcula el saldo), ``del_mes`` (ingresos y
    ajustes del mes actual en Colombia, del más reciente al más antiguo) y
    ``ajustes_del_mes``. ``ultimos`` se mantiene para quien ya lo usa.

    ``configuracion_fija``: ``true`` si el saldo inicial y la fecha de inicio
    ya no se pueden cambiar (``PUT /api/saldo/configuracion`` respondería
    400). Sale de la misma regla que usa el PUT (``saldo.configuracion_fija``):
    la pantalla no debe deducirlo del desglose.
    """

    configuracion: ConfiguracionSaldo | None
    configuracion_fija: bool
    saldo_centavos: int | None
    desglose: DesgloseSaldo | None
    mes: Mes
    nombre_mes: str
    del_mes: list[IngresoOAjusteDelMes]
    ajustes_del_mes: AjustesDelMes | None
    ultimos: list[IngresoOAjuste]
    token_ingreso: str | None
    fecha_hora_minima: FechaHora | None  # un ingreso no puede ser anterior
    ahora: FechaHora  # hora actual de Colombia
    hoy: Fecha
    maximo_descripcion: int


class IngresoEntrada(Entrada):
    monto_centavos: CentavosPositivos
    fecha_hora: Annotated[StrictStr, Field(max_length=19, examples=["2026-09-15T14:32"])]
    descripcion: Annotated[StrictStr, Field(max_length=1000)] = ""
    token: Annotated[StrictStr, Field(max_length=100)]


class IngresoRegistrado(BaseModel):
    id: int
    monto_centavos: int


class AjusteEntrada(Entrada):
    saldo_real_centavos: CentavosNoNegativos


class Ajuste(BaseModel):
    """``registrado`` es ``false`` si el saldo ya coincidía (no se guarda un ajuste de 0)."""

    registrado: bool
    diferencia_centavos: int
    saldo_centavos: int
