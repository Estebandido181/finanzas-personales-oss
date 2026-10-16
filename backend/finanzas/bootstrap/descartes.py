"""Composición de registro, transacción, reloj y contexto de Saldo."""
from finanzas.compartido import hora
from finanzas.bootstrap.saldo import componer_saldo
from finanzas.modulos.saldo.publico import MAXIMO_CENTAVOS
from finanzas.bootstrap.unidad_de_trabajo import UnidadDeTrabajoSQLite
from finanzas.modulos.movimientos.descartes_aplicacion import OperarDescartes
from finanzas.modulos.movimientos.descartes_sqlite import DescartesSQLite


class ContextoSaldo:
    maximo_centavos = MAXIMO_CENTAVOS

    def __init__(self, conn):
        self._saldo = componer_saldo(conn)

    def fecha_inicio(self):
        configuracion = self._saldo.leer_configuracion()
        return None if configuracion is None else configuracion.fecha_inicio

    def saldo_actual(self):
        return self._saldo.saldo_actual()


def componer_descartes(conn) -> OperarDescartes:
    return OperarDescartes(DescartesSQLite(conn), ContextoSaldo(conn), UnidadDeTrabajoSQLite(conn),
        lambda: hora.ahora_colombia().replace(tzinfo=None).isoformat(timespec="microseconds"))
