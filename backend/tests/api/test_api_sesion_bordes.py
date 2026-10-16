"""Casos borde del login de la API (``/api/sesion``) y de ``Origin``.

Desde el ítem 20 el único login es ``POST /api/sesion``. Aquí está portada
la cobertura de seguridad que antes solo probaba el formulario de la v1
(``POST /login``, en ``test_login_bordes.py``, ``test_web.py`` y
``test_categorizacion_bordes.py``): cookie manipulada, bloqueo por IP que
vence y no se alarga, contraseñas raras, contraseña por la URL, renovación
de la sesión al entrar, nada de la contraseña en el registro y las
variantes de ``Origin``.

Todos los datos son inventados.
"""

from __future__ import annotations

import base64
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner

from finanzas.seguridad import LimitadorIntentos
from finanzas.web.app import crear_app

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import CONTRASENA, SECRETO, ejecutar_sql, hash_barato, insertar_movimiento

OTRO_SECRETO = "otro-secreto-inventado-distinto-de-mas-de-32-caracteres"
IP_A = ("203.0.113.10", 50000)  # rango de documentación (RFC 5737)
IP_B = ("203.0.113.20", 50000)
MALA = "incorrecta-inventada"


def _login(cliente, contrasena, **kwargs):
    return cliente.post("/api/sesion", json={"contrasena": contrasena}, **kwargs)


def _cookie_firmada(datos: dict, secreto: str) -> str:
    """Construye una cookie con el mismo formato que SessionMiddleware."""
    carga = base64.b64encode(json.dumps(datos).encode("utf-8"))
    return TimestampSigner(secreto).sign(carga).decode("utf-8")


def _datos_cookie(cookie: str) -> dict:
    carga = cookie.split(".", 1)[0]
    return json.loads(base64.b64decode(carga + "=" * (-len(carga) % 4)))


def _con_sesion(cliente) -> bool:
    return cliente.get("/api/sesion").status_code == 200


# --- Cookie de sesión manipulada ------------------------------------------------------------

def test_cookie_con_la_clave_correcta_entra(cliente):
    # Control: confirma que _cookie_firmada imita el formato real; si esta
    # prueba pasa, las de "otra clave" o "autenticado falso" son significativas.
    cliente.cookies.set("sesion", _cookie_firmada({"autenticado": True}, SECRETO))
    assert _con_sesion(cliente)


@pytest.mark.parametrize(
    "datos",
    [
        {"autenticado": False},
        {"autenticado": "true"},
        {"autenticado": 1},
        {"autenticado": None},
        {},
        {"otro": "dato-inventado"},
    ],
    ids=["falso", "texto", "uno", "nulo", "vacia", "sin-clave"],
)
def test_cookie_firmada_sin_autenticado_verdadero_no_entra(cliente, datos):
    cliente.cookies.set("sesion", _cookie_firmada(datos, SECRETO))
    r = cliente.get("/api/reporte")
    assert r.status_code == 401
    assert r.json() == {"detalle": "Inicia sesión para continuar."}


def test_cookie_firmada_con_otra_clave_no_entra(cliente):
    cliente.cookies.set("sesion", _cookie_firmada({"autenticado": True}, OTRO_SECRETO))
    assert cliente.get("/api/reporte").status_code == 401


def test_cookie_sin_firma_no_entra(cliente):
    cliente.cookies.set("sesion", base64.b64encode(b'{"autenticado": true}').decode())
    assert cliente.get("/api/reporte").status_code == 401


def test_cookie_valida_con_carga_alterada_no_entra(cliente):
    original = _login(cliente, CONTRASENA).cookies["sesion"]
    _, resto = original.split(".", 1)
    falsa = base64.b64encode(json.dumps({"autenticado": True, "x": 1}).encode()).decode()
    cliente.cookies.clear()
    cliente.cookies.set("sesion", f"{falsa}.{resto}")
    assert cliente.get("/api/reporte").status_code == 401


@pytest.mark.parametrize("basura", ["no-es-una-cookie-valida!!", "a.b.c", "", "=" * 50, "%C3%B1" * 10])
def test_cookie_basura_no_rompe_la_app(cliente, basura):
    cliente.cookies.set("sesion", basura)
    r = cliente.get("/api/reporte")
    assert r.status_code == 401
    assert r.json() == {"detalle": "Inicia sesión para continuar."}
    # Con la cookie basura todavía se puede entrar.
    assert _login(cliente, CONTRASENA).status_code == 200
    assert _con_sesion(cliente)


def test_cookie_reutilizada_despues_de_cerrar_sesion_sigue_valida(api):
    """DOCUMENTA el comportamiento actual, no lo juzga (ver la especificación).

    SessionMiddleware guarda la sesión en la propia cookie firmada (no hay
    estado en el servidor). Cerrar sesión borra la cookie del navegador, pero
    una copia guardada antes sigue valiendo hasta que caduca (7 días); para
    invalidarlas todas se cambia ``SESSION_SECRET``.
    """
    copia = api.cliente.cookies.get("sesion")
    assert api.delete("/api/sesion").status_code == 204
    assert not _con_sesion(api.cliente)  # el navegador ya no tiene sesión
    api.cliente.cookies.clear()
    api.cliente.cookies.set("sesion", copia)
    assert _con_sesion(api.cliente)  # la copia reutilizada entra


def test_cookie_httponly_lax_y_de_7_dias(cliente):
    cookie = _login(cliente, CONTRASENA).headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=604800" in cookie  # la especificación fija la sesión en 7 días
    assert "secure" not in cookie  # cookie_secure=False en la configuración de prueba


# --- Bloqueo por IP ----------------------------------------------------------------------------

def test_bloqueo_es_por_ip(app):
    with TestClient(app, client=IP_A) as a, TestClient(app, client=IP_B) as b:
        for _ in range(3):
            assert _login(a, MALA).status_code == 401
        assert _login(a, CONTRASENA).status_code == 429
        assert not _con_sesion(a)
        # Otra IP no queda afectada.
        assert _login(b, CONTRASENA).status_code == 200
        assert _con_sesion(b)


def test_bloqueado_con_sesion_previa_sigue_dentro(app):
    """Documenta: el bloqueo solo afecta al login, no a sesiones ya abiertas."""
    with TestClient(app, client=IP_A) as a:
        assert _login(a, CONTRASENA).status_code == 200
        for _ in range(3):
            _login(a, MALA)
        assert _login(a, CONTRASENA).status_code == 429
        assert _con_sesion(a)


def _app_con_reloj(config, fabrica):
    reloj = {"t": 1000.0}
    app = crear_app(config, fabrica_cliente_gmail=fabrica)
    app.state.limitador = LimitadorIntentos(3, 15, reloj=lambda: reloj["t"])
    return app, reloj


def test_el_bloqueo_vence_y_vuelve_a_contar_desde_cero(config, fabrica):
    app, reloj = _app_con_reloj(config, fabrica)
    with TestClient(app) as c:
        for _ in range(3):
            _login(c, MALA)
        assert _login(c, CONTRASENA).status_code == 429
        reloj["t"] += 15 * 60 - 1
        assert _login(c, CONTRASENA).status_code == 429  # aún no vence
        reloj["t"] += 2
        assert _login(c, CONTRASENA).status_code == 200
        # Contador en cero: dos fallos más no bloquean.
        for _ in range(2):
            assert _login(c, MALA).status_code == 401
        assert _login(c, CONTRASENA).status_code == 200


def test_intentos_durante_el_bloqueo_no_alargan_el_bloqueo(config, fabrica):
    app, reloj = _app_con_reloj(config, fabrica)
    with TestClient(app) as c:
        for _ in range(3):
            _login(c, MALA)
        reloj["t"] += 10 * 60
        for _ in range(5):
            r = _login(c, MALA)
            assert r.status_code == 429
            assert "Espera" in r.json()["detalle"]
        reloj["t"] += 5 * 60 + 1
        assert _login(c, CONTRASENA).status_code == 200


def test_bloqueado_no_revela_si_la_contrasena_era_correcta(cliente):
    for _ in range(3):
        _login(cliente, MALA)
    correcta, incorrecta = _login(cliente, CONTRASENA), _login(cliente, MALA)
    assert correcta.status_code == incorrecta.status_code == 429
    assert correcta.json() == incorrecta.json()
    assert "set-cookie" not in correcta.headers


# --- Contraseña vacía, ausente, muy larga, con espacios o unicode -----------------------------

def test_contrasena_vacia_no_entra_y_cuenta_como_fallo(cliente):
    for _ in range(3):
        assert _login(cliente, "").status_code == 401
    assert _login(cliente, CONTRASENA).status_code == 429


def test_sin_campo_contrasena_no_entra_ni_cuenta(cliente):
    for _ in range(5):
        assert cliente.post("/api/sesion", json={}).status_code == 422
    assert not _con_sesion(cliente)
    assert _login(cliente, CONTRASENA).status_code == 200  # los 422 no gastaron intentos


def test_contrasena_muy_larga_no_entra_ni_rompe(cliente):
    r = _login(cliente, "x" * 100_000)
    assert r.status_code == 422  # tope de 1024 caracteres: no llega a scrypt
    assert "x" * 50 not in r.text
    assert _login(cliente, "x" * 1024).status_code == 401  # en el tope: se comprueba y falla
    assert _login(cliente, CONTRASENA).status_code == 200


@pytest.mark.parametrize("variante", [f" {CONTRASENA} ", f"{CONTRASENA} ", f" {CONTRASENA}",
                                      f"{CONTRASENA}\n", CONTRASENA.upper()])
def test_contrasena_con_espacios_o_mayusculas_no_entra(cliente, variante):
    assert _login(cliente, variante).status_code == 401
    assert not _con_sesion(cliente)


def test_contrasena_unicode_inventada(config, fabrica):
    clave = "contraseña-ñandú-🔒-inventada"
    app = crear_app(replace(config, app_password_hash=hash_barato(clave)), fabrica_cliente_gmail=fabrica)
    with TestClient(app) as c:
        # Otra forma de normalización (n + tilde combinada) no es la misma clave.
        assert _login(c, clave.replace("ñ", "ñ")).status_code == 401
        assert _login(c, clave).status_code == 200
        assert _con_sesion(c)


def test_login_no_acepta_la_contrasena_por_query_string(cliente):
    assert cliente.post(f"/api/sesion?contrasena={CONTRASENA}").status_code == 415
    r = cliente.post(f"/api/sesion?contrasena={CONTRASENA}", json={})
    assert r.status_code == 422
    assert CONTRASENA not in r.text
    assert not _con_sesion(cliente)


def test_get_con_la_contrasena_en_la_url_no_inicia_sesion(cliente):
    assert cliente.get(f"/api/sesion?contrasena={CONTRASENA}").status_code == 401
    assert not _con_sesion(cliente)


# --- Sesión nueva al entrar (fijación de sesión) -----------------------------------------------

def test_login_exitoso_renueva_la_sesion(cliente):
    # Lo que hubiera en la sesión (puesto por otro, por ejemplo) se descarta al entrar.
    plantada = {"otro": "dato-inventado", "csrf_token": "token-plantado-inventado"}
    cliente.cookies.set("sesion", _cookie_firmada(plantada, SECRETO))
    r = _login(cliente, CONTRASENA)
    assert r.status_code == 200
    datos = _datos_cookie(r.cookies["sesion"])
    assert set(datos) == {"autenticado", "csrf_token"}
    assert datos["autenticado"] is True
    assert datos["csrf_token"] == r.json()["csrf_token"] != "token-plantado-inventado"


def test_login_fallido_no_toca_la_sesion_existente(api):
    # Un intento fallido con sesión abierta no la cierra ni cambia el token.
    assert _login(api.cliente, MALA).status_code == 401
    assert api.get("/api/sesion").json()["csrf_token"] == api.csrf


# --- Registro (logs) ---------------------------------------------------------------------------

def test_login_fallido_ni_bloqueado_dejan_la_contrasena_en_el_registro(cliente, caplog):
    secreta = "clave-secreta-que-no-debe-aparecer"
    with caplog.at_level("DEBUG"):
        for _ in range(4):  # 3 fallos y uno ya bloqueado
            _login(cliente, secreta)
        _login(cliente, CONTRASENA)
    assert "Login fallido" in caplog.text  # sí se registra que falló…
    assert secreta not in caplog.text  # …pero nunca la contraseña
    assert CONTRASENA not in caplog.text
    assert "scrypt" not in caplog.text


# --- Cache-Control en todas las respuestas del login -------------------------------------------

def test_cache_control_no_store_en_el_login(cliente):
    assert _login(cliente, MALA).headers["cache-control"] == "no-store"
    assert cliente.post("/api/sesion", json={}).headers["cache-control"] == "no-store"
    ok = _login(cliente, CONTRASENA)
    assert ok.status_code == 200 and ok.headers["cache-control"] == "no-store"
    cliente.cookies.clear()
    for _ in range(3):
        _login(cliente, MALA)
    r = _login(cliente, CONTRASENA)
    assert r.status_code == 429 and r.headers["cache-control"] == "no-store"


# --- Origin (portado de test_categorizacion_bordes.py) ----------------------------------------

def test_login_legitimo_con_origin_propio(cliente):
    r = _login(cliente, CONTRASENA, headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200
    assert "sesion" in r.cookies
    assert cliente.get("/api/movimientos").status_code == 200


def test_login_legitimo_sin_origin(cliente):
    assert _login(cliente, CONTRASENA).status_code == 200
    assert cliente.get("/api/reglas").status_code == 200


ORIGENES_PROPIOS = ["http://testserver", "http://TESTSERVER", "http://testserver:80",
                    "http://testserver/", " http://testserver "]
ORIGENES_AJENOS = ["null", "https://malo.example", "http://testserver:8000", "http://testserver:443",
                   "http://testserver@malo.example", "http://malo.example@testserver", "http://testserver.",
                   "//testserver", "javascript:alert(1)", "file://testserver", "",
                   "http://testserver.malo.example"]


def _estado(config):
    return (
        ejecutar_sql(config, "SELECT id, categoria_id FROM movimientos ORDER BY id").fetchall(),
        ejecutar_sql(config, "SELECT id, categoria_id FROM reglas ORDER BY id").fetchall(),
    )


@pytest.mark.parametrize("origen", ORIGENES_PROPIOS)
def test_origin_propio_en_sus_variantes_se_acepta(api, config, origen):
    m = insertar_movimiento(config)
    r = api.put(f"/api/movimientos/{m}/categoria", json={"categoria_id": 1, "recordar": False},
                headers={"Origin": origen})
    assert r.status_code == 200, r.text
    assert ejecutar_sql(config, "SELECT categoria_id FROM movimientos WHERE id = ?", (m,)).fetchone()[0] == 1


@pytest.mark.parametrize("origen", ORIGENES_PROPIOS)
def test_origin_propio_en_el_login_se_acepta(cliente, origen):
    assert _login(cliente, CONTRASENA, headers={"Origin": origen}).status_code == 200


@pytest.mark.parametrize("origen", ORIGENES_AJENOS)
def test_origin_ajeno_o_raro_da_403_sin_cambios(api, config, origen):
    m = insertar_movimiento(config)
    api.put(f"/api/movimientos/{insertar_movimiento(config, descripcion='TIENDA REGLA')}/categoria",
            json={"categoria_id": 1, "recordar": True})
    rid = ejecutar_sql(config, "SELECT id FROM reglas").fetchone()[0]
    antes = _estado(config)
    for metodo, ruta, cuerpo in [
        ("PUT", f"/api/movimientos/{m}/categoria", {"categoria_id": 1, "recordar": True}),
        ("DELETE", f"/api/reglas/{rid}", None),
        ("DELETE", "/api/sesion", None),
    ]:
        kwargs = {"json": cuerpo} if cuerpo is not None else {}
        r = api.cliente.request(metodo, ruta, headers={"Origin": origen, "X-CSRF-Token": api.csrf}, **kwargs)
        assert r.status_code == 403, (ruta, origen)
        assert r.json() == {"detalle": "Petición rechazada: no viene de esta página."}
    assert _estado(config) == antes
    assert _con_sesion(api.cliente)  # DELETE /api/sesion no se ejecutó


@pytest.mark.parametrize("origen", ORIGENES_AJENOS)
def test_origin_ajeno_en_login_con_contrasena_correcta_no_da_sesion(cliente, origen):
    r = _login(cliente, CONTRASENA, headers={"Origin": origen})
    assert r.status_code == 403
    assert "sesion" not in r.cookies and "set-cookie" not in r.headers
    assert not _con_sesion(cliente)


def test_origin_ajeno_en_login_no_gasta_intentos(cliente):
    for _ in range(5):
        assert _login(cliente, MALA, headers={"Origin": "https://malo.example"}).status_code == 403
    assert _login(cliente, CONTRASENA).status_code == 200


# --- Lo que viene de un correo sale como JSON, nunca como HTML ---------------------------------

@pytest.mark.parametrize("carga", ['<script>alert("xss")</script>', '"><svg onload=alert(1)>', "{{ 7*7 }}"])
def test_descripcion_con_html_sale_como_dato_json(api, config, carga):
    """Antes se probaba el escapado de las plantillas; ahora la API no genera
    HTML: devuelve el texto tal cual en JSON (lo pinta React, que escapa), con
    ``nosniff`` para que el navegador nunca lo interprete como página."""
    insertar_movimiento(config, descripcion=f"TIENDA {carga}")
    r = api.get("/api/movimientos/sin-categorizar")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert f"TIENDA {carga}" in [mov["descripcion"] for mov in r.json()["movimientos"]]
