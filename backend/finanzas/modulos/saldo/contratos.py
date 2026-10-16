"""Datos y puertos de Saldo, sin conexiones ni HTTP."""
from __future__ import annotations
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from finanzas.modulos.movimientos.publico import RegistroSaldo


class ErrorSaldo(Exception):
    """Dato no válido o acción no permitida. El mensaje es para el dueño."""


class SaldoNoConfigurado(ErrorSaldo):
    """Todavía no hay saldo inicial ni fecha de inicio."""

    def __init__(self, mensaje: str | None = None) -> None:
        super().__init__(
            mensaje or "Todavía no has configurado el saldo inicial ni la fecha de inicio."
        )


class MovimientoNoEncontrado(ErrorSaldo):
    """El movimiento que se quiere borrar no existe (ítem 16)."""


class BorradoNoPermitido(ErrorSaldo):
    """El movimiento existe pero no se puede borrar (ítem 16): ajuste, Gmail o anterior al último ajuste."""


@dataclass(frozen=True)
class Configuracion:
    saldo_inicial_centavos: int
    fecha_inicio: date


@dataclass(frozen=True)
class Desglose:
    """Cómo se llega al saldo actual (todo desde la fecha de inicio, en centavos).

    ``saldo_centavos = saldo_inicial + ingresos − gastos + ajustes``; ``gastos``
    es positivo y ``ajustes`` lleva su signo (D9).
    """

    saldo_inicial_centavos: int
    ingresos_centavos: int
    gastos_centavos: int
    ajustes_centavos: int

    @property
    def saldo_centavos(self) -> int:
        return (
            self.saldo_inicial_centavos
            + self.ingresos_centavos
            - self.gastos_centavos
            + self.ajustes_centavos
        )


@dataclass(frozen=True)
class CopiaIngreso:
    """Un ingreso manual borrado, para poder restaurarlo (ítem 38).

    ``fila``: la fila **completa** de ``movimientos``, todas las columnas que
    tenga la tabla (``SELECT *``), también las que agreguen migraciones
    posteriores (p. ej. ``estado`` del ítem 29): se vuelve a insertar tal cual.
    ``categoria_nombre`` y ``categoria_clase``: los de su categoría al borrarlo
    (``None`` si no tenía), para notar si SQLite le dio ese id a otra.
    """

    fila: dict
    categoria_nombre: str | None = None
    categoria_clase: str | None = None
    # Ítem 29: la última importación del banco al borrarlo (0 si no había).
    # Si después se importó otro reporte, ese reporte no lo vio y pudo agregar
    # su depósito sin aviso: restaurarlo lo contaría dos veces.
    ultima_importacion_id: int = 0

    @property
    def id(self) -> int:
        return int(self.fila["id"])

    @property
    def fecha_hora(self) -> str:
        return str(self.fila["fecha_hora"])

    @property
    def monto_centavos(self) -> int:
        return int(self.fila["monto_centavos"])

    @property
    def categoria_id(self) -> int | None:
        valor = self.fila.get("categoria_id")
        return None if valor is None else int(valor)


class RestauracionNoPermitida(ErrorSaldo):
    """El ingreso borrado ya no se puede restaurar (algo cambió mientras tanto)."""



class ConfiguracionSaldo(Protocol):
    def leer(self) -> Configuracion | None: ...
    def guardar(self, monto: int, inicio: date) -> None: ...


class TiempoSaldo(Protocol):
    def ahora(self) -> datetime: ...
    def hoy(self) -> date: ...
    def a_hora(self, momento: datetime) -> datetime: ...


class UnidadSaldo(Protocol):
    saldo: ConfiguracionSaldo
    movimientos: RegistroSaldo
    def escritura(self, inmediata: bool = False) -> AbstractContextManager[None]: ...
    def lectura(self) -> AbstractContextManager[None]: ...
