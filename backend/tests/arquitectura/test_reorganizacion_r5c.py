"""Frontera pura de avisos y rollback de su vínculo bancario."""
from finanzas.bootstrap.saldo import componer_saldo
from datetime import datetime
import subprocess
import sys

import pytest
from finanzas import db, importacion
from finanzas.bootstrap.importaciones import componer_incorporacion_aviso
from finanzas.modulos.importaciones.avisos_sqlite import AvisosSQLite
from finanzas.modulos.sincronizacion.publico import MovimientoExtraido
from tests.soporte.ayudas_db import sql
from tests.soporte.importacion import conn, fila  # noqa: F401 (fixture compartido)


def test_caso_incorporacion_sin_sql_http_bootstrap_ni_lector():
    programa = """
import sys
from finanzas.modulos.importaciones.avisos_aplicacion import OperarAvisos
prohibidos = ('sqlalchemy', 'fastapi', 'finanzas.db', 'finanzas.importacion',
              'finanzas.bootstrap', 'finanzas.sincronizacion', 'finanzas.extractor',
              'googleapiclient')
assert not any(n == p or n.startswith(p + '.') for n in sys.modules for p in prohibidos)
"""
    subprocess.run([sys.executable, '-c', programa], check=True, capture_output=True)


def test_fallo_despues_de_vincular_aviso_preserva_fila_y_saldo(conn, monkeypatch):
    importacion.importar(conn, [fila(10, -150000)])
    antes = [tuple(f) for f in sql(conn, 'SELECT * FROM movimientos')]
    saldo_antes = componer_saldo(conn).saldo_actual()
    confirmar = AvisosSQLite.confirmar

    def fallar_despues(self, movimiento_id, gmail_id):
        confirmar(self, movimiento_id, gmail_id)
        raise RuntimeError('fallo inventado después de vincular')

    monkeypatch.setattr(AvisosSQLite, 'confirmar', fallar_despues)
    aviso = MovimientoExtraido('compra', 150000, datetime(2026, 8, 10, 12), 'TIENDA EJEMPLO')
    with pytest.raises(RuntimeError, match='fallo inventado'):
        with db.transaccion(conn, inmediata=True):
            componer_incorporacion_aviso(conn).incorporar_aviso('aviso-rollback-inventado', aviso)
    assert [tuple(f) for f in sql(conn, 'SELECT * FROM movimientos')] == antes
    assert componer_saldo(conn).saldo_actual() == saldo_antes
