"""Ayudas compartidas extraídas de test_conciliacion_propiedades; datos inventados."""

from __future__ import annotations


import shutil


from collections import Counter


import tempfile


from datetime import date, datetime, time


from pathlib import Path


import pytest


from hypothesis import HealthCheck, event, given, settings


from hypothesis import strategies as st


from finanzas.modulos.importaciones import motor as c


from finanzas import db, importacion, sincronizacion
from finanzas.modulos.sincronizacion.adaptadores.avisos import extractor


from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import MovimientoExcel, ultimos_4_de_referencia


from tests.soporte.ayudas_db import sql as _sql


def sql(conn, texto, parametros=()):
    return _sql(conn, texto, parametros).fetchall()


@pytest.fixture(scope="module")
def plantilla(tmp_path_factory) -> Path:
    ruta = tmp_path_factory.mktemp("plantilla") / "plantilla.db"
    db.preparar(str(ruta))
    conn = db.conectar(str(ruta))
    with db.transaccion(conn):
        sql(conn, "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, ?, ?)",
            (500_000_000, "2026-08-01"))
    conn.close()
    return ruta


class Base:
    """Copia de la plantilla en una carpeta temporal propia del ejemplo."""

    def __init__(self, plantilla: Path):
        self.carpeta = tempfile.mkdtemp()
        ruta = Path(self.carpeta) / "ejemplo.db"
        shutil.copy(plantilla, ruta)
        self.conn = db.conectar(str(ruta))

    def __enter__(self):
        return self.conn

    def __exit__(self, *_):
        self.conn.close()
        shutil.rmtree(self.carpeta, ignore_errors=True)
