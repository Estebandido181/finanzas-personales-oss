"""API: metapruebas de seguridad sobre **todas** las rutas de ``/api`` (ítem 10).

Recorren el router, así una ruta nueva queda cubierta sin escribir nada:

* sin sesión, todas responden 401 en JSON (nunca redirigen), salvo el login;
* las que cambian datos rechazan con 403 la falta de token CSRF, un token
  ajeno, un ``Origin`` de otro sitio o un ``Sec-Fetch-Site`` de otro sitio,
  y con 415 un cuerpo que no es JSON;
* no hay CORS: nada responde ``Access-Control-Allow-Origin``.
"""

from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from finanzas.api import dependencias
from finanzas.api import ROUTERS

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import CONTRASENA, configurar_saldo, ejecutar_sql

LOGIN = ("POST", "/api/sesion")
QUE_CAMBIAN = {"POST", "PUT", "PATCH", "DELETE"}
TODAS_RUTAS = [ruta for router in ROUTERS for ruta in router.routes]


def _rutas() -> list[tuple[str, str]]:
    rutas = []
    for ruta in TODAS_RUTAS:
        assert isinstance(ruta, APIRoute)
        for metodo in sorted(ruta.methods):
            rutas.append((metodo, re.sub(r"\{[^}]+\}", "1", ruta.path)))
    return rutas


RUTAS = _rutas()
PROTEGIDAS = [r for r in RUTAS if r != LOGIN]
CAMBIAN = [r for r in PROTEGIDAS if r[0] in QUE_CAMBIAN]


def _pedir(cliente, metodo, ruta, **kwargs):
    if metodo in {"POST", "PUT", "PATCH"}:
        kwargs.setdefault("json", {})
    return cliente.request(metodo, ruta, **kwargs)


def _huella(config):
    """Todo lo que la API puede cambiar, para comprobar que un rechazo no cambió nada."""
    tablas = ("categorias", "movimientos", "reglas", "configuracion_saldo", "estado_sincronizacion",
              "importaciones", "cambios_importacion", "preguntas_conciliacion", "candidatos_pregunta", "reversiones_importacion", "descartes_movimientos")
    return {t: ejecutar_sql(config, f"SELECT * FROM {t} ORDER BY 1").fetchall() for t in tablas}


def test_hay_rutas_que_cubrir():
    assert len(RUTAS) >= 17
    assert LOGIN in RUTAS
    assert len(CAMBIAN) >= 7


def test_la_app_no_tiene_otras_rutas_api_que_las_del_router(app):
    # Se mira la descripción OpenAPI de la app completa (no se publica, pero
    # se puede generar): lista todas sus rutas, también las incluidas.
    en_app = {
        (metodo.upper(), ruta)
        for ruta, operaciones in app.openapi()["paths"].items()
        if ruta.startswith("/api")
        for metodo in operaciones
    }
    en_router = {(metodo, ruta.path) for ruta in TODAS_RUTAS for metodo in ruta.methods}
    assert en_app == en_router


def test_cada_ruta_declara_usuario_actual_y_las_que_cambian_el_csrf():
    for ruta in TODAS_RUTAS:
        llamadas = {d.call for d in ruta.dependant.dependencies}
        if ruta.path == "/api/sesion" and ruta.methods == {"POST"}:
            continue
        assert dependencias.usuario_actual in llamadas, ruta.path
        if ruta.methods & QUE_CAMBIAN:
            assert dependencias.exigir_csrf in llamadas, ruta.path


@pytest.mark.parametrize("metodo, ruta", PROTEGIDAS)
def test_sin_sesion_401_json(cliente, config, fabrica, metodo, ruta):
    configurar_saldo(config)
    antes = _huella(config)
    r = _pedir(cliente, metodo, ruta)
    assert r.status_code == 401
    assert r.json() == {"detalle": "Inicia sesión para continuar."}
    assert "location" not in r.headers
    assert fabrica.llamadas == 0
    assert _huella(config) == antes


@pytest.mark.parametrize("metodo", ["GET", "POST", "PUT", "DELETE", "PATCH"])
def test_ruta_api_inexistente_sin_sesion_401_y_con_sesion_404(cliente, metodo):
    assert _pedir(cliente, metodo, "/api/no-existe").status_code == 401
    assert _pedir(cliente, metodo, "/api").status_code == 401
    token = cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"]
    r = _pedir(cliente, metodo, "/api/no-existe", headers={"X-CSRF-Token": token})
    assert r.status_code == 404
    assert r.json() == {"detalle": "No encontrado."}


def test_cookie_manipulada_401(cliente):
    cliente.cookies.set("sesion", "valor-inventado-sin-firma")
    assert cliente.get("/api/reporte").status_code == 401


@pytest.mark.parametrize("metodo, ruta", CAMBIAN)
@pytest.mark.parametrize(
    "encabezados",
    [
        {},
        {"X-CSRF-Token": ""},
        {"X-CSRF-Token": "token-inventado"},
    ],
    ids=["sin-token", "token-vacio", "token-falso"],
)
def test_sin_token_csrf_valido_403(api, config, fabrica, metodo, ruta, encabezados):
    configurar_saldo(config)
    antes = _huella(config)
    r = _pedir(api.cliente, metodo, ruta, headers=encabezados)
    assert r.status_code == 403
    assert r.json() == {"detalle": dependencias.MENSAJE_CSRF}
    assert fabrica.llamadas == 0
    assert _huella(config) == antes
    assert api.get("/api/sesion").status_code == 200  # la sesión sigue


@pytest.mark.parametrize("metodo, ruta", CAMBIAN)
def test_token_de_otra_sesion_403(api, app, config, metodo, ruta):
    with TestClient(app, follow_redirects=False) as otro:
        ajeno = otro.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"]
    assert ajeno != api.csrf
    r = _pedir(api.cliente, metodo, ruta, headers={"X-CSRF-Token": ajeno})
    assert r.status_code == 403


@pytest.mark.parametrize("metodo, ruta", [r for r in RUTAS if r[0] in QUE_CAMBIAN])  # con el login
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
def test_otro_sitio_403_aunque_traiga_el_token(api, config, fabrica, metodo, ruta, encabezados):
    configurar_saldo(config)
    antes = _huella(config)
    r = _pedir(api.cliente, metodo, ruta, headers={**encabezados, "X-CSRF-Token": api.csrf})
    assert r.status_code == 403
    assert "detalle" in r.json()
    assert fabrica.llamadas == 0
    assert _huella(config) == antes


@pytest.mark.parametrize("metodo, ruta", [r for r in RUTAS if r[0] in {"POST", "PUT", "PATCH"}])
@pytest.mark.parametrize(
    "tipo", ["application/x-www-form-urlencoded", "multipart/form-data; boundary=x", "text/plain", None]
)
def test_cuerpo_que_no_es_json_415(api, config, metodo, ruta, tipo):
    configurar_saldo(config)
    antes = _huella(config)
    encabezados = {"X-CSRF-Token": api.csrf}
    if tipo:
        encabezados["Content-Type"] = tipo
    r = api.cliente.request(metodo, ruta, content=b"{}", headers=encabezados)
    assert r.status_code == 415
    assert _huella(config) == antes


def test_mismo_origen_se_acepta(api, config):
    configurar_saldo(config)
    r = api.post(
        "/api/ajustes",
        json={"saldo_real_centavos": 1},
        headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"},
    )
    assert r.status_code == 200


def test_los_get_no_exigen_token(api, config):
    # Las rutas de detalle requieren una importación existente; la creamos
    # mediante el flujo real antes de comprobar los GET sin token CSRF.
    from datetime import date
    from finanzas.api.rutas_importacion import MIME_XLSX
    from tests.soporte.excel_inventado import generar_excel

    configurar_saldo(config)
    archivo = generar_excel([(date(2026, 8, 10), "TIENDA INVENTADA", None, -500)])
    analisis = api.cliente.post("/api/importaciones/analizar", content=archivo,
        headers={"Content-Type": MIME_XLSX, "X-CSRF-Token": api.csrf})
    assert analisis.status_code == 200
    assert api.post("/api/importaciones", json={"token": analisis.json()["token"]}).status_code == 200
    archivos = api.cliente.post("/api/arranque/archivos", content=archivo,
        headers={"Content-Type": MIME_XLSX, "X-CSRF-Token": api.csrf})
    assert archivos.status_code == 200
    # Una lista real sí puede leerse sin CSRF; el placeholder «1» no es
    # un token emitido y debe conservar su 410, no convertirse en 200.
    assert api.get(f'/api/arranque/archivos/{archivos.json()["token"]}').status_code == 200
    inexistentes = {
        "/api/arranque/archivos/1": (410, "El historial cambió, venció o ya se usó. Vuelve a agregar tus archivos."),
        # La importación1 existe, pero es ordinaria, no un arranque guiado.
        "/api/arranque/1": (404, "Ese historial guiado no existe."),
    }
    for metodo, ruta in RUTAS:
        if metodo == "GET" and "{" not in ruta:
            respuesta = api.get(ruta)
            if ruta in inexistentes:
                codigo, detalle = inexistentes[ruta]
                assert respuesta.status_code == codigo, ruta
                assert respuesta.json() == {"detalle": detalle}
            else:
                assert respuesta.status_code == 200, ruta


@pytest.mark.parametrize("metodo, ruta", RUTAS)
def test_sin_cors(api, metodo, ruta):
    r = api.cliente.options(
        ruta,
        headers={
            "Origin": "https://sitio-malo.example",
            "Access-Control-Request-Method": metodo,
            "Access-Control-Request-Headers": "x-csrf-token, content-type",
        },
    )
    assert "access-control-allow-origin" not in r.headers
    r = api.get("/api/sesion", headers={"Origin": "https://sitio-malo.example"})
    assert "access-control-allow-origin" not in r.headers
    assert "access-control-allow-credentials" not in r.headers


def test_encabezados_de_seguridad_y_sin_cache(api):
    r = api.get("/api/reporte")
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["content-type"].startswith("application/json")
    api.delete("/api/sesion")  # también en los 401
    r = api.get("/api/reporte")
    assert r.status_code == 401 and r.headers["cache-control"] == "no-store"


def test_documentacion_automatica_sigue_desactivada(api):
    for ruta in ("/docs", "/redoc", "/openapi.json", "/api/openapi.json", "/api/docs"):
        assert api.get(ruta).status_code == 404, ruta
