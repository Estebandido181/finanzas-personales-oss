"""Pureza del caso y atomicidad de sus participantes."""
from finanzas.bootstrap.saldo import componer_saldo
from contextlib import nullcontext
import subprocess
import sys

import pytest
from finanzas import db, importacion
from finanzas.modulos.importaciones.reportes_sqlite import ReportesSQLite
from tests.soporte.ayudas_db import sql
from tests.soporte.importacion import conn, fila  # noqa: F401 (fixture compartido)


def test_caso_y_politica_de_planes_sin_sql_http_bootstrap():
    programa = """
import sys
from finanzas.modulos.importaciones.reportes_aplicacion import OperarReportes
from finanzas.modulos.importaciones import politica_planes, publico
prohibidos = ('sqlalchemy', 'fastapi', 'finanzas.db', 'finanzas.importacion',
              'finanzas.bootstrap', 'finanzas.sincronizacion', 'googleapiclient')
assert not any(n == p or n.startswith(p + '.') for n in sys.modules for p in prohibidos)
"""
    subprocess.run([sys.executable, '-c', programa], check=True, capture_output=True)


@pytest.mark.parametrize('externa', [False, True])
def test_fallo_tras_materializar_fila_revierte_registro_diario_y_resumen(conn, monkeypatch, externa):
    antes = componer_saldo(conn).saldo_actual()
    agregar = ReportesSQLite.agregar

    def fallar_despues(self, importacion_id, fila):
        agregar(self, importacion_id, fila)
        raise RuntimeError('fallo inventado después de escribir')

    monkeypatch.setattr(ReportesSQLite, 'agregar', fallar_despues)
    with pytest.raises(RuntimeError, match='fallo inventado'):
        with db.transaccion(conn, inmediata=True) if externa else nullcontext():
            importacion.importar(conn, [fila(10, -150000)], transaccion_externa=externa)
    for tabla in ('movimientos', 'cambios_importacion', 'importaciones'):
        assert sql(conn, f'SELECT COUNT(*) FROM {tabla}').fetchone()[0] == 0
    assert componer_saldo(conn).saldo_actual() == antes


def test_transaccion_externa_no_confirma_el_savepoint_de_la_vista_previa(conn):
    antes = componer_saldo(conn).saldo_actual()
    with db.transaccion(conn, inmediata=True):
        savepoint = conn.begin_nested()
        try:
            importacion.importar(conn, [fila(10, -150000)], transaccion_externa=True)
            assert componer_saldo(conn).saldo_actual() == antes - 150000
        finally:
            savepoint.rollback()
        assert componer_saldo(conn).saldo_actual() == antes
        assert sql(conn, 'SELECT COUNT(*) FROM importaciones').fetchone()[0] == 0
