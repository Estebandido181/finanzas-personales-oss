"""Consulta mensual compuesta sobre una conexión y lectura consistentes."""
from finanzas.infraestructura.unidad_de_trabajo import UnidadDeTrabajoSQLite
from finanzas.bootstrap.movimientos import componer_registro_normalizado
from finanzas.bootstrap.saldo import componer_saldo
from finanzas.flujos import reporte


class ConsultarReporte(UnidadDeTrabajoSQLite):
    def __init__(self, conn):
        super().__init__(conn)
        self.saldo = componer_saldo(conn)
        self.movimientos = componer_registro_normalizado(conn)

    def reporte_mensual(self, anio: int, mes: int):
        return reporte.reporte_mensual(self, anio, mes)


def componer_reporte(conn):
    return ConsultarReporte(conn)
