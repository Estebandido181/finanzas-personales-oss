"""Ayudas compartidas extraídas de test_reorganizacion_r2a; datos inventados."""

import subprocess


import sys


from datetime import datetime


import pytest


from sqlalchemy import select


from finanzas import categorizacion, db


from finanzas.bootstrap.unidad_de_trabajo import UnidadDeTrabajoSQLite


from finanzas.modulos.movimientos.publico import MovimientoParaCategorizar


from finanzas.modulos.movimientos.repositorio_sqlite import MovimientosSQLite


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "registro-inventado.db"))
    db.inicializar(conexion)
    yield conexion
    conexion.close()


def _movimiento(conn, **cambios):
    valores = dict(fecha_hora="2026-08-10T10:00:00", monto_centavos=123456,
                   tipo="compra", descripcion="TIENDA INVENTADA", origen="manual")
    valores.update(cambios)
    with db.transaccion(conn):
        return conn.execute(db.movimientos.insert().values(**valores)).inserted_primary_key[0]


def _estado(conn):
    return [dict(fila) for fila in conn.execute(select(db.movimientos)).mappings()]
