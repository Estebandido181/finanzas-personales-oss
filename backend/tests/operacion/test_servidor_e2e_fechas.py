"""Los datos inventados del servidor e2e conservan su orden en cualquier día del mes."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parents[3] / "scripts" / "servidor_e2e.py"
_spec = importlib.util.spec_from_file_location("servidor_e2e", RUTA)
servidor_e2e = importlib.util.module_from_spec(_spec)
sys.modules["servidor_e2e"] = servidor_e2e
_spec.loader.exec_module(servidor_e2e)


@pytest.mark.parametrize("ruta", ["reiniciar", "sin-saldo", "movimiento-anterior"])
def test_limpieza_e2e_retira_descartes_y_elecciones_antes_de_movimientos(tmp_path, ruta):
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from finanzas import db

    dist = tmp_path / "dist-inventado"
    dist.mkdir()
    (dist / "index.html").write_text("<html>Prueba inventada</html>", encoding="utf-8")
    app = servidor_e2e.crear(tmp_path, dist)
    with db.conectar(str(tmp_path / "e2e.db")) as conn, db.transaccion(conn):
        m = conn.execute(select(db.movimientos).order_by(db.movimientos.c.id)).mappings().first()
        original = conn.execute(select(db.movimientos.c.id)).all()
        importacion = conn.execute(db.importaciones.insert().values(filas=1)).inserted_primary_key[0]
        conn.execute(db.reversiones_importacion.insert().values(importacion_id=importacion,
            diario="[]", conteos="{}", ultimo_movimiento_id=m["id"]))
        conn.execute(db.cambios_importacion.insert().values(importacion_id=importacion,
            movimiento_id=m["id"], accion="agregado"))
        pregunta = conn.execute(db.preguntas_conciliacion.insert().values(
            tipo="es_el_mismo", fuente="banco", importacion_id=importacion,
            fecha=m["fecha_hora"][:10], monto_centavos=-12300,
            respuesta="si", respondida_en="2026-08-11T10:00:00",
            ocurrencia_banco=1, movimiento_elegido_id=m["id"])).inserted_primary_key[0]
        conn.execute(db.candidatos_pregunta.insert().values(pregunta_id=pregunta, movimiento_id=m["id"]))
        for restaurado in (None, "2026-08-12T10:00:00"):
            conn.execute(db.descartes_movimientos.insert().values(movimiento_id=m["id"],
                descartado_en="2026-08-11T10:00:00", restaurado_en=restaurado,
                fecha=m["fecha_hora"][:10], monto_centavos=-12300,
                huella_movimiento="huella-inventada", huella_contexto="huella-inventada"))
    with TestClient(app) as cliente:
        respuesta = cliente.get(f"/e2e/datos/{ruta}")
        assert respuesta.status_code == 200, respuesta.text
    with db.conectar(str(tmp_path / "e2e.db")) as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        for tabla in (db.reversiones_importacion, db.candidatos_pregunta, db.preguntas_conciliacion,
                      db.cambios_importacion, db.descartes_movimientos, db.importaciones):
            assert conn.execute(select(tabla)).all() == []
        cantidad = len(conn.execute(select(db.movimientos.c.id)).all())
        assert cantidad == (len(original) if ruta == "reiniciar" else 0 if ruta == "sin-saldo" else 1)


def _instantes(hoy: date) -> list[datetime]:
    primero = hoy.replace(day=1)
    return [servidor_e2e._momento_mes_actual(d, hh, hoy, primero) for d, hh, *_ in servidor_e2e.MES_ACTUAL]


@pytest.mark.parametrize("dia", [1, 2, 5, 9, 10, 15, 28, 31])
def test_orden_y_mes_iguales_cualquier_dia(dia):
    hoy = date(2026, 10, dia)
    instantes = _instantes(hoy)
    assert all(i.year == 2026 and i.month == 10 for i in instantes)
    assert all(i.date() <= hoy for i in instantes)
    # Mismo orden relativo que "N días antes de hoy a esa hora", sin empates.
    esperado = _instantes(date(2026, 10, 31))
    assert sorted(range(len(instantes)), key=instantes.__getitem__) == sorted(
        range(len(esperado)), key=esperado.__getitem__
    )
    assert len(set(instantes)) == len(instantes)


def test_hoy_de_datos_lee_la_variable(monkeypatch):
    monkeypatch.setenv("FINANZAS_E2E_HOY", "2026-10-02")
    assert servidor_e2e._hoy_de_datos() == date(2026, 10, 2)
    monkeypatch.delenv("FINANZAS_E2E_HOY")
    assert isinstance(servidor_e2e._hoy_de_datos(), date)
