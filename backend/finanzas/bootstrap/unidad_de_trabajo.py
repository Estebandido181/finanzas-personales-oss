"""Participantes concretos compuestos sobre una sola conexión prestada."""
from finanzas.infraestructura.unidad_de_trabajo import UnidadDeTrabajoSQLite as FronteraSQLite
from finanzas.modulos.categorias.repositorio_sqlite import CategoriasSQLite
from finanzas.modulos.categorias.reglas_sqlite import ReglasSQLite
from finanzas.modulos.movimientos.repositorio_sqlite import MovimientosSQLite
from finanzas.modulos.saldo.repositorio_sqlite import SaldoSQLite


class UnidadDeTrabajoSQLite(FronteraSQLite):
    def __init__(self, conn):
        super().__init__(conn)
        self.categorias = CategoriasSQLite(conn)
        self.reglas = ReglasSQLite(conn)
        self.movimientos = MovimientosSQLite(conn)
        self.saldo = SaldoSQLite(conn)
