"""Participantes prestados por el arranque; sin construir módulos consumidores."""
from dataclasses import dataclass
from finanzas.modulos.categorias.publico import AsignarPorReglas, ClasificarEntrada, ConsultarPendientes
from finanzas.modulos.movimientos.publico import RegistroBancario, RegistroNormalizado, ReservasDescartes
from finanzas.modulos.saldo.publico import ServicioSaldo


@dataclass(frozen=True)
class ColaboradoresImportacion:
    bancario: RegistroBancario
    normalizado: RegistroNormalizado
    descartes: ReservasDescartes
    clasificacion: ClasificarEntrada
    asignacion: AsignarPorReglas
    catalogo: ConsultarPendientes
    saldo: ServicioSaldo
