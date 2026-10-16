"""API: login, estado de la sesión y cierre (ítem 10). Datos inventados."""

from __future__ import annotations

from fastapi.testclient import TestClient

from finanzas.web.app import crear_app

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import CONTRASENA


def test_login_correcto_devuelve_usuario_y_token(cliente):
    r = cliente.post("/api/sesion", json={"contrasena": CONTRASENA})
    assert r.status_code == 200
    datos = r.json()
    assert datos["usuario"] == {"id": "dueno", "nombre": "Dueño"}
    assert len(datos["csrf_token"]) >= 40
    assert "sesion" in r.cookies or cliente.cookies.get("sesion")


def test_login_incorrecto_401_json_sin_repetir_la_contrasena(cliente):
    r = cliente.post("/api/sesion", json={"contrasena": "otra-clave-inventada"})
    assert r.status_code == 401
    assert r.json() == {"detalle": "Contraseña incorrecta."}
    assert "otra-clave-inventada" not in r.text
    assert cliente.get("/api/sesion").status_code == 401


def test_login_sin_contrasena_o_con_campos_de_mas_es_422_sin_eco(cliente):
    r = cliente.post("/api/sesion", json={})
    assert r.status_code == 422
    r = cliente.post("/api/sesion", json={"contrasena": "clave-eco-inventada", "extra": 1})
    assert r.status_code == 422
    assert "clave-eco-inventada" not in r.text  # los 422 nunca repiten los valores
    assert r.json()["detalle"] == "Revisa los datos enviados."


def test_login_con_contrasena_no_texto_es_422(cliente):
    assert cliente.post("/api/sesion", json={"contrasena": 12345}).status_code == 422


def test_login_como_formulario_se_rechaza_con_415(cliente):
    r = cliente.post("/api/sesion", data={"contrasena": CONTRASENA})
    assert r.status_code == 415
    assert cliente.get("/api/sesion").status_code == 401


def test_login_json_sin_content_type_se_rechaza(cliente):
    # Un fetch con un Blob sin tipo no manda Content-Type: FastAPI lo leería como JSON.
    r = cliente.post("/api/sesion", content=b'{"contrasena": "clave-de-prueba-inventada"}')
    assert r.status_code == 415
    assert cliente.get("/api/sesion").status_code == 401


def test_limite_de_intentos(cliente):
    # max_intentos=3 en la configuración de prueba.
    for _ in range(3):
        assert cliente.post("/api/sesion", json={"contrasena": "mala-inventada"}).status_code == 401
    r = cliente.post("/api/sesion", json={"contrasena": CONTRASENA})
    assert r.status_code == 429
    assert r.json() == {"detalle": "Demasiados intentos fallidos. Espera unos minutos y vuelve a intentarlo."}
    assert cliente.get("/api/sesion").status_code == 401


def test_el_login_de_la_v1_ya_no_existe_ni_cuenta_intentos(cliente):
    # Ítem 20: POST /login se retiró (GET /login solo redirige a /app/).
    for _ in range(5):
        r = cliente.post("/login", data={"contrasena": "mala-inventada"})
        assert r.status_code == 405
        assert "set-cookie" not in r.headers
    r = cliente.post("/login", data={"contrasena": CONTRASENA})
    assert r.status_code == 405 and "set-cookie" not in r.headers
    assert cliente.get("/api/sesion").status_code == 401
    # Los 405 no gastaron intentos: el login de la API sigue disponible.
    assert cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).status_code == 200


def test_login_correcto_reinicia_el_contador(cliente):
    for _ in range(2):
        cliente.post("/api/sesion", json={"contrasena": "mala-inventada"})
    assert cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).status_code == 200
    for _ in range(2):
        cliente.post("/api/sesion", json={"contrasena": "mala-inventada"})
    assert cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).status_code == 200


def test_estado_de_sesion(api):
    r = api.get("/api/sesion")
    assert r.status_code == 200
    assert r.json() == {"usuario": {"id": "dueno", "nombre": "Dueño"}, "csrf_token": api.csrf}


def test_cada_login_rota_el_token(cliente):
    uno = cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"]
    dos = cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"]
    assert uno != dos
    assert cliente.get("/api/sesion").json()["csrf_token"] == dos


def test_cerrar_sesion(api):
    r = api.delete("/api/sesion")
    assert r.status_code == 204
    assert api.get("/api/sesion").status_code == 401
    assert api.get("/api/reporte").status_code == 401


def test_cerrar_sesion_sin_token_no_cierra(api):
    r = api.cliente.delete("/api/sesion")
    assert r.status_code == 403
    assert api.get("/api/sesion").status_code == 200


def test_cookie_de_sesion_segura_en_produccion(config, fabrica):
    from dataclasses import replace

    app = crear_app(replace(config, cookie_secure=True), fabrica_cliente_gmail=fabrica)
    with TestClient(app, base_url="https://testserver", follow_redirects=False) as c:
        r = c.post("/api/sesion", json={"contrasena": CONTRASENA})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
