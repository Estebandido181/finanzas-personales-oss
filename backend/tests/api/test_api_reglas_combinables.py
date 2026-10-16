"""API de reglas combinables (ítem 17): elegir qué regla crear, verla y su frase.

Datos inventados.
"""

from __future__ import annotations

import pytest

from finanzas import categorizacion, db
from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import ejecutar_sql, insertar_movimiento

TRANSPORTE, RESTAURANTES, VIVIENDA, PRESTAMOS = 3, 2, 4, 11
BUS = 320000


@pytest.fixture
def mov(config):
    return {
        "bus_1": insertar_movimiento(config, "2026-08-02T07:10:00", BUS, "transferencia", "*3000000001"),
        "bus_2": insertar_movimiento(config, "2026-08-03T07:10:00", BUS, "transferencia", "*3000000002"),
        "bus_3": insertar_movimiento(config, "2026-08-04T07:10:00", BUS, "transferencia", "CONDUCTOR EJEMPLO"),
        "compra": insertar_movimiento(config, "2026-08-05T10:00:00", BUS, "compra", "PANADERIA EJEMPLO"),
        "otro_monto": insertar_movimiento(config, "2026-08-06T10:00:00", 330000, "transferencia", "*3000000001"),
        "laura_1": insertar_movimiento(config, "2026-08-07T21:28:00", 620000, "transferencia", "LAURA GÓMEZ EJEMPLO"),
        "laura_2": insertar_movimiento(config, "2026-08-08T21:28:00", 620000, "transferencia", "LAURA GÓMEZ EJEMPLO"),
        "laura_3": insertar_movimiento(config, "2026-08-09T21:28:00", 1500000, "transferencia", "LAURA GÓMEZ EJEMPLO"),
        "prestamo": insertar_movimiento(config, "2026-08-10T10:00:00", 40000000, "ingreso", "CARLOS RUIZ EJEMPLO"),
    }


def _put(api, movimiento_id, **cuerpo):
    return api.put(f"/api/movimientos/{movimiento_id}/categoria", json=cuerpo)


def _movimientos(api):
    r = api.get("/api/movimientos", params={"mes": "2026-08"})
    assert r.status_code == 200
    return {m["id"]: m for m in r.json()["movimientos"]}


def _reglas(config):
    return ejecutar_sql(config, "SELECT campo, texto, monto_centavos, categoria_id FROM reglas ORDER BY id").fetchall()


def test_regla_del_bus_por_monto(api, config, mov):
    """Criterio de terminado: "transferencia + $3.200" sin importar el destino, y no a compras."""
    r = _put(api, mov["bus_1"], categoria_id=TRANSPORTE, recordar=True, condiciones="monto")
    assert r.status_code == 200, r.text
    regla_id = ejecutar_sql(config, "SELECT id FROM reglas").fetchone()[0]
    regla = {
        "modo_texto": "exacta", "origen_regla": "todos",
        "id": regla_id, "tipo_movimiento": "transferencia", "campo": "cuenta_destino", "texto": None,
        "monto_centavos": BUS, "condiciones": "monto", "frase": "transferencia de $3.200",
    }
    assert r.json() == {"categorizados": 3, "regla_guardada": True, "regla": regla}
    assert _reglas(config) == [("cuenta_destino", None, BUS, TRANSPORTE)]

    movimientos = _movimientos(api)
    assert movimientos[mov["bus_1"]]["origen_categoria"] == "manual"
    for clave in ("bus_2", "bus_3"):
        assert movimientos[mov[clave]]["categoria"]["id"] == TRANSPORTE
        assert movimientos[mov[clave]]["origen_categoria"] == "regla"
        assert movimientos[mov[clave]]["regla"] == regla
    assert movimientos[mov["compra"]]["categoria"] is None
    assert movimientos[mov["otro_monto"]]["categoria"] is None


def test_las_dos_cosas_juntas(api, config, mov):
    r = _put(api, mov["laura_1"], categoria_id=RESTAURANTES, recordar=True, condiciones="texto_y_monto")
    assert r.status_code == 200, r.text
    assert r.json()["categorizados"] == 2
    assert r.json()["regla"]["condiciones"] == "texto_y_monto"
    assert r.json()["regla"]["frase"] == "transferencia a «laura gómez ejemplo» por $6.200"
    assert _reglas(config) == [("cuenta_destino", "laura gómez ejemplo", 620000, RESTAURANTES)]
    movimientos = _movimientos(api)
    assert movimientos[mov["laura_2"]]["origen_categoria"] == "regla"
    assert movimientos[mov["laura_3"]]["categoria"] is None  # otro monto


def test_por_texto_sigue_siendo_lo_de_siempre(api, config, mov):
    # Sin ``condiciones`` (como manda hoy el frontend) y pidiéndolo explícitamente.
    assert _put(api, mov["laura_1"], categoria_id=RESTAURANTES, recordar=True).json()["categorizados"] == 3
    assert _put(api, mov["bus_1"], categoria_id=TRANSPORTE, recordar=True, condiciones="texto").status_code == 200
    assert _reglas(config) == [
        ("cuenta_destino", "laura gómez ejemplo", None, RESTAURANTES),
        ("cuenta_destino", "*0001", None, TRANSPORTE),
    ]


def test_prioridad_en_la_api_texto_antes_que_monto(api, config, mov):
    _put(api, mov["bus_1"], categoria_id=TRANSPORTE, recordar=True, condiciones="monto")
    # Una transferencia nueva de $3.200 a una cuenta con regla por texto: gana el texto.
    _put(api, mov["otro_monto"], categoria_id=VIVIENDA, recordar=True, condiciones="texto")
    conn = db.conectar(config.db_path)
    try:
        regla = categorizacion.regla_que_coincide(conn, "transferencia", "*3000000001", BUS)
    finally:
        conn.close()
    texto_id = ejecutar_sql(config, "SELECT id FROM reglas WHERE texto IS NOT NULL").fetchone()[0]
    assert (regla["id"], regla["categoria_id"]) == (texto_id, VIVIENDA)


def test_ingreso_por_texto_y_monto(api, config, mov):
    r = _put(api, mov["prestamo"], categoria_id=PRESTAMOS, recordar=True, condiciones="texto_y_monto")
    assert r.status_code == 200, r.text
    [regla] = api.get("/api/reglas").json()["reglas"]
    assert regla == {
        "modo_texto": "exacta", "origen_regla": "todos",
        "id": r.json()["regla"]["id"],
        "tipo_movimiento": "ingreso",
        "campo": "quien_envia",
        "texto": "carlos ruiz ejemplo",
        "monto_centavos": 40000000,
        "condiciones": "texto_y_monto",
        "categoria": {"id": PRESTAMOS, "nombre": "Préstamos", "clase": "ingreso", "color": "cat-prestamos",
                      "icono": "handshake"},
        "frase": "Si es un ingreso de «carlos ruiz ejemplo» por $400.000, va a Préstamos",
    }


def test_get_reglas_refleja_el_monto(api, mov):
    _put(api, mov["bus_1"], categoria_id=TRANSPORTE, recordar=True, condiciones="monto")
    [regla] = api.get("/api/reglas").json()["reglas"]
    assert regla["frase"] == "Si es una transferencia de $3.200, va a Transporte"
    assert (regla["texto"], regla["monto_centavos"], regla["condiciones"]) == (None, BUS, "monto")


def test_reglas_posibles_de_cada_movimiento(api, mov):
    movimientos = _movimientos(api)
    assert [o["condiciones"] for o in movimientos[mov["laura_1"]]["reglas_posibles"]] == [
        "texto", "monto", "texto_y_monto"
    ]
    assert [o["frase"] for o in movimientos[mov["laura_1"]]["reglas_posibles"]] == [
        "transferencia a «laura gómez ejemplo»",
        "transferencia de $6.200",
        "transferencia a «laura gómez ejemplo» por $6.200",
    ]
    assert [o["condiciones"] for o in movimientos[mov["compra"]]["reglas_posibles"]] == ["texto"]
    assert [o["condiciones"] for o in movimientos[mov["prestamo"]]["reglas_posibles"]] == [
        "texto", "monto", "texto_y_monto"
    ]
    assert movimientos[mov["prestamo"]]["reglas_posibles"][2]["frase"] == (
        "ingreso de «carlos ruiz ejemplo» por $400.000"
    )


def test_transferencia_sin_descripcion_solo_ofrece_y_acepta_el_monto(api, config):
    vacia = insertar_movimiento(config, "2026-08-11T10:00:00", BUS, "transferencia", " ")
    movimiento = _movimientos(api)[vacia]
    assert movimiento["regla_posible"] is None
    assert [o["condiciones"] for o in movimiento["reglas_posibles"]] == ["monto"]
    r = _put(api, vacia, categoria_id=TRANSPORTE, recordar=True, condiciones="texto")
    assert r.status_code == 400
    assert _movimientos(api)[vacia]["categoria"] is None
    assert _put(api, vacia, categoria_id=TRANSPORTE, recordar=True, condiciones="monto").status_code == 200


def test_una_compra_por_monto_si_se_pide(api, config, mov):
    r = _put(api, mov["compra"], categoria_id=8, recordar=True, condiciones="monto")
    assert r.status_code == 200, r.text
    assert r.json()["regla"]["frase"] == "compra de $3.200"
    # Solo compras: ninguna transferencia de $3.200 cambió.
    assert r.json()["categorizados"] == 1
    assert _movimientos(api)[mov["bus_2"]]["categoria"] is None


def test_condiciones_sin_recordar_es_400_sin_cambiar_nada(api, config, mov):
    r = _put(api, mov["bus_1"], categoria_id=TRANSPORTE, condiciones="monto")
    assert r.status_code == 400
    assert _movimientos(api)[mov["bus_1"]]["categoria"] is None
    assert _reglas(config) == []


@pytest.mark.parametrize("condiciones", ["contiene", "", "MONTO", 1, True, ["monto"]])
def test_condiciones_invalidas_422(api, config, mov, condiciones):
    r = _put(api, mov["bus_1"], categoria_id=TRANSPORTE, recordar=True, condiciones=condiciones)
    assert r.status_code == 422
    assert _reglas(config) == []


# --- Seguridad (ítem 10) ----------------------------------------------------------------------

def test_sin_sesion_401(cliente, mov):
    assert cliente.get("/api/reglas").status_code == 401
    r = cliente.put(
        f"/api/movimientos/{mov['bus_1']}/categoria",
        json={"categoria_id": TRANSPORTE, "recordar": True, "condiciones": "monto"},
    )
    assert r.status_code in (401, 403)


def test_sin_csrf_403_sin_cambiar_nada(api, cliente, config, mov):
    r = cliente.put(
        f"/api/movimientos/{mov['bus_1']}/categoria",
        json={"categoria_id": TRANSPORTE, "recordar": True, "condiciones": "monto"},
    )
    assert r.status_code == 403
    assert _reglas(config) == []


def test_desde_otro_origen_403_sin_cambiar_nada(api, config, mov):
    r = api.put(
        f"/api/movimientos/{mov['bus_1']}/categoria",
        json={"categoria_id": TRANSPORTE, "recordar": True, "condiciones": "monto"},
        headers={"Origin": "https://sitio-ajeno.example"},
    )
    assert r.status_code == 403
    assert _reglas(config) == []
