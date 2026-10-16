"""Registro grupal: rollback compartido y guardas sobre candidatos."""
import pytest

from finanzas import categorizacion, db
from finanzas.modulos.movimientos.repositorio_sqlite import MovimientosSQLite
from tests.soporte.reorganizacion_r2a import conn, _estado, _movimiento  # noqa: F401


def test_fallo_despues_de_guardar_regla_revierte_todo_el_grupo(conn, monkeypatch):
    ids = [_movimiento(conn), _movimiento(conn)]
    anterior = _estado(conn)
    from finanzas.modulos.categorias.asignacion import AsignarCategorias
    guardar = AsignarCategorias.guardar_regla

    def guardar_y_fallar(*args):
        guardar(*args)
        raise RuntimeError("fallo grupal inventado")

    monkeypatch.setattr(AsignarCategorias, "guardar_regla", guardar_y_fallar)
    clave = categorizacion.clave_grupo("compra", "TIENDA INVENTADA")
    with pytest.raises(RuntimeError, match="fallo grupal inventado"):
        categorizacion.categorizar_grupo(conn, clave, ids, 1)
    assert _estado(conn) == anterior
    assert conn.exec_driver_sql("SELECT id FROM reglas").all() == []


def test_registro_grupal_filtra_y_preserva_asignaciones_del_dueno(conn):
    pendiente = _movimiento(conn)
    manual = _movimiento(conn, categoria_id=2, origen_categoria="manual")
    descartado = _movimiento(conn, borrado_en="2026-08-11T10:00:00")
    ingreso = _movimiento(conn, tipo="ingreso")
    registro = MovimientosSQLite(conn)
    candidatos = registro.listar_pendientes_por_ids([pendiente, manual, descartado, ingreso], ("compra",))
    assert [m.id for m in candidatos] == [pendiente]
    with db.transaccion(conn):
        assert registro.asignar_grupo_si_pendientes([pendiente, manual], 1) == 1
    filas = {m["id"]: m for m in _estado(conn)}
    assert filas[pendiente]["categoria_id"] == 1
    assert filas[manual]["categoria_id"] == 2
    assert filas[descartado]["categoria_id"] is None
    assert filas[ingreso]["categoria_id"] is None
