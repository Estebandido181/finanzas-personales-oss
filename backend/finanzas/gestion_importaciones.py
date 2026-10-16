"""Compatibilidad de gestión; implementación única en Importaciones."""
from finanzas.compartido import hora
from finanzas.modulos.importaciones.gestion_sqlite import (diario, _componer, _ajustes, _importaciones_actuales, _registro, _reversion, _pendientes, _no_banco, _filas_sin_categoria, _sin_categoria_importacion, _grupos, _hora_importacion_colombia, _dato, _identificaciones, Analisis, ConflictoImportacion, ImportacionInexistente, MENSAJE_CONFLICTO, MENSAJE_REVERSION, TABLAS_DIARIO, TABLAS_HUELLA, TABLAS, _foto, _clave, _where, _coincide, _revertir, _hijos_ajenos, huella, _json)
import finanzas.modulos.importaciones.gestion_sqlite as _gestion_sqlite
from finanzas.modulos.importaciones.gestion_aplicacion import _rango
from finanzas.bootstrap.importaciones import componer_gestion_importaciones, componer_reportes, componer_preguntas, componer_diferencias


def analizar(conn, filas):
    return componer_gestion_importaciones(conn).analizar(filas)


def confirmar(conn, analisis):
    return componer_gestion_importaciones(conn).confirmar(analisis)


def deshacer_importacion(conn, ident):
    return componer_gestion_importaciones(conn).deshacer_importacion(ident)


def _guardar(conn, filas):
    return _gestion_sqlite._guardar(conn, filas, componer_reportes(conn), colaboradores=componer_colaboradores_importacion(conn))


def _simular_respuesta(conn, p, si, movimiento_id, ya_estaba):
    return _gestion_sqlite._simular_respuesta(conn, p, si, movimiento_id, ya_estaba, componer_preguntas(conn), colaboradores=componer_colaboradores_importacion(conn))


def _preguntas(conn):
    return _gestion_sqlite._preguntas(conn, componer_preguntas(conn), colaboradores=componer_colaboradores_importacion(conn))


def preguntas(conn):
    return componer_diferencias(conn).preguntas()


def responder(conn, decisiones, *, transaccion_externa=False):
    return componer_gestion_importaciones(conn).responder(decisiones, transaccion_externa=transaccion_externa)


def aceptar_sugerencias(conn):
    return componer_gestion_importaciones(conn).aceptar_sugerencias()


def no_en_banco(conn):
    return componer_diferencias(conn).no_en_banco()


def decidir_no_en_banco(conn, ident, opcion):
    return componer_gestion_importaciones(conn).decidir_no_en_banco(ident, opcion)


def deshacer_decision(conn, copia):
    return componer_gestion_importaciones(conn).deshacer_decision(copia)


def _deshacible(conn, fila):
    return componer_gestion_importaciones(conn).deshacible(fila)


def _detalle(conn, ident):
    return componer_gestion_importaciones(conn).detalle(ident)


def detalle(conn, ident):
    return componer_gestion_importaciones(conn).detalle(ident)


def ultima(conn):
    return componer_gestion_importaciones(conn).ultima()


def _estado(conn):
    return componer_gestion_importaciones(conn).estado()


def estado(conn):
    return componer_gestion_importaciones(conn).estado()


def comprobar_saldo(conn, saldo_real_centavos, analisis=None):
    return componer_gestion_importaciones(conn).comprobar_saldo(saldo_real_centavos, analisis)

from finanzas.bootstrap.importaciones import componer_colaboradores_importacion

def _categorizar_nuevos(conn, importacion_id):
    return _gestion_sqlite._categorizar_nuevos(conn, importacion_id, colaboradores=componer_colaboradores_importacion(conn))

def _ofrecer_extender_historial(conn, anteriores, desde):
    return _gestion_sqlite._ofrecer_extender_historial(conn, anteriores, desde, colaboradores=componer_colaboradores_importacion(conn))

def pendientes_saldo(conn):
    return _gestion_sqlite.pendientes_saldo(conn, colaboradores=componer_colaboradores_importacion(conn))
