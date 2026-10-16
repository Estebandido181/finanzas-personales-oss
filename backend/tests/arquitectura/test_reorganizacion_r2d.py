"""Reglas: los participantes revierten juntos sin tocar el dinero del registro."""
import subprocess
import sys

import pytest
from sqlalchemy import select

from finanzas import categorizacion, db
from finanzas.modulos.categorias.reglas_sqlite import ReglasSQLite
from finanzas.modulos.movimientos.repositorio_sqlite import MovimientosSQLite


@pytest.mark.parametrize("operacion", ["borrar", "restaurar"])
def test_fallo_despues_de_escribir_revierte_regla_y_vinculos(tmp_path, monkeypatch, operacion):
    conn = db.conectar(str(tmp_path / "reglas-inventadas.db"))
    try:
        db.inicializar(conn)
        with db.transaccion(conn):
            regla_id = conn.execute(db.reglas.insert().values(
                campo="comercio", texto="tienda inventada", categoria_id=1,
            )).inserted_primary_key[0]
            conn.execute(db.movimientos.insert().values(
                fecha_hora="2026-08-10T10:00:00", monto_centavos=123456,
                tipo="compra", descripcion="TIENDA INVENTADA", origen="manual",
                categoria_id=1, origen_categoria="regla", regla_id=regla_id,
            ))
        def estado():
            return tuple([dict(fila) for fila in conn.execute(select(tabla)).mappings()]
                         for tabla in (db.movimientos, db.reglas))
        if operacion == "restaurar":
            copia = categorizacion.borrar_regla_con_copia(conn, regla_id)
            clase, metodo = MovimientosSQLite, "revincular_regla_si_compatible"
        else:
            clase, metodo = ReglasSQLite, "borrar"
        anterior = estado()
        original = getattr(clase, metodo)

        def fallar(self, *args):
            original(self, *args)
            raise RuntimeError("fallo inventado tras escribir")

        monkeypatch.setattr(clase, metodo, fallar)
        with pytest.raises(RuntimeError, match="fallo inventado"):
            if operacion == "borrar":
                categorizacion.borrar_regla_con_copia(conn, regla_id)
            else:
                categorizacion.restaurar_regla(conn, copia)
        assert estado() == anterior
    finally:
        conn.close()


def test_casos_de_reglas_no_cargan_sql_http_ni_adaptadores():
    codigo = (
        "import sys; import finanzas.modulos.categorias.administracion_reglas; "
        "assert not any(m.startswith(('sqlalchemy', 'fastapi', 'starlette', "
        "'finanzas.db', 'finanzas.bootstrap', 'finanzas.infraestructura')) for m in sys.modules)"
    )
    resultado = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr
