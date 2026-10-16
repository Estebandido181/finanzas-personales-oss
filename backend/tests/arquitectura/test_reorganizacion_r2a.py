"""Frontera Movimientos/Categorías: decisiones y transacción compartida."""
import subprocess
import sys
from datetime import datetime

import pytest
from sqlalchemy import select

from finanzas import categorizacion, db
from finanzas.bootstrap.unidad_de_trabajo import UnidadDeTrabajoSQLite
from finanzas.modulos.movimientos.publico import MovimientoParaCategorizar
from finanzas.modulos.movimientos.repositorio_sqlite import MovimientosSQLite
from tests.soporte.reorganizacion_r2a import _estado, _movimiento, conn  # ayudas compartidas








def test_candidatos_son_datos_puros_y_excluyen_descartados_y_asignados(conn):
    activo = _movimiento(conn)
    descartado = _movimiento(conn, borrado_en="2026-08-11T10:00:00")
    _movimiento(conn, categoria_id=1)
    registro = MovimientosSQLite(conn)
    assert registro.buscar_activo(descartado) is None
    pendientes = registro.listar_pendientes("compra")
    assert len(pendientes) == 1 and pendientes[0].id == activo
    assert isinstance(pendientes[0], MovimientoParaCategorizar)
    assert pendientes[0].monto_centavos == 123456


def test_asignacion_manual_preserva_dinero_e_identidad_y_no_se_pisa_por_regla(conn):
    movimiento_id = _movimiento(conn)
    anterior = _estado(conn)[0]
    categorizacion.asignar_con_detalle(conn, movimiento_id, 1, recordar=True)
    registro = MovimientosSQLite(conn)
    with db.transaccion(conn):
        regla_id = conn.execute(select(db.reglas.c.id)).scalar_one()
        assert registro.asignar_por_regla_si_pendiente(movimiento_id, 2, regla_id) == 0
    actual = _estado(conn)[0]
    assert actual == {**anterior, "categoria_id": 1, "origen_categoria": "manual", "regla_id": None}


def test_fallo_al_aplicar_regla_revierte_asignacion_regla_y_pendientes(conn, monkeypatch):
    movimiento_id = _movimiento(conn)
    _movimiento(conn)
    anterior = _estado(conn)
    aplicar = MovimientosSQLite.asignar_por_regla_si_pendiente

    def fallar_despues_de_escribir(self, *args):
        assert aplicar(self, *args) == 1
        raise RuntimeError("fallo inventado")

    monkeypatch.setattr(MovimientosSQLite, "asignar_por_regla_si_pendiente", fallar_despues_de_escribir)
    with pytest.raises(RuntimeError, match="fallo inventado"):
        categorizacion.asignar_con_detalle(conn, movimiento_id, 1, recordar=True)
    assert _estado(conn) == anterior
    assert conn.execute(select(db.reglas.c.id)).all() == []


def test_participantes_comparten_escritura_y_no_confirman_por_separado(conn):
    movimiento_id = _movimiento(conn)
    unidad = UnidadDeTrabajoSQLite(conn)
    with pytest.raises(RuntimeError):
        with db.transaccion(conn, inmediata=True):
            assert unidad.movimientos.asignar_manual(movimiento_id, 1) == 1
            desde, hasta = datetime(2026, 8, 1), datetime(2026, 9, 1)
            consulta = unidad.categorias.consultar_con_uso(desde, hasta, uso=unidad.movimientos.uso_por_categoria(desde, hasta))
            assert next(f for f in consulta if f.id == 1).movimientos_mes == 1
            assert db.en_transaccion(conn)
            raise RuntimeError()
    assert _estado(conn)[0]["categoria_id"] is None
    assert not conn.closed


def test_contrato_movimientos_no_carga_adaptadores_ni_categorias():
    codigo = (
        "import sys; import finanzas.modulos.movimientos.publico; "
        "assert not any(m.startswith(('sqlalchemy', 'fastapi', 'starlette', "
        "'finanzas.modulos.categorias', 'finanzas.db')) for m in sys.modules)"
    )
    resultado = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr
