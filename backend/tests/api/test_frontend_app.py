"""Frontend nuevo servido en ``/app`` (ítem 12, ``finanzas.web.frontend``).

Se prueba con una compilación falsa (archivos inventados en una carpeta
temporal): lo que importa es cómo se sirve, no el contenido.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from finanzas.web import frontend
from finanzas.web.app import ENCABEZADOS_SEGURIDAD, crear_app

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import CONTRASENA

INDICE = "<!doctype html><title>Finanzas</title><div id=raiz></div>"


@pytest.fixture
def dist(tmp_path):
    carpeta = tmp_path / "dist"
    (carpeta / "assets").mkdir(parents=True)
    (carpeta / "index.html").write_text(INDICE, encoding="utf-8")
    (carpeta / "tema-inicial.js").write_text("// tema", encoding="utf-8")
    (carpeta / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (carpeta / "assets" / "index-abc123.css").write_text("body{}", encoding="utf-8")
    (carpeta / "assets" / "fuente-abc123.woff2").write_bytes(b"wOF2")
    # Un archivo fuera del build: nunca debe poder leerse desde /app.
    (tmp_path / "secreto.txt").write_text("no", encoding="utf-8")
    return carpeta


@pytest.fixture
def cliente_app(config, fabrica, dist):
    app = crear_app(config, fabrica_cliente_gmail=fabrica, directorio_frontend=dist)
    with TestClient(app, follow_redirects=False) as c:
        yield c


def _entrar(cliente):
    r = cliente.post("/api/sesion", json={"contrasena": CONTRASENA})
    assert r.status_code == 200
    return r.json()["csrf_token"]


# --- Cascarón público --------------------------------------------------------


@pytest.mark.parametrize("ruta", ["/app/", "/app/saldo", "/app/mas", "/app/categorias/algo"])
def test_rutas_del_frontend_devuelven_el_indice_sin_sesion(cliente_app, ruta):
    r = cliente_app.get(ruta)
    assert r.status_code == 200
    assert r.text == INDICE
    assert r.headers["content-type"].startswith("text/html")
    # El cascarón no se guarda: al publicar otra versión se carga la nueva.
    assert r.headers["cache-control"] == "no-store"


def test_app_sin_barra_redirige(cliente_app):
    r = cliente_app.get("/app")
    assert r.status_code == 307
    assert r.headers["location"] == "/app/"


def test_head_funciona(cliente_app):
    assert cliente_app.head("/app/").status_code == 200
    assert cliente_app.head("/app/assets/index-abc123.js").status_code == 200


def test_el_indice_lleva_los_encabezados_de_seguridad(cliente_app):
    r = cliente_app.get("/app/")
    for nombre, valor in ENCABEZADOS_SEGURIDAD.items():
        assert r.headers[nombre] == valor
    csp = r.headers["content-security-policy"]
    assert "script-src 'self';" in csp and "style-src 'self';" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp


def test_el_cascaron_no_trae_datos_ni_cambia_la_sesion(cliente_app):
    r = cliente_app.get("/app/")
    assert "set-cookie" not in r.headers
    # Sin sesión, los datos siguen cerrados.
    assert cliente_app.get("/api/reporte").status_code == 401


# --- Archivos -----------------------------------------------------------------


def test_assets_con_hash_se_guardan_un_anio(cliente_app):
    r = cliente_app.get("/app/assets/index-abc123.js")
    assert r.status_code == 200
    assert r.text == "console.log(1)"
    assert r.headers["content-type"] == "text/javascript; charset=utf-8"
    assert r.headers["cache-control"] == frontend.CACHE_ASSETS
    # También llevan los encabezados de seguridad (nosniff: un tipo equivocado no se ejecuta).
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    ("archivo", "tipo"),
    [("index-abc123.css", "text/css; charset=utf-8"), ("fuente-abc123.woff2", "font/woff2")],
)
def test_tipos_de_los_assets(cliente_app, archivo, tipo):
    r = cliente_app.get(f"/app/assets/{archivo}")
    assert r.status_code == 200
    assert r.headers["content-type"] == tipo


def test_archivos_publicos_sin_hash_no_se_guardan(cliente_app):
    r = cliente_app.get("/app/tema-inicial.js")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/javascript; charset=utf-8"
    assert r.headers["cache-control"] == "no-store"


# --- Instalable en el celular (ítem 18) ---------------------------------------
# No hizo falta cambiar el servidor: estas pruebas fijan lo que la PWA necesita
# de él, para que un cambio futuro no lo rompa sin avisar.


@pytest.fixture
def dist_pwa(dist):
    (dist / "manifest.webmanifest").write_text('{"name": "Finanzas"}', encoding="utf-8")
    (dist / "sw.js").write_text("// sw", encoding="utf-8")
    (dist / "iconos").mkdir()
    (dist / "iconos" / "icono-192.png").write_bytes(b"\x89PNG")
    return dist


@pytest.fixture
def cliente_pwa(config, fabrica, dist_pwa):
    app = crear_app(config, fabrica_cliente_gmail=fabrica, directorio_frontend=dist_pwa)
    with TestClient(app, follow_redirects=False) as c:
        yield c


@pytest.mark.parametrize(
    ("ruta", "tipo"),
    [
        ("/app/manifest.webmanifest", "application/manifest+json"),
        # El service worker: JavaScript (con nosniff, otro tipo no se registra)
        # y sin caché HTTP, así el navegador siempre ve si hay versión nueva.
        ("/app/sw.js", "text/javascript; charset=utf-8"),
        ("/app/iconos/icono-192.png", "image/png"),
    ],
)
def test_manifest_service_worker_e_iconos_sin_sesion_y_sin_cache(cliente_pwa, ruta, tipo):
    r = cliente_pwa.get(ruta)
    assert r.status_code == 200
    assert r.headers["content-type"] == tipo
    assert r.headers["cache-control"] == "no-store"
    assert "set-cookie" not in r.headers  # no crean ni tocan la sesión
    assert r.headers["x-content-type-options"] == "nosniff"


def test_la_csp_permite_manifest_y_service_worker_propios_sin_abrirse():
    # manifest-src y worker-src no se declaran: heredan default-src 'self'
    # (y worker-src, script-src 'self'). Así solo valen los de este dominio.
    csp = ENCABEZADOS_SEGURIDAD["Content-Security-Policy"]
    assert "default-src 'self';" in csp
    assert "script-src 'self';" in csp
    assert "manifest-src" not in csp
    assert "worker-src" not in csp
    assert "unsafe-inline" not in csp


def test_la_api_nunca_se_puede_guardar(cliente_pwa):
    # El service worker no toca /api; además el servidor la marca no-store.
    _entrar(cliente_pwa)
    r = cliente_pwa.get("/api/sesion")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "ruta",
    [
        "/app/assets/no-existe.js",
        "/app/assets/",
        "/app/no-existe.js",
        "/app/index.html",  # el índice solo se sirve como cascarón, con no-store
        "/app/assets/%2e%2e/%2e%2e/secreto.txt",
        "/app/..%2fsecreto.txt",
        "/app/%2e%2e/secreto.txt",
    ],
)
def test_lo_que_no_existe_da_404_y_nunca_el_indice(cliente_app, ruta):
    r = cliente_app.get(ruta)
    assert r.status_code == 404
    assert r.headers["cache-control"] == "no-store"
    assert r.text != INDICE
    assert r.text != "no"  # el contenido de secreto.txt


def test_no_se_sale_de_la_carpeta(dist, config, fabrica):
    assert frontend._archivo_dentro(dist, "../secreto.txt") is None
    assert frontend._archivo_dentro(dist, "assets/../../secreto.txt") is None
    assert frontend._archivo_dentro(dist, "/etc/passwd") is None
    assert frontend._archivo_dentro(dist, "assets\x00.js") is None
    assert frontend._archivo_dentro(dist, "") is None
    assert frontend._archivo_dentro(dist, "assets") is None  # carpeta, no archivo
    assert frontend._archivo_dentro(dist, "tema-inicial.js") == (dist / "tema-inicial.js").resolve()


def test_solo_get_y_head(cliente_app):
    token = _entrar(cliente_app)
    r = cliente_app.post("/app/", json={}, headers={"X-CSRF-Token": token})
    assert r.status_code == 405


# --- Sin compilación ------------------------------------------------------------


def test_sin_compilar_la_app_arranca_y_app_lo_dice(config, fabrica, tmp_path):
    app = crear_app(config, fabrica_cliente_gmail=fabrica, directorio_frontend=tmp_path / "no-hay")
    with TestClient(app, follow_redirects=False) as c:
        r = c.get("/app/")
        assert r.status_code == 503
        assert "npm run build" in r.text
        assert "13.2" in r.text
        assert r.headers["content-security-policy"] == ENCABEZADOS_SEGURIDAD["Content-Security-Policy"]
        assert r.headers["cache-control"] == "no-store"
        r = c.get("/app/assets/index.js")
        assert r.status_code == 503 and r.headers["cache-control"] == "no-store"
        assert "npm ci --ignore-scripts" in r.text
        # Lo demás sigue igual.
        assert c.get("/").status_code == 307
        assert c.get("/api/sesion").status_code == 401


def test_por_defecto_usa_frontend_dist():
    assert frontend.DIRECTORIO_POR_DEFECTO.parts[-2:] == ("frontend", "dist")


# --- Lo demás (ítem 20: sin interfaz de plantillas) ------------------------------


def test_las_rutas_de_la_v1_llevan_a_la_app(cliente_app):
    for ruta, destino in (("/", "/app/"), ("/saldo", "/app/saldo"), ("/reglas", "/app/categorias"),
                          ("/sin-categorizar", "/app/movimientos"), ("/login", "/app/")):
        r = cliente_app.get(ruta)
        assert r.status_code == 307 and r.headers["location"] == destino, ruta


def test_rutas_parecidas_a_app_no_son_publicas_ni_el_frontend(cliente_app):
    # "/apple" o "/aplicacion" no son /app: no hay nada ahí (404, sin el índice).
    for ruta in ("/apple", "/aplicacion", "/app-otra"):
        r = cliente_app.get(ruta)
        assert r.status_code == 404, ruta
        assert INDICE not in r.text
        assert r.headers["cache-control"] == "no-store"


def test_con_sesion_el_frontend_y_la_api_comparten_login(cliente_app):
    _entrar(cliente_app)
    assert cliente_app.get("/app/saldo").text == INDICE
    assert cliente_app.get("/api/sesion").status_code == 200


def test_los_estaticos_de_la_v1_ya_no_existen(cliente_app):
    _entrar(cliente_app)
    for ruta in ("/static/estilos.css", "/static/reporte.js", "/static/confirmar.js"):
        r = cliente_app.get(ruta)
        assert r.status_code == 404, ruta
        assert r.headers["cache-control"] == "no-store"  # ya no es un prefijo cacheable
