"""Saldo: aplicación pura y atomicidad después de materializar dinero."""
from finanzas.bootstrap.saldo import componer_saldo
import subprocess
import sys
from datetime import date, datetime

import pytest
from sqlalchemy import select

from finanzas import db
from finanzas.modulos.movimientos.repositorio_sqlite import MovimientosSQLite


def test_saldo_y_comprobacion_no_cargan_sql_http_lectores_ni_composicion():
    codigo = (
        "import sys; import finanzas.modulos.saldo.aplicacion; import finanzas.modulos.saldo.comprobacion; "
        "assert not any(m.startswith(('sqlalchemy', 'fastapi', 'starlette', 'finanzas.db', "
        "'finanzas.bootstrap', 'finanzas.extractor', 'finanzas.importacion')) for m in sys.modules)"
    )
    resultado = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr


@pytest.mark.parametrize("operacion", ["ajustar", "restaurar"])
def test_fallo_despues_de_materializar_revierte_registro_y_saldo(tmp_path, monkeypatch, operacion):
    conn = db.conectar(str(tmp_path / "saldo-inventado.db"))
    try:
        db.inicializar(conn)
        componer_saldo(conn).configurar(100000, date(2026, 8, 1))
        if operacion == "restaurar":
            ident = componer_saldo(conn).registrar_ingreso(50000, datetime(2026, 8, 10, 10), "INGRESO INVENTADO")
            copia, _ = componer_saldo(conn).borrar_ingreso_con_copia(ident)
            metodo = "restaurar_fila_completa"
        else:
            metodo = "registrar"
        anterior = [dict(f) for f in conn.execute(select(db.movimientos)).mappings()]
        antes = componer_saldo(conn).saldo_actual()
        escribir = getattr(MovimientosSQLite, metodo)

        def escribir_y_fallar(self, *args):
            escribir(self, *args)
            raise RuntimeError("fallo inventado tras escribir dinero")

        monkeypatch.setattr(MovimientosSQLite, metodo, escribir_y_fallar)
        with pytest.raises(RuntimeError, match="fallo inventado"):
            if operacion == "ajustar":
                componer_saldo(conn).ajustar_saldo(150000)
            else:
                componer_saldo(conn).restaurar_ingreso(copia)
        assert [dict(f) for f in conn.execute(select(db.movimientos)).mappings()] == anterior
        assert componer_saldo(conn).saldo_actual() == antes
    finally:
        conn.close()
