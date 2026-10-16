"""API: saldo, configuración, ingresos manuales y ajustes (ítem 10). Datos inventados."""

from __future__ import annotations
from finanzas.bootstrap.saldo import componer_saldo
from finanzas.modulos.saldo import politica as saldo_politica

import pytest


from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import configurar_saldo, ejecutar_sql, insertar_movimiento


def _contar(config, tipo):
    return ejecutar_sql(config, "SELECT COUNT(*) FROM movimientos WHERE tipo = ?", (tipo,)).fetchone()[0]


def _ingreso(api, token, **cambios):
    cuerpo = {"monto_centavos": 2500001, "fecha_hora": "2026-08-15T10:30", "descripcion": "Efectivo inventado", "token": token}
    cuerpo.update(cambios)
    return api.post("/api/ingresos", json=cuerpo)


# --- Ver y configurar ---------------------------------------------------------------------

def test_saldo_sin_configurar(api):
    r = api.get("/api/saldo")
    assert r.status_code == 200
    datos = r.json()
    assert datos["configuracion"] is None
    assert datos["saldo_centavos"] is None and datos["token_ingreso"] is None
    assert datos["ultimos"] == [] and datos["fecha_hora_minima"] is None
    assert datos["maximo_descripcion"] == saldo_politica.MAXIMO_DESCRIPCION
    assert len(datos["hoy"]) == 10 and len(datos["ahora"]) == 19


def test_configurar_y_ver(api):
    r = api.put("/api/saldo/configuracion", json={"saldo_inicial_centavos": 123456789, "fecha_inicio": "2026-08-01"})
    assert r.status_code == 200
    assert r.json() == {"saldo_inicial_centavos": 123456789, "fecha_inicio": "2026-08-01"}
    datos = api.get("/api/saldo").json()
    assert datos["configuracion"] == {"saldo_inicial_centavos": 123456789, "fecha_inicio": "2026-08-01"}
    assert datos["saldo_centavos"] == 123456789
    assert datos["fecha_hora_minima"] == "2026-08-01T00:00:00"
    assert datos["token_ingreso"]


def test_configurar_con_movimientos_400(api, config):
    configurar_saldo(config)
    insertar_movimiento(config)
    r = api.put("/api/saldo/configuracion", json={"saldo_inicial_centavos": 1, "fecha_inicio": "2026-08-01"})
    assert r.status_code == 400
    assert "detalle" in r.json()


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"saldo_inicial_centavos": 12.5, "fecha_inicio": "2026-08-01"},
        {"saldo_inicial_centavos": "100", "fecha_inicio": "2026-08-01"},
        {"saldo_inicial_centavos": -1, "fecha_inicio": "2026-08-01"},
        {"saldo_inicial_centavos": saldo_politica.MAXIMO_CENTAVOS + 1, "fecha_inicio": "2026-08-01"},
        {"saldo_inicial_centavos": True, "fecha_inicio": "2026-08-01"},
        {"saldo_inicial_centavos": 100, "fecha_inicio": 20260801},
        {"saldo_inicial_centavos": 100},
    ],
)
def test_configurar_valida_la_forma(api, cuerpo):
    assert api.put("/api/saldo/configuracion", json=cuerpo).status_code == 422
    assert api.get("/api/saldo").json()["configuracion"] is None


@pytest.mark.parametrize("fecha", ["2026-8-1", "01/08/2026", "2026-02-30", "2026-08-01T00:00", ""])
def test_configurar_fecha_invalida_400(api, fecha):
    r = api.put("/api/saldo/configuracion", json={"saldo_inicial_centavos": 100, "fecha_inicio": fecha})
    assert r.status_code in (400, 422)
    assert api.get("/api/saldo").json()["configuracion"] is None


def test_configurar_con_cero_y_con_el_maximo(api):
    assert api.put("/api/saldo/configuracion", json={"saldo_inicial_centavos": saldo_politica.MAXIMO_CENTAVOS, "fecha_inicio": "2026-08-01"}).status_code == 200
    assert api.get("/api/saldo").json()["saldo_centavos"] == saldo_politica.MAXIMO_CENTAVOS
    assert api.put("/api/saldo/configuracion", json={"saldo_inicial_centavos": 0, "fecha_inicio": "2026-08-01"}).status_code == 200


# --- Ingresos --------------------------------------------------------------------------------

def test_registrar_ingreso(api, config):
    configurar_saldo(config, centavos=100000000)
    token = api.get("/api/saldo").json()["token_ingreso"]
    r = _ingreso(api, token)
    assert r.status_code == 201
    assert r.json()["monto_centavos"] == 2500001
    assert isinstance(r.json()["id"], int)
    datos = api.get("/api/saldo").json()
    assert datos["saldo_centavos"] == 100000000 + 2500001
    assert datos["ultimos"][0] == {
        "id": r.json()["id"],
        "fecha_hora": "2026-08-15T10:30:00",
        "tipo": "ingreso",
        "descripcion": "Efectivo inventado",
        "monto_centavos": 2500001,
    }


def test_ingreso_repetido_409_y_no_se_duplica(api, config):
    configurar_saldo(config)
    token = api.get("/api/saldo").json()["token_ingreso"]
    assert _ingreso(api, token).status_code == 201
    r = _ingreso(api, token)
    assert r.status_code == 409
    assert _contar(config, "ingreso") == 1


def test_ingreso_con_token_desconocido_400(api, config):
    configurar_saldo(config)
    api.get("/api/saldo")
    r = _ingreso(api, "token-inventado")
    assert r.status_code == 400
    assert _contar(config, "ingreso") == 0


def test_ingreso_con_token_de_otra_sesion_400(api, config, app):
    from fastapi.testclient import TestClient

    from tests.soporte.ayudas_api import CONTRASENA, ClienteApi

    configurar_saldo(config)
    with TestClient(app, follow_redirects=False) as otro:
        csrf = otro.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"]
        ajeno = ClienteApi(otro, csrf).get("/api/saldo").json()["token_ingreso"]
    api.get("/api/saldo")
    assert _ingreso(api, ajeno).status_code == 400
    assert _contar(config, "ingreso") == 0


def test_ingreso_invalido_no_gasta_el_token(api, config):
    configurar_saldo(config)
    token = api.get("/api/saldo").json()["token_ingreso"]
    r = _ingreso(api, token, fecha_hora="2026-07-31T23:59")  # antes de la fecha de inicio
    assert r.status_code == 400
    assert _ingreso(api, token).status_code == 201  # corregido, el mismo token sirve


@pytest.mark.parametrize(
    "cambios",
    [
        {"monto_centavos": 0},
        {"monto_centavos": -100},
        {"monto_centavos": 100.5},
        {"monto_centavos": "100"},
        {"monto_centavos": saldo_politica.MAXIMO_CENTAVOS + 1},
        {"fecha_hora": 1},
        {"extra": "x"},
    ],
)
def test_ingreso_valida_la_forma(api, config, cambios):
    configurar_saldo(config)
    token = api.get("/api/saldo").json()["token_ingreso"]
    assert _ingreso(api, token, **cambios).status_code == 422
    assert _contar(config, "ingreso") == 0
    assert _ingreso(api, token).status_code == 201  # el token no se gastó


@pytest.mark.parametrize(
    "fecha_hora",
    ["2026-08-15", "2026-08-15T10:30-05:00", "2026-08-15T10:30Z", "15/08/2026 10:30", "2099-01-01T00:00"],
)
def test_ingreso_fecha_hora_invalida_400(api, config, fecha_hora):
    configurar_saldo(config)
    token = api.get("/api/saldo").json()["token_ingreso"]
    r = _ingreso(api, token, fecha_hora=fecha_hora)
    assert r.status_code in (400, 422)
    assert _contar(config, "ingreso") == 0


def test_ingreso_descripcion_demasiado_larga_400(api, config):
    configurar_saldo(config)
    token = api.get("/api/saldo").json()["token_ingreso"]
    assert _ingreso(api, token, descripcion="x" * (saldo_politica.MAXIMO_DESCRIPCION + 1)).status_code == 400


def test_ingreso_sin_configurar_no_hay_token_y_se_rechaza_400(api, config):
    # Sin saldo configurado, GET /api/saldo no emite token_ingreso: cualquier
    # token enviado es desconocido y el ingreso se rechaza (400) sin guardar nada.
    assert api.get("/api/saldo").json()["token_ingreso"] is None
    assert _ingreso(api, "cualquiera").status_code == 400
    assert _contar(config, "ingreso") == 0


# --- Ajustes ---------------------------------------------------------------------------------

def test_ajuste_negativo_y_positivo(api, config):
    configurar_saldo(config, centavos=100000000)
    r = api.post("/api/ajustes", json={"saldo_real_centavos": 99954322})
    assert r.status_code == 200
    assert r.json() == {"registrado": True, "diferencia_centavos": -45678, "saldo_centavos": 99954322}
    r = api.post("/api/ajustes", json={"saldo_real_centavos": 99954323})
    assert r.json() == {"registrado": True, "diferencia_centavos": 1, "saldo_centavos": 99954323}
    assert api.get("/api/saldo").json()["saldo_centavos"] == 99954323
    assert _contar(config, "ajuste") == 2


def test_ajuste_cero_no_se_registra(api, config):
    configurar_saldo(config, centavos=100000000)
    r = api.post("/api/ajustes", json={"saldo_real_centavos": 100000000})
    assert r.status_code == 200
    assert r.json() == {"registrado": False, "diferencia_centavos": 0, "saldo_centavos": 100000000}
    assert _contar(config, "ajuste") == 0


def test_ajuste_sin_configurar_400(api, config):
    assert api.post("/api/ajustes", json={"saldo_real_centavos": 1}).status_code == 400
    assert _contar(config, "ajuste") == 0


@pytest.mark.parametrize("valor", [-1, 1.5, "100", None, True, saldo_politica.MAXIMO_CENTAVOS + 1])
def test_ajuste_valida_la_forma(api, config, valor):
    configurar_saldo(config)
    assert api.post("/api/ajustes", json={"saldo_real_centavos": valor}).status_code == 422
    assert _contar(config, "ajuste") == 0


# --- configuracion_fija: misma regla que el PUT de la configuración -------------------------

def _fija_segun_get_y_put(api):
    """Devuelve (lo que dice el GET, si el PUT rechaza el cambio)."""
    fija = api.get("/api/saldo").json()["configuracion_fija"]
    r = api.put("/api/saldo/configuracion", json={"saldo_inicial_centavos": 7777, "fecha_inicio": "2026-08-01"})
    assert r.status_code in (200, 400)
    if r.status_code == 400:
        assert "Ya hay movimientos" in r.json()["detalle"]
    return fija, r.status_code == 400


def _correo_no_reconocido(config):
    ejecutar_sql(config, "INSERT INTO correos_no_reconocidos VALUES (?, NULL, NULL)", ("id-inventado-nr",))


@pytest.mark.parametrize(
    ("preparar", "esperado"),
    [
        pytest.param(lambda config: None, False, id="sin-movimientos"),
        pytest.param(
            lambda config: insertar_movimiento(config, fecha_hora="2026-07-20T09:00:00", tipo="compra"),
            True,
            id="gasto-anterior-a-fecha-inicio",
        ),
        pytest.param(
            lambda config: insertar_movimiento(config, fecha_hora="2026-07-20T09:00:00", tipo="transferencia"),
            True,
            id="transferencia-anterior-a-fecha-inicio",
        ),
        pytest.param(lambda config: insertar_movimiento(config, tipo="compra"), True, id="gasto"),
        pytest.param(
            lambda config: insertar_movimiento(config, tipo="ingreso", origen="manual", descripcion="Ingreso inventado"),
            True,
            id="ingreso",
        ),
        pytest.param(
            lambda config: insertar_movimiento(config, tipo="ajuste", monto=-1500, origen="manual", descripcion=""),
            True,
            id="ajuste",
        ),
        pytest.param(_correo_no_reconocido, False, id="correo-no-reconocido"),
    ],
)
def test_configuracion_fija_coincide_con_el_put(api, config, preparar, esperado):
    configurar_saldo(config)
    preparar(config)
    fija, rechazado = _fija_segun_get_y_put(api)
    assert fija is esperado
    assert rechazado is esperado


def test_configuracion_fija_con_gasto_anterior_y_desglose_en_cero(api, config):
    # El caso que la pantalla no podía deducir: el desglose no ve el gasto.
    configurar_saldo(config)
    insertar_movimiento(config, fecha_hora="2026-07-20T09:00:00")
    datos = api.get("/api/saldo").json()
    assert datos["desglose"]["gastos_centavos"] == 0
    assert datos["desglose"]["ingresos_centavos"] == 0 and datos["desglose"]["ajustes_centavos"] == 0
    assert datos["configuracion_fija"] is True


def test_configuracion_fija_sin_configurar(api, config):
    assert api.get("/api/saldo").json()["configuracion_fija"] is False
    insertar_movimiento(config)
    fija, rechazado = _fija_segun_get_y_put(api)
    assert fija is True and rechazado is True


def test_configuracion_fija_pasa_a_true_al_registrar_un_ingreso(api):
    assert api.put("/api/saldo/configuracion", json={"saldo_inicial_centavos": 100, "fecha_inicio": "2026-08-01"}).status_code == 200
    datos = api.get("/api/saldo").json()
    assert datos["configuracion_fija"] is False
    assert _ingreso(api, datos["token_ingreso"]).status_code in (200, 201)
    fija, rechazado = _fija_segun_get_y_put(api)
    assert fija is True and rechazado is True


def test_funcion_configuracion_fija(config):
    from finanzas import db

    conn = db.conectar(config.db_path)
    try:
        assert componer_saldo(conn).configuracion_fija() is False
        insertar_movimiento(config, tipo="ajuste", monto=1, origen="manual")
        assert componer_saldo(conn).configuracion_fija() is True
    finally:
        conn.close()
