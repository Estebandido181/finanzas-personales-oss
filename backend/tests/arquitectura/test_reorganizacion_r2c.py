"""La administración participa en una sola transacción y no depende de SQL."""
import subprocess
import sys

import pytest
from sqlalchemy import select

from finanzas import categorizacion, db
from finanzas.modulos.categorias.repositorio_sqlite import CategoriasSQLite


def test_fallo_entre_traslados_revierte_movimientos_reglas_y_categoria(tmp_path, monkeypatch):
    conn = db.conectar(str(tmp_path / "categorias-inventadas.db"))
    try:
        db.inicializar(conn)
        with db.transaccion(conn):
            conn.execute(db.movimientos.insert().values(
                fecha_hora="2026-08-10T10:00:00", monto_centavos=123456,
                tipo="compra", descripcion="TIENDA INVENTADA", origen="manual", categoria_id=1,
            ))
        def estado():
            return tuple([dict(fila) for fila in conn.execute(select(tabla)).mappings()]
                         for tabla in (db.movimientos, db.reglas, db.categorias))
        anterior = estado()
        mover = CategoriasSQLite.mover_reglas

        def fallar(self, *args):
            mover(self, *args)
            raise RuntimeError("fallo inventado tras los traslados")

        monkeypatch.setattr(CategoriasSQLite, "mover_reglas", fallar)
        with pytest.raises(RuntimeError, match="fallo inventado"):
            categorizacion.borrar_categoria(conn, 1, 2)
        assert estado() == anterior
    finally:
        conn.close()


def test_administracion_carga_solo_contratos_y_politicas_puras():
    codigo = (
        "import sys; import finanzas.modulos.categorias.administracion; "
        "assert not any(m.startswith(('sqlalchemy', 'fastapi', 'starlette', "
        "'finanzas.db', 'finanzas.bootstrap', 'finanzas.infraestructura')) for m in sys.modules)"
    )
    resultado = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr
