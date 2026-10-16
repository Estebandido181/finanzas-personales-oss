"""API, ítem 16: pantalla de saldo (desglose, ingresos y ajustes del mes) y borrar un ingreso manual.

Las restricciones se prueban llamando directo a la API. Datos inventados.
"""

from __future__ import annotations
from finanzas.modulos.saldo import politica as saldo_politica

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from finanzas.compartido import hora
from finanzas.api import dependencias

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import CONTRASENA, configurar_saldo, ejecutar_sql, insertar_movimiento

AHORA = datetime(2026, 9, 15, 12, 0, 0)


@pytest.fixture
def reloj(monkeypatch):
    class Reloj:
        actual = AHORA

    r = Reloj()
    monkeypatch.setattr(hora, "ahora_colombia", lambda: r.actual)
    return r


@pytest.fixture
def con_saldo(config, reloj):
    configurar_saldo(config, centavos=1_250_000_00, fecha="2026-09-01")
    return config


def _ingreso(api, monto=150_000_00, fecha_hora="2026-09-12T10:00", descripcion="Efectivo venta inventada"):
    token = api.get("/api/saldo").json()["token_ingreso"]
    r = api.post(
        "/api/ingresos",
        json={"monto_centavos": monto, "fecha_hora": fecha_hora, "descripcion": descripcion, "token": token},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _ajuste(api, reloj, momento, saldo_real):
    reloj.actual = momento
    r = api.post("/api/ajustes", json={"saldo_real_centavos": saldo_real})
    reloj.actual = AHORA
    assert r.status_code == 200 and r.json()["registrado"], r.text


def _huella(config):
    return ejecutar_sql(config, "SELECT * FROM movimientos ORDER BY id").fetchall()


def _id_de(config, tipo):
    return ejecutar_sql(config, "SELECT MAX(id) FROM movimientos WHERE tipo = ?", (tipo,)).fetchone()[0]


# --- GET /api/saldo -------------------------------------------------------------------------

def test_saldo_sin_configurar_trae_lo_nuevo_vacio(api, reloj):
    datos = api.get("/api/saldo").json()
    assert datos["desglose"] is None and datos["ajustes_del_mes"] is None
    assert datos["del_mes"] == []
    assert datos["mes"] == "2026-09" and datos["nombre_mes"] == "septiembre de 2026"


def test_pantalla_de_saldo(api, con_saldo, reloj):
    insertar_movimiento(con_saldo, "2026-08-31T23:00:00", 9_99, "compra")  # antes del inicio
    insertar_movimiento(con_saldo, "2026-09-02T08:00:00", 1_842_450_00, "compra")
    insertar_movimiento(con_saldo, "2026-09-04T08:00:00", 4_800_000_00, "ingreso", "EMPRESA EJEMPLO S.A.S.")
    insertar_movimiento(con_saldo, "2026-09-12T15:45:00", 400_000_00, "ingreso", "CARLOS EJEMPLO")
    _ajuste(api, reloj, datetime(2026, 9, 13, 9, 10), 1_250_000_00 + 5_200_000_00 - 1_842_450_00 - 6_000_50)
    _ajuste(api, reloj, datetime(2026, 9, 14, 19, 30), 1_250_000_00 + 5_200_000_00 - 1_842_450_00 - 18_400_00)
    id_borrable = _ingreso(api, 150_000_00, "2026-09-15T10:00")

    datos = api.get("/api/saldo").json()
    assert datos["desglose"] == {
        "saldo_inicial_centavos": 1_250_000_00,
        "ingresos_centavos": 5_350_000_00,
        "gastos_centavos": 1_842_450_00,
        "ajustes_centavos": -18_400_00,
    }
    assert datos["saldo_centavos"] == 1_250_000_00 + 5_350_000_00 - 1_842_450_00 - 18_400_00
    assert datos["ajustes_del_mes"] == {"total_centavos": -18_400_00, "cantidad": 2}
    filas = datos["del_mes"]
    assert [(f["tipo"], f["origen"]) for f in filas] == [
        ("ingreso", "manual"), ("ajuste", "manual"), ("ajuste", "manual"), ("ingreso", "gmail"), ("ingreso", "gmail"),
    ]
    assert [f["id"] for f in filas if f["se_puede_borrar"]] == [id_borrable]
    assert filas[0] == {
        "id": id_borrable, "fecha_hora": "2026-09-15T10:00:00", "tipo": "ingreso",
        "descripcion": "Efectivo venta inventada", "monto_centavos": 150_000_00,
        "origen": "manual", "se_puede_borrar": True,
    }


def test_del_mes_es_solo_el_mes_actual(api, con_saldo, reloj):
    reloj.actual = datetime(2026, 10, 1, 0, 0, 0)
    _ingreso(api, 1_00, "2026-09-30T23:59")
    datos = api.get("/api/saldo").json()
    assert datos["mes"] == "2026-10" and datos["del_mes"] == []
    assert datos["ajustes_del_mes"] == {"total_centavos": 0, "cantidad": 0}
    assert datos["desglose"]["ingresos_centavos"] == 1_00


# --- DELETE /api/ingresos/{id} ---------------------------------------------------------------

def test_borrar_ingreso_baja_el_saldo_exactamente_en_su_monto(api, con_saldo):
    insertar_movimiento(con_saldo, "2026-09-02T08:00:00", 12_345_67, "compra")
    id_ingreso = _ingreso(api, 150_000_37)
    antes = api.get("/api/saldo").json()["saldo_centavos"]

    r = api.delete(f"/api/ingresos/{id_ingreso}")
    assert r.status_code == 200
    datos_borrado = r.json()
    assert set(datos_borrado.pop("deshacer")) == {"token", "segundos"}  # ítem 38
    assert datos_borrado == {"id": id_ingreso, "monto_centavos": 150_000_37, "saldo_centavos": antes - 150_000_37}
    datos = api.get("/api/saldo").json()
    assert datos["saldo_centavos"] == antes - 150_000_37
    assert datos["desglose"]["ingresos_centavos"] == 0
    assert all(f["id"] != id_ingreso for f in datos["del_mes"])

    r = api.delete(f"/api/ingresos/{id_ingreso}")
    assert r.status_code == 404
    assert r.json() == {"detalle": saldo_politica.MENSAJE_INGRESO_NO_EXISTE}
    assert api.get("/api/saldo").json()["saldo_centavos"] == antes - 150_000_37


def test_borrar_ingreso_posterior_al_ultimo_ajuste(api, con_saldo, reloj):
    _ajuste(api, reloj, datetime(2026, 9, 10, 8, 0), 1_000_000_00)
    id_ingreso = _ingreso(api, 5_00, "2026-09-11T08:00")
    r = api.delete(f"/api/ingresos/{id_ingreso}")
    assert r.status_code == 200
    assert r.json()["saldo_centavos"] == 1_000_000_00  # el saldo que se cuadró


def _prohibido(api, config, movimiento_id, mensaje):
    antes, saldo_antes = _huella(config), api.get("/api/saldo").json()["saldo_centavos"]
    r = api.delete(f"/api/ingresos/{movimiento_id}")
    assert r.status_code == 409
    assert r.json() == {"detalle": mensaje}
    assert _huella(config) == antes
    assert api.get("/api/saldo").json()["saldo_centavos"] == saldo_antes


def test_no_se_borra_un_ajuste(api, con_saldo, reloj):
    _ajuste(api, reloj, datetime(2026, 9, 10, 8, 0), 1_000_000_00)
    _prohibido(api, con_saldo, _id_de(con_saldo, "ajuste"), saldo_politica.MENSAJE_NO_SE_BORRA_AJUSTE)


@pytest.mark.parametrize("tipo", ["ingreso", "compra", "transferencia"])
def test_no_se_borra_un_movimiento_de_gmail(api, con_saldo, tipo):
    id_gmail = insertar_movimiento(con_saldo, "2026-09-02T08:00:00", 4_800_000_00, tipo)
    _prohibido(api, con_saldo, id_gmail, saldo_politica.MENSAJE_NO_SE_BORRA_GMAIL)


def test_no_se_borra_un_ingreso_anterior_al_ultimo_ajuste(api, con_saldo, reloj):
    id_ingreso = _ingreso(api, 150_000_00, "2026-09-05T08:00")
    _ajuste(api, reloj, datetime(2026, 9, 10, 8, 0), 1_000_000_00)
    _prohibido(api, con_saldo, id_ingreso, saldo_politica.MENSAJE_ANTERIOR_AL_AJUSTE)


def test_no_se_borra_un_ingreso_con_fecha_anterior_al_ultimo_ajuste(api, con_saldo, reloj):
    _ajuste(api, reloj, datetime(2026, 9, 10, 8, 0), 1_000_000_00)
    id_ingreso = _ingreso(api, 150_000_00, "2026-09-09T08:00")
    _prohibido(api, con_saldo, id_ingreso, saldo_politica.MENSAJE_ANTERIOR_AL_AJUSTE)


@pytest.mark.parametrize("valor", ["0", "-1", "abc", "1.5", str(10**19)])
def test_id_invalido_422(api, con_saldo, valor):
    _ingreso(api)
    antes = _huella(con_saldo)
    assert api.delete(f"/api/ingresos/{valor}").status_code == 422
    assert _huella(con_saldo) == antes


# --- Seguridad: sesión, CSRF y Origin, con un ingreso que sí se podría borrar ---------------------

@pytest.fixture
def borrable(api, con_saldo):
    return _ingreso(api)


def _sigue(config, movimiento_id):
    return ejecutar_sql(config, "SELECT COUNT(*) FROM movimientos WHERE id = ?", (movimiento_id,)).fetchone()[0] == 1


def test_sin_sesion_401(app, con_saldo, borrable):
    with TestClient(app, follow_redirects=False) as anonimo:
        r = anonimo.delete(f"/api/ingresos/{borrable}")
    assert r.status_code == 401
    assert _sigue(con_saldo, borrable)


def test_sesion_cerrada_401(api, con_saldo, borrable):
    csrf = api.csrf
    assert api.delete("/api/sesion").status_code == 204
    r = api.cliente.delete(f"/api/ingresos/{borrable}", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 401
    assert _sigue(con_saldo, borrable)


@pytest.mark.parametrize(
    "encabezados", [{}, {"X-CSRF-Token": ""}, {"X-CSRF-Token": "token-inventado"}],
    ids=["sin-token", "token-vacio", "token-falso"],
)
def test_sin_csrf_valido_403(api, con_saldo, borrable, encabezados):
    r = api.cliente.delete(f"/api/ingresos/{borrable}", headers=encabezados)
    assert r.status_code == 403
    assert r.json() == {"detalle": dependencias.MENSAJE_CSRF}
    assert _sigue(con_saldo, borrable)


def test_csrf_de_otra_sesion_403(api, app, con_saldo, borrable):
    with TestClient(app, follow_redirects=False) as otro:
        ajeno = otro.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"]
    r = api.cliente.delete(f"/api/ingresos/{borrable}", headers={"X-CSRF-Token": ajeno})
    assert r.status_code == 403
    assert _sigue(con_saldo, borrable)


@pytest.mark.parametrize(
    "encabezados",
    [
        {"Origin": "https://sitio-malo.example"},
        {"Origin": "null"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ],
    ids=["origin-ajeno", "origin-null", "cross-site", "same-site"],
)
def test_otro_sitio_403_aunque_traiga_el_token(api, con_saldo, borrable, encabezados):
    r = api.cliente.delete(f"/api/ingresos/{borrable}", headers={**encabezados, "X-CSRF-Token": api.csrf})
    assert r.status_code == 403
    assert _sigue(con_saldo, borrable)


def test_mismo_origen_se_acepta(api, con_saldo, borrable):
    r = api.delete(
        f"/api/ingresos/{borrable}",
        headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"},
    )
    assert r.status_code == 200
    assert not _sigue(con_saldo, borrable)
    assert "access-control-allow-origin" not in r.headers


def test_no_se_borra_un_ingreso_conciliado_con_el_banco(api, con_saldo):
    """Ítem 29: confirmado por el banco -> 409 con mensaje claro, no un 500."""
    from datetime import date

    from finanzas import db, importacion
    from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import MovimientoExcel

    id_ingreso = _ingreso(api, 150_000_00, "2026-09-12T10:00")
    conn = db.conectar(con_saldo.db_path)
    try:
        importacion.importar(conn, [MovimientoExcel(date(2026, 9, 12), 150_000_00, "ABONO EJEMPLO")])
    finally:
        conn.close()
    _prohibido(api, con_saldo, id_ingreso, saldo_politica.MENSAJE_CONCILIADO)
