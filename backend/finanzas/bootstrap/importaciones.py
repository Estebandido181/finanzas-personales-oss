"""Composición de los casos de reporte e incorporación de avisos.

El participante conserva la conexión y transacción que ya posee Sincronización.
Aquí se construyen los participantes; ningún adaptador importa este módulo.
"""
from sqlalchemy import Connection
from finanzas.modulos.importaciones.publico import IncorporarAviso, ImportarReporte, ResponderPreguntas, ServicioGestionImportaciones, ServicioDiferencias


def componer_operacion_avisos(conn: Connection):
    from finanzas.modulos.importaciones.avisos_aplicacion import OperarAvisos
    from finanzas.modulos.importaciones.avisos_sqlite import AvisosSQLite
    return OperarAvisos(AvisosSQLite(conn, colaboradores=componer_colaboradores_importacion(conn)))


def componer_incorporacion_aviso(conn: Connection) -> IncorporarAviso:
    return componer_operacion_avisos(conn)


class _UnidadReporteSQLite:
    """Frontera propietaria exacta del importador histórico.

    transaccion_externa evita esta frontera en el caso; aquí se abre la escritura
    inmediata y se confirma/revierte según las primitivas existentes.
    """
    def __init__(self, conn: Connection):
        from finanzas.modulos.importaciones.reportes_sqlite import ReportesSQLite
        self._conn = conn
        self.importaciones = ReportesSQLite(conn, colaboradores=componer_colaboradores_importacion(conn))

    def escritura(self, inmediata: bool = False):
        from finanzas.infraestructura import persistencia as db
        return db.transaccion(self._conn, inmediata=inmediata)


def componer_reportes(conn: Connection) -> ImportarReporte:
    from finanzas.modulos.importaciones.reportes_aplicacion import OperarReportes
    return OperarReportes(_UnidadReporteSQLite(conn))


class _UnidadPreguntasSQLite:
    def __init__(self, conn: Connection):
        from finanzas.modulos.importaciones.preguntas_sqlite import PreguntasSQLite
        self._conn = conn
        self.preguntas = PreguntasSQLite(conn, colaboradores=componer_colaboradores_importacion(conn))

    def escritura(self, inmediata: bool = False):
        from finanzas.infraestructura import persistencia as db
        return db.transaccion(self._conn, inmediata=inmediata)


def componer_preguntas(conn: Connection) -> ResponderPreguntas:
    from finanzas.modulos.importaciones.preguntas_aplicacion import OperarPreguntas
    return OperarPreguntas(_UnidadPreguntasSQLite(conn))


class _UnidadGestionSQLite:
    def __init__(self, conn: Connection):
        from finanzas.modulos.importaciones.gestion_sqlite import GestionSQLite, DiferenciasSQLite
        self._conn = conn
        from finanzas.bootstrap.saldo import TiempoColombia
        self.tiempo = TiempoColombia()
        self.gestion = GestionSQLite(conn, componer_reportes(conn), self.tiempo, colaboradores=componer_colaboradores_importacion(conn))
        self.respuestas = componer_preguntas(conn)
        self.diferencias = DiferenciasSQLite(conn, self.respuestas, colaboradores=componer_colaboradores_importacion(conn))

    def escritura(self, inmediata: bool = False):
        from finanzas.infraestructura import persistencia as db
        return db.transaccion(self._conn, inmediata=inmediata)

    def lectura(self):
        from finanzas.infraestructura import persistencia as db
        return db.lectura_consistente(self._conn)

    def savepoint(self):
        return self._conn.begin_nested()

    def reversion(self):
        from contextlib import contextmanager
        from sqlalchemy.exc import IntegrityError
        from finanzas.infraestructura import persistencia as db
        from finanzas.modulos.importaciones.contratos import ConflictoImportacion, MENSAJE_REVERSION

        @contextmanager
        def frontera():
            try:
                with db.transaccion(self._conn, inmediata=True):
                    yield
            except IntegrityError:
                raise ConflictoImportacion(MENSAJE_REVERSION) from None
        return frontera()


def componer_gestion_importaciones(conn: Connection) -> ServicioGestionImportaciones:
    from finanzas.modulos.importaciones.gestion_aplicacion import GestionarImportaciones
    return GestionarImportaciones(_UnidadGestionSQLite(conn))


class _UnidadDiferenciasSQLite:
    def __init__(self, conn):
        from finanzas.modulos.importaciones.gestion_sqlite import DiferenciasSQLite
        self._conn = conn
        self.diferencias = DiferenciasSQLite(conn, componer_preguntas(conn), colaboradores=componer_colaboradores_importacion(conn))

    def lectura(self):
        from finanzas.infraestructura import persistencia as db
        return db.lectura_consistente(self._conn)


def componer_diferencias(conn: Connection) -> ServicioDiferencias:
    from finanzas.modulos.importaciones.diferencias_aplicacion import ConsultarDiferencias
    return ConsultarDiferencias(_UnidadDiferenciasSQLite(conn))


def componer_colaboradores_importacion(conn):
    from finanzas.modulos.importaciones.colaboradores import ColaboradoresImportacion
    from finanzas.bootstrap.movimientos import componer_registro_bancario, componer_registro_normalizado
    from finanzas.bootstrap.descartes import componer_descartes
    from finanzas.bootstrap.categorias import componer_asignacion_categorias, componer_catalogo_categorias
    from finanzas.bootstrap.saldo import componer_saldo
    asignacion = componer_asignacion_categorias(conn)
    return ColaboradoresImportacion(
        bancario=componer_registro_bancario(conn), normalizado=componer_registro_normalizado(conn),
        descartes=componer_descartes(conn), clasificacion=asignacion, asignacion=asignacion,
        catalogo=componer_catalogo_categorias(conn), saldo=componer_saldo(conn))
