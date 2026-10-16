"""API: sincronizar ahora, última sincronización y no reconocidos (ítem 10). Gmail falso."""

from __future__ import annotations

import threading

import pytest

from finanzas.gmail import ErrorAutorizacionGmail

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import Fabrica, configurar_saldo, ejecutar_sql


def _contar_movimientos(config):
    return ejecutar_sql(config, "SELECT COUNT(*) FROM movimientos").fetchone()[0]


def test_nunca_sincronizado(api):
    assert api.get("/api/sincronizacion").json() == {
        "en_curso": False, "ultima": None, "ultima_correcta_en": None,
        "debe_sincronizar_al_abrir": False,  # sin GMAIL_TOKEN (ítem 38)
    }


def test_sincronizar_ahora(api, config, fabrica):
    configurar_saldo(config)
    r = api.post("/api/sincronizacion")
    assert r.status_code == 200
    datos = r.json()
    assert datos["estado"] == "ok"
    assert datos["origen"] == "web"
    assert datos["codigo_error"] is None
    assert datos["contadores"] == {
        "nuevos": 3, "duplicados": 0, "no_reconocidos": 1, "errores": 0, "rechazados_autenticacion": 0,
    }
    assert datos["mensaje"].startswith("Sincronización terminada: 3 nuevos")
    assert len(datos["terminada_en"]) == 19
    assert fabrica.llamadas == 1
    assert _contar_movimientos(config) == 3
    # La última sincronización queda guardada y se lee igual.
    assert api.get("/api/sincronizacion").json() == {
        "en_curso": False, "ultima": datos, "ultima_correcta_en": datos["terminada_en"],
        "debe_sincronizar_al_abrir": False,
    }


def test_segunda_sincronizacion_no_duplica(api, config):
    configurar_saldo(config)
    api.post("/api/sincronizacion")
    datos = api.post("/api/sincronizacion").json()
    assert datos["contadores"]["nuevos"] == 0
    assert _contar_movimientos(config) == 3


def test_sin_saldo_configurado_queda_como_fallida(api, fabrica):
    datos = api.post("/api/sincronizacion").json()
    assert datos["estado"] == "fallida"
    assert datos["codigo_error"] == "sin_fecha_inicio"
    assert datos["contadores"] is None
    assert fabrica.llamadas == 0  # no se tocó Gmail
    assert api.get("/api/sincronizacion").json()["ultima"]["codigo_error"] == "sin_fecha_inicio"


@pytest.mark.parametrize(
    "error, codigo",
    [
        (ErrorAutorizacionGmail("token revocado (texto inventado)"), "autorizacion_gmail"),
        (RuntimeError("fallo con datos inventados $1.000"), "error_inesperado"),
    ],
)
def test_errores_de_gmail_quedan_con_codigo_y_sin_datos(cliente, config, app, error, codigo):
    from tests.soporte.ayudas_api import CONTRASENA, ClienteApi

    configurar_saldo(config)
    app.state.fabrica_cliente_gmail = Fabrica(error=error)
    csrf = cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"]
    api = ClienteApi(cliente, csrf)
    r = api.post("/api/sincronizacion")
    assert r.status_code == 200
    datos = r.json()
    assert (datos["estado"], datos["codigo_error"], datos["contadores"]) == ("fallida", codigo, None)
    assert "inventad" not in r.text and "$1.000" not in r.text
    guardado = ejecutar_sql(config, "SELECT * FROM estado_sincronizacion").fetchall()
    assert "inventad" not in repr(guardado)


def test_en_curso_409(api, config, app):
    configurar_saldo(config)
    candado: threading.Lock = app.state.candado_sincronizacion
    candado.acquire()
    try:
        assert api.get("/api/sincronizacion").json()["en_curso"] is True
        r = api.post("/api/sincronizacion")
        assert r.status_code == 409
        assert r.json() == {"detalle": "Ya hay una sincronización en curso."}
    finally:
        candado.release()
    assert api.get("/api/sincronizacion").json()["en_curso"] is False


def test_el_candado_se_libera_aunque_falle(api, config, app):
    configurar_saldo(config)
    app.state.fabrica_cliente_gmail = Fabrica(error=RuntimeError("inventado"))
    api.post("/api/sincronizacion")
    assert app.state.candado_sincronizacion.acquire(blocking=False)
    app.state.candado_sincronizacion.release()


def test_ve_la_sincronizacion_del_temporizador(api, config, monkeypatch, capsys):
    # El comando del temporizador (python -m finanzas.sincronizacion) también guarda el estado.
    from finanzas import sincronizacion
    from tests.soporte.ayudas_api import SECRETO
    from tests.soporte.gmail_falso import ClienteFalso

    configurar_saldo(config)
    monkeypatch.setenv("DB_PATH", config.db_path)
    monkeypatch.setenv("APP_PASSWORD_HASH", config.app_password_hash)
    monkeypatch.setenv("SESSION_SECRET", SECRETO)
    assert sincronizacion.main([], fabrica_cliente=lambda _config: ClienteFalso()) == 0
    ultima = api.get("/api/sincronizacion").json()["ultima"]
    assert ultima["origen"] == "comando"
    assert ultima["estado"] == "ok"
    assert ultima["contadores"]["nuevos"] == 3


def test_ultima_correcta_se_conserva_si_la_siguiente_falla(api, config, app, monkeypatch):
    from datetime import datetime

    from finanzas.compartido import hora

    configurar_saldo(config)
    monkeypatch.setattr(hora, "ahora_colombia", lambda: datetime(2026, 9, 10, 8, 0, 0))
    correcta = api.post("/api/sincronizacion").json()
    assert correcta["estado"] == "ok"

    monkeypatch.setattr(hora, "ahora_colombia", lambda: datetime(2026, 9, 10, 14, 0, 0))
    app.state.fabrica_cliente_gmail = Fabrica(error=ErrorAutorizacionGmail("revocado (inventado)"))
    fallida = api.post("/api/sincronizacion").json()
    assert fallida["estado"] == "fallida"

    datos = api.get("/api/sincronizacion").json()
    assert datos["ultima"]["terminada_en"] == "2026-09-10T14:00:00"
    assert datos["ultima"]["codigo_error"] == "autorizacion_gmail"
    assert datos["ultima_correcta_en"] == "2026-09-10T08:00:00"
    assert isinstance(datos["ultima_correcta_en"], str)


def test_primera_sincronizacion_fallida_sin_ultima_correcta(api):
    datos = api.post("/api/sincronizacion").json()  # sin saldo configurado: fallida
    assert datos["estado"] == "fallida"
    estado = api.get("/api/sincronizacion").json()
    assert estado["ultima"]["estado"] == "fallida"
    assert "ultima_correcta_en" in estado and estado["ultima_correcta_en"] is None


def test_estado_sin_sesion_401(cliente):
    r = cliente.get("/api/sincronizacion")
    assert r.status_code == 401
    assert "ultima_correcta_en" not in r.text


def test_no_reconocidos(api, config):
    ejecutar_sql(
        config,
        "INSERT INTO correos_no_reconocidos VALUES (?, ?, ?)",
        ("id-inventado-1", "2026-08-08T07:00:00", "Asunto inventado uno"),
    )
    ejecutar_sql(
        config,
        "INSERT INTO correos_no_reconocidos VALUES (?, ?, ?)",
        ("id-inventado-2", "2026-08-09T07:00:00", "Asunto inventado dos"),
    )
    ejecutar_sql(config, "INSERT INTO correos_no_reconocidos VALUES (?, NULL, NULL)", ("id-inventado-3",))
    r = api.get("/api/no-reconocidos")
    assert r.status_code == 200
    assert r.json() == {
        "correos": [
            {"gmail_id": "id-inventado-2", "fecha": "2026-08-09T07:00:00", "asunto": "Asunto inventado dos"},
            {"gmail_id": "id-inventado-1", "fecha": "2026-08-08T07:00:00", "asunto": "Asunto inventado uno"},
            {"gmail_id": "id-inventado-3", "fecha": None, "asunto": None},
        ]
    }


def test_no_reconocidos_tras_sincronizar(api, config):
    configurar_saldo(config)
    api.post("/api/sincronizacion")
    correos = api.get("/api/no-reconocidos").json()["correos"]
    assert [c["gmail_id"] for c in correos] == ["msg-0003"]
    assert set(correos[0]) == {"gmail_id", "fecha", "asunto"}  # nunca el cuerpo


# --- Recuperadas de test_web_sincronizacion.py (ítem 20) ----------------------------------------

def test_ruta_sincronizar_es_sincrona():
    """``def`` y no ``async def``: FastAPI la ejecuta en el threadpool, así la
    descarga de correos (y la espera del candado) no bloquea las demás peticiones."""
    import inspect

    from finanzas.api import rutas

    assert not inspect.iscoroutinefunction(rutas.sincronizar_ahora)
    assert "async def sincronizar_ahora(" not in inspect.getsource(rutas)


def test_sin_gmail_token_queda_como_gmail_no_configurado(config, hash_prueba):
    # Sin fábrica inyectada se usa la real, que lee GMAIL_TOKEN de la configuración.
    from fastapi.testclient import TestClient

    from finanzas.web.app import crear_app
    from tests.soporte.ayudas_api import CONTRASENA, ClienteApi

    assert config.gmail_token is None
    configurar_saldo(config)
    with TestClient(crear_app(config), follow_redirects=False) as c:
        api = ClienteApi(c, c.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"])
        r = api.post("/api/sincronizacion")
    assert r.status_code == 200
    assert (r.json()["estado"], r.json()["codigo_error"]) == ("fallida", "gmail_no_configurado")


def test_error_inesperado_no_deja_detalles_en_el_registro(api, config, app, caplog):
    from tests.soporte.gmail_falso import ClienteFalso

    class Roto(ClienteFalso):
        def listar_ids(self, desde):
            raise RuntimeError("detalle interno MERPAGO 245.700")

    configurar_saldo(config)
    app.state.fabrica_cliente_gmail = Fabrica(cliente=Roto())
    with caplog.at_level("DEBUG"):
        r = api.post("/api/sincronizacion")
    assert r.json()["codigo_error"] == "error_inesperado"
    assert "No se pudo completar la sincronización" in r.json()["mensaje"]
    assert "MERPAGO" not in r.text and "245.700" not in r.text
    assert "MERPAGO" not in caplog.text and "245.700" not in caplog.text
