"""Pruebas de la app web (ítem 20): rutas de la v1 que redirigen a ``/app``,
404 para lo demás, encabezados de seguridad (CSP incluida), ``Origin`` y
configuración.

La seguridad del login está en ``test_api_sesion.py`` y
``test_api_sesion_bordes.py``; la de la API, en ``test_api_seguridad.py`` y
``test_api_bordes.py``. Todos los datos son inventados.
"""

import pytest
from fastapi.testclient import TestClient

from finanzas.compartido.config import Config, ErrorConfiguracion
from finanzas.seguridad import generar_hash
from finanzas.web.app import ENCABEZADOS_SEGURIDAD, crear_app, origen_permitido
from finanzas import db

CONTRASENA = "clave-de-prueba-inventada"
SECRETO = "secreto-de-prueba-inventado-de-mas-de-32-caracteres"
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
INDICE = "<!doctype html><title>Finanzas</title><div id=raiz></div>"


@pytest.fixture(scope="module")
def hash_prueba():
    return generar_hash(CONTRASENA)


@pytest.fixture
def config(tmp_path, hash_prueba):
    configuracion = Config(
        db_path=str(tmp_path / "web.db"),
        app_password_hash=hash_prueba,
        session_secret=SECRETO,
        cookie_secure=False,
        max_intentos=5,
        bloqueo_minutos=15,
    )
    db.preparar(configuracion.db_path)  # la app exige la base migrada (ítem 22)
    return configuracion


@pytest.fixture
def dist(tmp_path):
    carpeta = tmp_path / "dist"
    (carpeta / "assets").mkdir(parents=True)
    (carpeta / "index.html").write_text(INDICE, encoding="utf-8")
    (carpeta / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    return carpeta


@pytest.fixture
def cliente(config, dist):
    with TestClient(crear_app(config, directorio_frontend=dist), follow_redirects=False) as c:
        yield c


@pytest.fixture
def con_sesion(cliente):
    r = cliente.post("/api/sesion", json={"contrasena": CONTRASENA})
    assert r.status_code == 200
    cliente.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return cliente


def test_con_la_base_migrada_arranca_y_estan_las_14_categorias(config):
    # Ítem 22: la base la crean las migraciones (el fixture la prepara), no la app.
    import sqlite3

    crear_app(config)
    conn = sqlite3.connect(config.db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM categorias").fetchone()[0] == 14
    finally:
        conn.close()


def test_sin_migrar_la_app_no_arranca_ni_crea_la_base(config, tmp_path):
    # Ítem 22: la app nunca crea ni cambia tablas; exige la base migrada.
    from dataclasses import replace

    nueva = replace(config, db_path=str(tmp_path / "sin-migrar.db"))
    with pytest.raises(db.BaseNoMigrada, match="python -m finanzas.migrar"):
        crear_app(nueva)
    assert not (tmp_path / "sin-migrar.db").exists()


def test_no_quedan_plantillas_ni_estaticos_de_la_v1():
    from pathlib import Path

    from finanzas.web import app as modulo

    carpeta = Path(modulo.__file__).resolve().parent
    assert not (carpeta / "templates").exists()
    assert not (carpeta / "static").exists()


# --- Rutas de la v1: redirigen a la app (ítem 20) ----------------------------------------------

REDIRECCIONES = [
    ("/", "/app/"),
    ("/login", "/app/"),
    ("/saldo", "/app/saldo"),
    ("/sin-categorizar", "/app/movimientos"),
    ("/reglas", "/app/categorias"),
]


@pytest.mark.parametrize("sesion", [False, True], ids=["sin-sesion", "con-sesion"])
@pytest.mark.parametrize("metodo", ["GET", "HEAD"])
@pytest.mark.parametrize("ruta, destino", REDIRECCIONES)
def test_rutas_de_la_v1_redirigen_a_la_app(cliente, sesion, metodo, ruta, destino):
    if sesion:
        assert cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).status_code == 200
    r = cliente.request(metodo, ruta)
    # 307 (temporal, nunca 301 ni 308): el navegador no lo guarda para siempre.
    assert r.status_code == 307
    assert r.headers["location"] == destino
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["content-security-policy"] == CSP
    assert "set-cookie" not in r.headers or sesion


def test_el_destino_existe_en_la_app(cliente):
    for _, destino in REDIRECCIONES:
        r = cliente.get(destino)
        assert r.status_code == 200 and r.text == INDICE, destino


@pytest.mark.parametrize("mes", ["2026-09", "2000-01", "2099-12", "2028-02"])
def test_inicio_conserva_un_mes_valido(cliente, mes):
    r = cliente.get(f"/?mes={mes}")
    assert r.status_code == 307
    assert r.headers["location"] == f"/app/?mes={mes}"


@pytest.mark.parametrize(
    "consulta",
    [
        "mes=2026-9",
        "mes=2026-13",
        "mes=1999-12",
        "mes=2100-01",
        "mes=2026-09-01",
        "mes=%00",
        "mes=2026-09%00",
        "mes=",
        "mes",
        "mes=%202026-09",
        "mes=2026-09%20",
        "mes=+2026-09",
        "mes=2026%2D09%0A",
        "mes=%D9%A2%D9%A0%D9%A2%D9%A6-%D9%A0%D9%A9",  # cifras arábigo-índicas
        "mes=%EF%BC%92%EF%BC%90%EF%BC%92%EF%BC%96-%EF%BC%90%EF%BC%99",  # ancho completo
        "mes=" + "9" * 5000,
        "mes=%3Cscript%3E",
        "mes=%FF",  # UTF-8 inválido
        "mes=2026-09%26next%3D%2F%2Fevil.example",
        "mes=%2F%2Fevil.example",
        "mes=https://evil.example",
        "mes=2026-09%0D%0ALocation:%20https://evil.example",
    ],
)
def test_inicio_con_mes_invalido_va_al_mes_actual(cliente, consulta):
    r = cliente.get("/?" + consulta)
    assert r.status_code == 307, consulta
    assert r.headers["location"] == "/app/"
    assert r.headers.get_list("location") == ["/app/"]


def test_inicio_con_mes_repetido_usa_el_primero_y_lo_valida(cliente):
    assert cliente.get("/?mes=2026-08&mes=2026-07").headers["location"] == "/app/?mes=2026-08"
    assert cliente.get("/?mes=2026-08&mes=malo").headers["location"] == "/app/?mes=2026-08"
    assert cliente.get("/?mes=malo&mes=2026-08").headers["location"] == "/app/"


@pytest.mark.parametrize(
    "url",
    [
        "/?next=https://evil.example",
        "/?url=//evil.example&mes=2026-09",
        "/login?next=https://evil.example",
        "/login?volver=//evil.example",
        "/saldo?volver=/%5Cevil.example",
        # Regresión: una versión con ``destino`` como argumento por defecto lo
        # leía de la URL y redirigía a donde dijera.
        "/reglas?destino=https://evil.example",
        "/login?destino=https://evil.example",
        "/saldo?destino=//evil.example",
        "/sin-categorizar?destino=https://evil.example",
        "/?destino=https://evil.example&mes=2026-09",
        "/?request=https://evil.example",
        "/sin-categorizar?x=1",
    ],
)
def test_sin_redireccion_abierta(cliente, url):
    r = cliente.get(url)
    assert r.status_code == 307
    destino = r.headers["location"]
    assert destino in {d for _, d in REDIRECCIONES} | {"/app/?mes=2026-09"}
    assert "evil" not in destino


def test_el_host_recibido_no_cambia_el_destino(cliente):
    for ruta, destino in REDIRECCIONES:
        r = cliente.get(ruta, headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"})
        assert r.headers["location"] == destino  # relativa: nunca arma la URL con el Host


@pytest.mark.parametrize("ruta", ["//evil.example", "//evil.example/", "/\\evil.example", "///evil.example"])
def test_rutas_que_parecen_otro_host_dan_404(cliente, ruta):
    r = cliente.get("http://testserver" + ruta)
    assert r.status_code == 404
    assert "location" not in r.headers


# --- Los formularios de la v1 ya no existen: 404 o 405 -----------------------------------------

POST_VIEJOS = [
    ("/login", 405),
    ("/", 405),
    ("/saldo", 405),
    ("/reglas", 405),
    ("/sin-categorizar", 405),
    ("/logout", 404),
    ("/sincronizar", 404),
    ("/ingresos", 404),
    ("/ajustes", 404),
    ("/saldo/configurar", 404),
    ("/movimientos/1/categoria", 404),
    ("/reglas/1/borrar", 404),
]


@pytest.mark.parametrize("sesion", [False, True], ids=["sin-sesion", "con-sesion"])
@pytest.mark.parametrize("ruta, estado", POST_VIEJOS)
def test_los_post_de_la_v1_dan_404_o_405(cliente, config, sesion, ruta, estado):
    if sesion:
        assert cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).status_code == 200
    antes = _huella(config)
    datos = {"contrasena": CONTRASENA, "categoria_id": "1", "saldo_real": "1", "monto": "1",
             "saldo_inicial": "1", "fecha_inicio": "2026-08-01", "volver": "/saldo"}
    r = cliente.post(ruta, data=datos)
    assert r.status_code == estado
    assert "location" not in r.headers
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["cache-control"] == "no-store"
    assert _huella(config) == antes
    if not sesion:
        assert cliente.get("/api/sesion").status_code == 401  # POST /login no da sesión


def _huella(config):
    import sqlite3

    c = sqlite3.connect(config.db_path)
    try:
        return tuple(
            c.execute(f"SELECT * FROM {tabla}").fetchall()
            for tabla in ("movimientos", "reglas", "configuracion_saldo", "categorias")
        )
    finally:
        c.close()


# --- Lo que no es /api ni /app y no tiene ruta: 404, sin filtrar nada --------------------------

NO_EXISTEN = [
    "/ruta-inventada",
    "/reporte?mes=2026-09",
    "/LOGIN",
    "/Login",
    "/login/",
    "/login/extra",
    "/login;/",
    "/login%2F..",
    "/saldo/",
    "/reglas/1/borrar",
    "/movimientos",
    "/static",
    "/static/",
    "/static/estilos.css",
    "/static/reporte.js",
    "/static/..%2Fapp.py",
    "/static/%2e%2e/app.py",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/apple",
    "/app-otra",
    "/.env",
    "/finanzas.db",
]


@pytest.mark.parametrize("ruta", NO_EXISTEN)
def test_rutas_inexistentes_dan_404_igual_con_o_sin_sesion(cliente, ruta):
    sin = cliente.get(ruta)
    cliente.post("/api/sesion", json={"contrasena": CONTRASENA})
    con = cliente.get(ruta)
    for r in (sin, con):
        assert r.status_code == 404, ruta
        assert "location" not in r.headers
        assert r.headers["content-security-policy"] == CSP
        assert r.headers["cache-control"] == "no-store"
        assert "import" not in r.text and "crear_app" not in r.text and "Traceback" not in r.text
        assert len(r.content) < 100
    assert sin.content == con.content  # la sesión no cambia lo que se ve


@pytest.mark.parametrize("metodo", ["HEAD", "OPTIONS", "PUT", "DELETE", "PATCH"])
def test_otros_metodos_a_la_raiz_no_redirigen(cliente, metodo):
    r = cliente.request(metodo, "/")
    if metodo == "HEAD":
        assert r.status_code == 307
    else:
        assert r.status_code == 405
        assert "location" not in r.headers


def test_la_api_sin_sesion_sigue_dando_401_json(cliente):
    for ruta in ("/api/sesion", "/api/reporte", "/api/saldo", "/api/no-existe", "/api"):
        r = cliente.get(ruta)
        assert r.status_code == 401, ruta
        assert r.json() == {"detalle": "Inicia sesión para continuar."}
        assert "location" not in r.headers


# --- Encabezados de seguridad y CSP --------------------------------------------------------------

def test_la_csp_es_la_esperada():
    # Igual o más estricta que la de la v1; nunca más laxa.
    assert ENCABEZADOS_SEGURIDAD["Content-Security-Policy"] == CSP


def test_la_csp_bloquea_lo_que_va_en_linea():
    directivas = dict(d.strip().split(" ", 1) for d in CSP.split(";"))
    assert directivas["default-src"] == "'self'"
    assert directivas["script-src"] == "'self'"
    assert directivas["style-src"] == "'self'"
    assert directivas["object-src"] == "'none'"
    assert directivas["base-uri"] == "'none'"
    assert directivas["frame-ancestors"] == "'none'"
    assert "unsafe-inline" not in CSP and "unsafe-eval" not in CSP and "nonce-" not in CSP
    assert "http:" not in CSP and "https:" not in CSP and "*" not in CSP


@pytest.mark.parametrize(
    "ruta",
    ["/app/", "/app/saldo", "/app/assets/index-abc123.js", "/", "/?mes=2026-09", "/login", "/saldo",
     "/reglas", "/sin-categorizar", "/no-existe", "/api/sesion", "/api/reporte"],
)
def test_csp_exacta_y_unica_con_y_sin_sesion(cliente, ruta):
    r = cliente.get(ruta)
    assert r.headers.get_list("content-security-policy") == [CSP], ruta
    cliente.post("/api/sesion", json={"contrasena": CONTRASENA})
    r = cliente.get(ruta)
    assert r.headers.get_list("content-security-policy") == [CSP], ruta
    for nombre, valor in ENCABEZADOS_SEGURIDAD.items():
        assert r.headers[nombre] == valor


def test_csp_en_las_respuestas_de_error_de_los_middlewares(con_sesion):
    casos = [
        # _verificar_origen: Origin ajeno, en la API y fuera de ella.
        (con_sesion.post("/api/ajustes", json={"saldo_real_centavos": 1},
                         headers={"Origin": "https://otro.example"}), 403),
        (con_sesion.post("/logout", headers={"Origin": "https://otro.example"}), 403),
        # _verificar_origen: Sec-Fetch-Site de otro sitio.
        (con_sesion.post("/api/ajustes", json={"saldo_real_centavos": 1},
                         headers={"Sec-Fetch-Site": "cross-site"}), 403),
        # _proteger_api: sin token CSRF y cuerpo que no es JSON.
        (con_sesion.post("/api/ajustes", json={"saldo_real_centavos": 1}, headers={"X-CSRF-Token": ""}), 403),
        (con_sesion.post("/api/ajustes", content=b"{}", headers={"Content-Type": "text/plain"}), 415),
    ]
    con_sesion.cookies.clear()
    # _exigir_sesion: sin sesión.
    casos.append((con_sesion.get("/api/reporte"), 401))
    for r, estado in casos:
        assert r.status_code == estado, r.text
        assert r.headers.get_list("content-security-policy") == [CSP]
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["cache-control"] == "no-store"


def test_solo_los_archivos_con_hash_se_guardan_en_cache(cliente):
    assert cliente.get("/app/assets/index-abc123.js").headers["cache-control"] != "no-store"
    for ruta in ("/app/", "/", "/login", "/no-existe", "/static/estilos.css", "/api/sesion"):
        assert cliente.get(ruta).headers["cache-control"] == "no-store", ruta


# --- Origin (portado de test_web_categorias.py) -------------------------------------------------

@pytest.mark.parametrize(
    "origen, host, esperado",
    [
        (None, "finanzas.example", True),
        ("https://finanzas.example", "finanzas.example", True),
        ("https://FINANZAS.example", "finanzas.example", True),
        ("https://finanzas.example:443", "finanzas.example", True),
        ("https://finanzas.example", "finanzas.example:443", True),
        ("http://127.0.0.1:8000", "127.0.0.1:8000", True),
        ("https://otro.example", "finanzas.example", False),
        ("https://finanzas.example.otro.example", "finanzas.example", False),
        ("https://finanzas.example:8443", "finanzas.example", False),
        ("null", "finanzas.example", False),
        ("", "finanzas.example", False),
        ("ftp://finanzas.example", "finanzas.example", False),
        ("https://finanzas.example", None, False),
    ],
)
def test_origen_permitido(origen, host, esperado):
    assert origen_permitido(origen, host) is esperado


# --- Configuración ---------------------------------------------------------

def _entorno(hash_prueba, **cambios):
    env = {"APP_PASSWORD_HASH": hash_prueba, "SESSION_SECRET": SECRETO}
    env.update(cambios)
    return {k: v for k, v in env.items() if v is not None}


def test_config_valores_por_defecto(hash_prueba):
    c = Config.desde_entorno(_entorno(hash_prueba))
    assert c.db_path == "finanzas.db"
    assert c.cookie_secure is True
    assert (c.max_intentos, c.bloqueo_minutos) == (5, 15)
    assert SECRETO not in repr(c)


def test_config_falla_sin_session_secret(hash_prueba):
    with pytest.raises(ErrorConfiguracion, match="SESSION_SECRET"):
        Config.desde_entorno(_entorno(hash_prueba, SESSION_SECRET=None))


@pytest.mark.parametrize("transformar", [str, str.upper, lambda s: "  " + s + "\n"])
def test_config_rechaza_secreto_publico_del_ejemplo(hash_prueba, transformar):
    secreto = transformar("reemplazar-con-una-clave-aleatoria-de-al-menos-32-caracteres")
    with pytest.raises(ErrorConfiguracion, match="SESSION_SECRET") as error:
        Config.desde_entorno(_entorno(hash_prueba, SESSION_SECRET=secreto))
    assert secreto.strip().casefold() not in str(error.value).casefold()


def test_config_falla_sin_hash(hash_prueba):
    with pytest.raises(ErrorConfiguracion, match="APP_PASSWORD_HASH"):
        Config.desde_entorno(_entorno(hash_prueba, APP_PASSWORD_HASH=""))


def test_config_secreto_corto_no_muestra_el_valor(hash_prueba):
    with pytest.raises(ErrorConfiguracion) as error:
        Config.desde_entorno(_entorno(hash_prueba, SESSION_SECRET="corto-123"))
    assert "corto-123" not in str(error.value)


@pytest.mark.parametrize(
    "cambios",
    [{"COOKIE_SECURE": "quizas"}, {"MAX_INTENTOS": "cinco"}, {"BLOQUEO_MINUTOS": "0"}],
)
def test_config_valores_invalidos(hash_prueba, cambios):
    with pytest.raises(ErrorConfiguracion):
        Config.desde_entorno(_entorno(hash_prueba, **cambios))


def test_config_acepta_hash_valido(hash_prueba):
    assert Config.desde_entorno(_entorno(hash_prueba)).app_password_hash == hash_prueba


def _truncado(h):
    return h[: len(h) // 2]


@pytest.mark.parametrize(
    "transformar",
    [
        lambda h: h.replace(":", "$"),  # formato anterior con "$"
        lambda h: "scrypt",  # lo que deja la shell al expandir los "$"
        _truncado,
        lambda h: h.rsplit(":", 1)[0],  # falta el hash
        lambda h: h.replace("scrypt:", "bcrypt:"),
        lambda h: h[:-1] + "z",  # hash no hexadecimal
        lambda h: h.replace(":16384:", ":0:"),
        lambda h: "reemplazar-con-salida-de-python-m-finanzas.seguridad",
    ],
)
def test_config_rechaza_hash_mal_formado_sin_mostrarlo(hash_prueba, transformar):
    malo = transformar(hash_prueba)
    with pytest.raises(ErrorConfiguracion, match="APP_PASSWORD_HASH") as error:
        Config.desde_entorno(_entorno(hash_prueba, APP_PASSWORD_HASH=malo))
    if len(malo) > 10:  # "scrypt" a secas aparece como palabra en el propio mensaje
        assert malo not in str(error.value)
    assert hash_prueba[-20:] not in str(error.value)


def test_crear_app_con_hash_mal_formado_falla_al_arrancar(monkeypatch, hash_prueba):
    monkeypatch.setenv("APP_PASSWORD_HASH", hash_prueba.replace(":", "$"))
    monkeypatch.setenv("SESSION_SECRET", SECRETO)
    with pytest.raises(ErrorConfiguracion, match="APP_PASSWORD_HASH"):
        crear_app()


def test_crear_app_sin_entorno_falla_con_mensaje_claro(monkeypatch, hash_prueba):
    monkeypatch.setenv("APP_PASSWORD_HASH", hash_prueba)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(ErrorConfiguracion, match="SESSION_SECRET"):
        crear_app()


# --- Configuración de Gmail (recuperadas de test_web_sincronizacion.py, ítem 20) ----------------

from finanzas.gmail import REMITENTE_AYN, REMITENTE_POR_DEFECTO  # noqa: E402


def test_config_gmail_opcional(hash_prueba):
    from finanzas.gmail import REMITENTES_OFICIALES

    c = Config.desde_entorno(_entorno(hash_prueba))
    assert c.gmail_token is None
    assert c.gmail_remitentes == REMITENTES_OFICIALES


@pytest.mark.parametrize(
    "antiguo",
    ["", "  ", REMITENTE_POR_DEFECTO, REMITENTE_AYN.upper()],
)
def test_config_gmail_desde_entorno_siempre_con_los_dos_remitentes(hash_prueba, antiguo):
    # D30: GMAIL_REMITENTE ya no elige nada; vacío o con una oficial, se usan las dos.
    from finanzas.gmail import REMITENTES_OFICIALES

    c = Config.desde_entorno(_entorno(
        hash_prueba, GMAIL_TOKEN=" /srv/finanzas/token.json ", GMAIL_REMITENTE=antiguo,
    ))
    assert c.gmail_token == "/srv/finanzas/token.json"
    assert c.gmail_remitentes == REMITENTES_OFICIALES


@pytest.mark.parametrize(
    "remitente",
    ["alertas@example.com", "a@b.com OR c@d.com", "sin-arroba", "a@b.com)", 'a"@b.com', "a@b",
     REMITENTE_AYN.replace("@ayn.", "@otro.")],
)
def test_config_rechaza_remitente_invalido(hash_prueba, remitente):
    with pytest.raises(ErrorConfiguracion, match="GMAIL_REMITENTE"):
        Config.desde_entorno(_entorno(hash_prueba, GMAIL_REMITENTE=remitente))
