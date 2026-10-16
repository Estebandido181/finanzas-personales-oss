"""Participantes del arranque, sin conexiones ni tipos HTTP."""
from contextlib import AbstractContextManager
from typing import Protocol
from finanzas.modulos.saldo.publico import ServicioSaldo, ConfiguracionHistorial
from finanzas.modulos.saldo.publico import TiempoSaldo
from finanzas.modulos.importaciones.publico import RegistroHistorialImportaciones
from finanzas.modulos.sincronizacion.publico import RegistroAvisos


class PuntoReversible(Protocol):
    def rollback(self) -> None: ...


class UnidadArranque(Protocol):
    saldo: ServicioSaldo
    configuracion: ConfiguracionHistorial
    tiempo: TiempoSaldo
    importaciones: RegistroHistorialImportaciones
    avisos: RegistroAvisos
    def escritura(self, inmediata: bool = False) -> AbstractContextManager: ...
    def savepoint(self) -> PuntoReversible: ...
