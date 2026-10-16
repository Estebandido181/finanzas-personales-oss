"""Cableado de Categorías: aplicación no importa los adaptadores."""
from sqlalchemy import Connection
from finanzas.bootstrap.unidad_de_trabajo import UnidadDeTrabajoSQLite
from finanzas.modulos.categorias.aplicacion import ConsultarCategorias
from finanzas.modulos.categorias.contratos import ConsultaCategorias
from finanzas.modulos.categorias.administracion import AdministrarCategorias
from finanzas.modulos.categorias.publico import ClasificarEntrada


def componer_consulta_categorias(conn: Connection) -> ConsultaCategorias:
    return ConsultarCategorias(UnidadDeTrabajoSQLite(conn))


def componer_administracion_categorias(conn: Connection) -> AdministrarCategorias:
    return AdministrarCategorias(UnidadDeTrabajoSQLite(conn))


def componer_administracion_reglas(conn: Connection):
    from finanzas.modulos.categorias.administracion_reglas import AdministrarReglas
    return AdministrarReglas(UnidadDeTrabajoSQLite(conn))


def componer_asignacion_categorias(conn: Connection):
    from finanzas.modulos.categorias.asignacion import AsignarCategorias
    return AsignarCategorias(UnidadDeTrabajoSQLite(conn))


def componer_clasificacion_entrada(conn: Connection) -> ClasificarEntrada:
    return componer_asignacion_categorias(conn)


def componer_catalogo_categorias(conn: Connection):
    from finanzas.modulos.categorias.catalogo import ConsultarCatalogo
    return ConsultarCatalogo(UnidadDeTrabajoSQLite(conn))
