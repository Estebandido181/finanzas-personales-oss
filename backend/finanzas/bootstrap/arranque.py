"""Cableado del historial: mismos participantes y conexión en una sola frontera."""
from finanzas.infraestructura import persistencia as db
from finanzas.compartido import hora
from finanzas.bootstrap.importaciones import componer_reportes, componer_colaboradores_importacion
from finanzas.bootstrap.saldo import componer_saldo, TiempoColombia
from finanzas.modulos.saldo.repositorio_sqlite import SaldoSQLite
from finanzas.modulos.importaciones.gestion_sqlite import HistorialImportacionesSQLite
from finanzas.bootstrap.sincronizacion import componer_registro_avisos
from finanzas.modulos.sincronizacion.publico import REMITENTES_OFICIALES
from finanzas.flujos.arranque import OperarArranque
from finanzas.flujos.historial import preparar_avisos as _preparar_avisos


class _UnidadArranqueSQLite:
    def __init__(self, conn):
        self._conn = conn
        self.tiempo = TiempoColombia()
        self.saldo = componer_saldo(conn)
        self.configuracion = SaldoSQLite(conn)
        self.importaciones = HistorialImportacionesSQLite(conn, componer_reportes(conn), self.tiempo, colaboradores=componer_colaboradores_importacion(conn))
        self.avisos = componer_registro_avisos(conn)

    def escritura(self, inmediata=False):
        return db.transaccion(self._conn, inmediata=inmediata)

    def savepoint(self):
        return self._conn.begin_nested()


def componer_arranque(conn):
    return OperarArranque(_UnidadArranqueSQLite(conn))


def preparar_avisos(cliente, desde, registrados, remitentes=REMITENTES_OFICIALES):
    from finanzas.modulos.sincronizacion.adaptadores.avisos import evaluacion
    return _preparar_avisos(cliente, desde, registrados, remitentes,
        evaluacion.evaluar_correo, hora.ZONA_COLOMBIA)


def snapshot_preparacion(conn):
    unidad = _UnidadArranqueSQLite(conn)
    with db.lectura_consistente(conn):
        return unidad.importaciones.huella(), unidad.avisos.ids_registrados()
