"""Composición temporal para los consumidores históricos de Categorías."""
from sqlalchemy import Connection

from finanzas.bootstrap.unidad_de_trabajo import UnidadDeTrabajoSQLite
from finanzas.modulos.movimientos.publico import RegistroCategorizable, RegistroNormalizado, RegistroBancario


def componer_registro_categorizable(conn: Connection) -> RegistroCategorizable:
    return UnidadDeTrabajoSQLite(conn).movimientos


def componer_registro_normalizado(conn: Connection) -> RegistroNormalizado:
    return UnidadDeTrabajoSQLite(conn).movimientos


def componer_registro_bancario(conn: Connection) -> RegistroBancario:
    from finanzas.modulos.movimientos.bancario_sqlite import RegistroBancarioSQLite
    return RegistroBancarioSQLite(conn)
