"""Caso puro de respuestas y reversión de respuesta/elección/ajuste juntos."""
from finanzas.bootstrap.saldo import componer_saldo
import subprocess
import sys
from contextlib import nullcontext
import pytest
from finanzas import db, importacion, gestion_importaciones as gestion
from finanzas.bootstrap.importaciones import componer_preguntas
from finanzas.modulos.importaciones.preguntas_sqlite import PreguntasSQLite
from tests.soporte.importacion import conn, fila, ajuste_el_dia  # noqa: F401


def test_caso_respuestas_sin_infraestructura():
    programa = """
import sys
from finanzas.modulos.importaciones.preguntas_aplicacion import OperarPreguntas
prohibidos = ('sqlalchemy', 'fastapi', 'finanzas.db', 'finanzas.importacion',
              'finanzas.bootstrap', 'finanzas.sincronizacion', 'googleapiclient')
assert not any(n == p or n.startswith(p + '.') for n in sys.modules for p in prohibidos)
"""
    subprocess.run([sys.executable, '-c', programa], check=True, capture_output=True)


@pytest.mark.parametrize('externa', [False, True])
def test_fallo_despues_de_eleccion_revierte_respuesta_movimiento_y_ajuste(conn, monkeypatch, externa):
    ajuste_el_dia(conn, 20, -5000)
    importacion.importar(conn, [fila(20, -3000, 'COMERCIO INVENTADO')])
    pregunta = importacion.preguntas_pendientes(conn)[0]
    antes = gestion.huella(conn)
    saldo_antes = componer_saldo(conn).saldo_actual()
    guardar = PreguntasSQLite.guardar_eleccion

    def fallar_despues(self, pregunta_id, movimiento_id):
        guardar(self, pregunta_id, movimiento_id)
        raise RuntimeError('fallo inventado después de elección')

    monkeypatch.setattr(PreguntasSQLite, 'guardar_eleccion', fallar_despues)
    with pytest.raises(RuntimeError, match='fallo inventado'):
        with db.transaccion(conn, inmediata=True) if externa else nullcontext():
            componer_preguntas(conn).responder_pregunta(pregunta['id'], True, transaccion_externa=externa)
    assert gestion.huella(conn) == antes
    assert componer_saldo(conn).saldo_actual() == saldo_antes
    assert importacion.preguntas_pendientes(conn)[0]['id'] == pregunta['id']
