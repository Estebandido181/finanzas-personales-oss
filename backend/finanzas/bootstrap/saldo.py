"""Composición de Saldo sobre la unidad compartida y el reloj de Colombia."""
from finanzas.compartido import hora
from finanzas.bootstrap.unidad_de_trabajo import UnidadDeTrabajoSQLite
from finanzas.modulos.saldo.aplicacion import OperarSaldo


class TiempoColombia:
    def ahora(self):
        return hora.ahora_colombia()

    def hoy(self):
        return hora.hoy_colombia()

    def a_hora(self, momento):
        return hora.a_hora_colombia(momento)


def componer_saldo(conn) -> OperarSaldo:
    return OperarSaldo(UnidadDeTrabajoSQLite(conn), TiempoColombia())
