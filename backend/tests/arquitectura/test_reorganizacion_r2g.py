"""El descarte es independiente de servicios concretos; registro conserva deduplicación."""
import subprocess
import sys

import pytest
from sqlalchemy import select

from finanzas import db
from finanzas.bootstrap.unidad_de_trabajo import UnidadDeTrabajoSQLite
from finanzas.modulos.movimientos.publico import MovimientoNuevo


def test_descartes_cargan_solo_puertos_y_politicas():
    codigo = (
        "import sys; import finanzas.modulos.movimientos.descartes_aplicacion; "
        "assert not any(m.startswith(('sqlalchemy', 'fastapi', 'starlette', "
        "'finanzas.db', 'finanzas.bootstrap', 'finanzas.saldo', 'finanzas.importacion')) for m in sys.modules)"
    )
    resultado = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr


def test_registro_normalizado_deduplica_sin_confirmar_transaccion_ajena(tmp_path):
    conn = db.conectar(str(tmp_path / "registro-inventado.db"))
    try:
        db.inicializar(conn)
        unidad = UnidadDeTrabajoSQLite(conn)
        nuevo = MovimientoNuevo("2026-08-10T10:00:00", 123456, "compra", "TIENDA INVENTADA", "gmail", gmail_id="correo-inventado")
        with pytest.raises(RuntimeError):
            with unidad.escritura(inmediata=True):
                assert unidad.movimientos.registrar_correo_si_nuevo(nuevo)
                assert not unidad.movimientos.registrar_correo_si_nuevo(nuevo)
                assert conn.execute(select(db.movimientos.c.monto_centavos)).scalar_one() == 123456
                raise RuntimeError()
        assert conn.execute(select(db.movimientos)).all() == []
    finally:
        conn.close()
