"""Descarte reversible; todos los movimientos y archivos son inventados."""
from finanzas.bootstrap.saldo import componer_saldo
from datetime import date
import pytest
from sqlalchemy import select, update
from finanzas.bootstrap.descartes import componer_descartes
from finanzas.modulos.movimientos.descartes_contratos import DescarteNoPermitido
from finanzas import db, gestion_importaciones as gestion
from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.api_importaciones import analizar


def accion(api, ident, nombre="descartar"):
    return api.post(f"/api/movimientos/{ident}/{nombre}")


def foto(config):
    with db.conectar(config.db_path) as conn:
        return gestion.huella(conn)


@pytest.mark.parametrize("tipo", ["compra", "transferencia", "ingreso"])
def test_descartar_restaurar_misma_fila_idempotencia_y_saldo(api, config, tipo):
    configurar_saldo(config, centavos=100000)
    ident = insertar_movimiento(config, tipo=tipo, monto=12300)
    visible = api.get("/api/movimientos?mes=2026-08").json()["movimientos"][0]
    assert visible["puede_descartar"] and not visible["descartado"]
    antes = api.get("/api/saldo").json()["saldo_centavos"]
    r = accion(api, ident)
    assert r.status_code == 200, r.text
    esperado = antes - 12300 if tipo == "ingreso" else antes + 12300
    assert r.json()["saldo_antes_centavos"] == antes
    assert r.json()["saldo_despues_centavos"] == esperado
    assert accion(api, ident).json()["saldo_despues_centavos"] == esperado
    assert api.get("/api/movimientos?mes=2026-08").json()["movimientos"] == []
    assert api.get("/api/movimientos/sin-categorizar").json()["total"] == 0
    listado = api.get("/api/movimientos/descartados").json()["movimientos"]
    assert len(listado) == 1 and listado[0]["id"] == ident and listado[0]["puede_restaurar"]
    with db.conectar(config.db_path) as conn:
        reserva = componer_descartes(conn).listar_reservas()[0]
        assert reserva["movimiento"]["id"] == ident
        assert reserva["gmail_id"] is not None and reserva["banco"] is None
        registro = conn.execute(select(db.descartes_movimientos)).mappings().one()
        assert registro["monto_centavos"] == (12300 if tipo == "ingreso" else -12300)
    assert accion(api, ident, "restaurar").json()["saldo_despues_centavos"] == antes
    assert accion(api, ident, "restaurar").status_code == 200
    assert api.get("/api/movimientos?mes=2026-08").json()["movimientos"][0]["id"] == ident
    assert api.get("/api/movimientos/descartados").json()["movimientos"] == []
    assert accion(api, ident).status_code == 200
    with db.conectar(config.db_path) as conn:
        ciclos = conn.execute(select(db.descartes_movimientos).order_by(db.descartes_movimientos.c.id)).mappings().all()
        assert len(ciclos) == 2 and ciclos[0]["restaurado_en"] and ciclos[1]["restaurado_en"] is None


@pytest.mark.parametrize("guarda", ["manual", "ajuste", "preinicio", "ajuste_id", "ajuste_fecha", "pregunta", "borrado", "sin_config"])
def test_guardas_descartar_sin_mutacion_y_motivos(api, config, guarda):
    if guarda != "sin_config":
        configurar_saldo(config)
    if guarda == "ajuste_fecha":
        insertar_movimiento(config, tipo="ajuste", origen="manual", monto=0, fecha_hora="2026-08-12T10:00:00")
    ident = insertar_movimiento(config,
        origen="manual" if guarda in ("manual", "ajuste") else "gmail",
        tipo="ajuste" if guarda == "ajuste" else "ingreso",
        fecha_hora="2026-07-01T10:00:00" if guarda == "preinicio" else "2026-08-10T10:00:00")
    if guarda == "ajuste_id":
        insertar_movimiento(config, tipo="ajuste", origen="manual", monto=0, fecha_hora="2026-08-01T10:00:00")
    if guarda == "borrado":
        ejecutar_sql(config, "UPDATE movimientos SET borrado_en='2026-08-11T10:00:00' WHERE id=?", (ident,))
    if guarda == "pregunta":
        pregunta = ejecutar_sql(config, "INSERT INTO preguntas_conciliacion (tipo,fuente,fecha,monto_centavos) VALUES ('es_el_mismo','banco','2026-08-10',12300)").lastrowid
        ejecutar_sql(config, "INSERT INTO candidatos_pregunta (pregunta_id,movimiento_id) VALUES (?,?)", (pregunta,ident))
    antes = foto(config)
    r = accion(api, ident)
    assert r.status_code == 409 and r.json()["detalle"]
    assert foto(config) == antes
    assert accion(api, 999999).status_code == 404


@pytest.mark.parametrize("cambio", ["ajuste_id", "ajuste_fecha", "preinicio", "categoria", "pregunta"])
def test_restaurar_bloqueado_tras_cambio_sin_mutar(api, config, cambio):
    configurar_saldo(config)
    if cambio == "ajuste_fecha":
        ajuste = insertar_movimiento(config, tipo="ajuste", origen="manual", monto=0, fecha_hora="2026-08-01T10:00:00")
    ident = insertar_movimiento(config, tipo="ingreso")
    assert accion(api, ident).status_code == 200
    if cambio == "ajuste_id":
        insertar_movimiento(config, tipo="ajuste", origen="manual", monto=0)
    elif cambio == "ajuste_fecha":
        ejecutar_sql(config, "UPDATE movimientos SET fecha_hora='2026-08-12T10:00:00' WHERE id=?", (ajuste,))
    elif cambio == "preinicio":
        ejecutar_sql(config, "UPDATE configuracion_saldo SET fecha_inicio='2026-08-11' WHERE id=1")
    elif cambio == "categoria":
        ejecutar_sql(config, "UPDATE movimientos SET descripcion='OTRO COMERCIO INVENTADO' WHERE id=?", (ident,))
    else:
        p = ejecutar_sql(config, "INSERT INTO preguntas_conciliacion (tipo,fuente,fecha,monto_centavos) VALUES ('es_el_mismo','banco','2026-08-10',12300)").lastrowid
        ejecutar_sql(config, "INSERT INTO candidatos_pregunta (pregunta_id,movimiento_id) VALUES (?,?)", (p,ident))
    antes = foto(config)
    assert not api.get("/api/movimientos/descartados").json()["movimientos"][0]["puede_restaurar"]
    assert accion(api, ident, "restaurar").status_code == 409
    assert foto(config) == antes


def test_respaldo_banco_autoritativo_conserva_descarte_y_restaurar_importe(api, config):
    configurar_saldo(config, centavos=100000)
    ident = insertar_movimiento(config, monto=12300)
    assert accion(api, ident).status_code == 200
    with db.conectar(config.db_path) as conn, db.transaccion(conn, inmediata=True):
        conn.execute(update(db.movimientos).where(db.movimientos.c.id == ident).values(
            monto_centavos=12500, estado="confirmado", fecha_banco="2026-08-10", referencia="*1234"))
        componer_descartes(conn).actualizar_respaldo_banco(ident, fecha=date(2026,8,10), monto_centavos=-12500, referencia="*1234")
        assert componer_saldo(conn).saldo_actual() == 100000
        assert componer_descartes(conn).listar_reservas()[0]["banco"] == dict(fecha="2026-08-10", monto_centavos=-12500, referencia="*1234")
    assert accion(api, ident, "restaurar").json()["saldo_despues_centavos"] == 87500


@pytest.mark.parametrize("cambio", [dict(categoria_id=1), dict(origen="extracto"),
    dict(fecha_hora="2026-08-09T10:00:00"), dict(borrado_en=None), dict(descripcion="CAMBIO INVENTADO")])
def test_confirmacion_no_legitima_cambios_ajenos_y_rollback(config, cambio):
    configurar_saldo(config)
    ident = insertar_movimiento(config)
    with db.conectar(config.db_path) as conn:
        componer_descartes(conn).cambiar(ident)
    antes = foto(config)
    with pytest.raises(DescarteNoPermitido):
        with db.conectar(config.db_path) as conn, db.transaccion(conn, inmediata=True):
            conn.execute(update(db.movimientos).where(db.movimientos.c.id == ident).values(
                **cambio, estado="confirmado", fecha_banco="2026-08-10"))
            componer_descartes(conn).actualizar_respaldo_banco(ident, fecha=date(2026,8,10), monto_centavos=-6863000, referencia=None)
    assert foto(config) == antes


def test_preview_y_undo_importacion_antiguos_conflicto_incluso_tras_restaurar(api, config):
    configurar_saldo(config)
    analisis = analizar(api).json()
    importe = api.post("/api/importaciones", json={"token":analisis["token"]}).json()
    ident = api.get("/api/movimientos?mes=2026-08").json()["movimientos"][0]["id"]
    pendiente = analizar(api).json()
    assert accion(api, ident).status_code == 200
    assert api.post("/api/importaciones", json={"token":pendiente["token"]}).status_code == 409
    assert api.post(f'/api/importaciones/{importe["id"]}/deshacer').status_code == 409
    assert accion(api, ident, "restaurar").status_code == 200
    antes = foto(config)
    assert api.post(f'/api/importaciones/{importe["id"]}/deshacer').status_code == 409
    assert foto(config) == antes
