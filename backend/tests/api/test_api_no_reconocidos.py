"""API: reprocesar los correos no reconocidos (ítem 19). Gmail falso y correos inventados.

La lógica del reproceso se prueba a fondo en ``tests/modulos/sincronizacion/test_reproceso.py``; aquí,
el contrato de la API, la seguridad (sesión, CSRF, Origin) y el candado
compartido con "Sincronizar".
"""

from __future__ import annotations

import threading

import pytest

from finanzas import sincronizacion
from finanzas.modulos.sincronizacion.adaptadores.avisos import lector
from finanzas.gmail import ErrorAutorizacionGmail
from finanzas.sincronizacion import SincronizacionNoConfigurada

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import CONTRASENA, ClienteApi, Fabrica, configurar_saldo, ejecutar_sql
from tests.soporte.gmail_falso import ClienteFalso, correo_fixture
from tests.soporte.reproceso import ENCABEZADO_NUEVO, _correo

RUTA = "/api/no-reconocidos/reprocesar"


def _cliente_gmail() -> ClienteFalso:
    return ClienteFalso(
        {
            "msg-r001": _correo("encabezado_nuevo_inventado.json"),
            "msg-r002": _correo("dmarc_fallido_aviso_valido.json"),
            "msg-0003": correo_fixture("msg-0003"),
        }
    )


@pytest.fixture
def gmail(app):
    """Gmail falso con los tres correos del reproceso, ya sincronizados (los tres quedan en la lista)."""
    cliente = _cliente_gmail()
    app.state.fabrica_cliente_gmail = Fabrica(cliente)
    return cliente


@pytest.fixture
def sincronizado(api, config, gmail):
    configurar_saldo(config)
    assert api.post("/api/sincronizacion").json()["contadores"]["no_reconocidos"] == 2
    return gmail


@pytest.fixture
def corregir_lector(monkeypatch):
    claves = lector._CLAVES_ENCABEZADOS | {lector._clave_encabezado(ENCABEZADO_NUEVO)}
    return lambda: monkeypatch.setattr(lector, "_CLAVES_ENCABEZADOS", claves)


def _ids(api) -> list[str]:
    return sorted(c["gmail_id"] for c in api.get("/api/no-reconocidos").json()["correos"])


def _movimientos(config) -> list[tuple]:
    return [tuple(f) for f in ejecutar_sql(config, "SELECT gmail_id, monto_centavos FROM movimientos").fetchall()]


def test_reprocesar_todos(api, config, sincronizado, corregir_lector):
    corregir_lector()
    r = api.post(RUTA)
    assert r.status_code == 200
    assert r.json() == {
        "estado": "ok",
        "contadores": {
            "revisados": 3,
            "movimientos_creados": 1,
            "siguen_sin_reconocerse": 2,
            "ya_registrados": 0,
            "errores": 0,
        },
        "codigo_error": None,
        "mensaje": (
            "Reproceso terminado: 3 revisados, 1 movimientos creados, 2 siguen sin reconocerse, "
            "0 ya registrados, 0 errores."
        ),
    }
    assert _ids(api) == ["msg-0003", "msg-r002"]  # el de DMARC fallido sigue en la lista
    assert _movimientos(config) == [("msg-r001", 1234500)]


def test_reprocesar_dos_veces_no_duplica(api, config, sincronizado, corregir_lector):
    corregir_lector()
    api.post(RUTA)
    datos = api.post(RUTA).json()
    assert datos["contadores"]["revisados"] == 2
    assert datos["contadores"]["movimientos_creados"] == 0
    assert _movimientos(config) == [("msg-r001", 1234500)]


def test_sin_corregir_el_lector_nada_cambia(api, config, sincronizado):
    datos = api.post(RUTA).json()
    assert datos["contadores"]["siguen_sin_reconocerse"] == 3
    assert _ids(api) == ["msg-0003", "msg-r001", "msg-r002"]
    assert _movimientos(config) == []


def test_errores_de_descarga_dan_con_errores(api, sincronizado):
    del sincronizado.correos["msg-0003"]
    sincronizado.fallan["msg-0003"] = RuntimeError("inventado")
    datos = api.post(RUTA).json()
    assert datos["estado"] == "con_errores"
    assert datos["contadores"]["errores"] == 1
    assert "msg-0003" in _ids(api)


def test_reprocesar_uno(api, config, sincronizado, corregir_lector):
    corregir_lector()
    sincronizado.llamadas_obtener.clear()
    r = api.post("/api/no-reconocidos/msg-r001/reprocesar")
    assert r.status_code == 200
    assert r.json()["contadores"] == {
        "revisados": 1, "movimientos_creados": 1, "siguen_sin_reconocerse": 0, "ya_registrados": 0, "errores": 0,
    }
    assert sincronizado.llamadas_obtener == ["msg-r001"]
    assert _ids(api) == ["msg-0003", "msg-r002"]


def test_reprocesar_uno_dmarc_fallido_sigue(api, config, sincronizado, corregir_lector):
    corregir_lector()
    datos = api.post("/api/no-reconocidos/msg-r002/reprocesar").json()
    assert datos["contadores"]["siguen_sin_reconocerse"] == 1
    assert "msg-r002" in _ids(api)
    assert _movimientos(config) == []


def test_reprocesar_uno_que_no_esta_en_la_lista_404(api, config, sincronizado):
    sincronizado.llamadas_obtener.clear()
    r = api.post("/api/no-reconocidos/id-inventado-inexistente/reprocesar")
    assert r.status_code == 404
    assert r.json() == {"detalle": "Ese correo no está en la lista de no reconocidos."}
    assert sincronizado.llamadas_obtener == []
    largo = api.post("/api/no-reconocidos/" + "a" * 201 + "/reprocesar")
    assert largo.status_code == 422


def test_lista_vacia_no_toca_gmail(api, config, app):
    configurar_saldo(config)
    fabrica = Fabrica(error=SincronizacionNoConfigurada("sin token (inventado)"))
    app.state.fabrica_cliente_gmail = fabrica
    datos = api.post(RUTA).json()
    assert datos["estado"] == "ok"
    assert datos["contadores"]["revisados"] == 0
    assert fabrica.llamadas == 0


@pytest.mark.parametrize(
    "error, codigo",
    [
        (SincronizacionNoConfigurada("sin token (inventado)"), "gmail_no_configurado"),
        (ErrorAutorizacionGmail("token revocado (texto inventado)"), "autorizacion_gmail"),
        (RuntimeError("fallo con datos inventados $1.000"), "error_inesperado"),
    ],
)
def test_mismos_errores_que_sincronizar(api, app, sincronizado, error, codigo):
    from finanzas.api.rutas import MENSAJES_ERROR_SINCRONIZACION

    app.state.fabrica_cliente_gmail = Fabrica(error=error)
    r = api.post(RUTA)
    assert r.status_code == 200
    assert r.json() == {
        "estado": "fallida",
        "contadores": None,
        "codigo_error": codigo,
        "mensaje": MENSAJES_ERROR_SINCRONIZACION[codigo],
    }
    assert "inventad" not in r.text and "$1.000" not in r.text
    assert len(_ids(api)) == 3
    # No pisa el estado de la última sincronización.
    assert api.get("/api/sincronizacion").json()["ultima"]["estado"] == "ok"


def test_sin_fecha_de_inicio(api, app):
    fabrica = Fabrica()
    app.state.fabrica_cliente_gmail = fabrica
    datos = api.post(RUTA).json()
    assert (datos["estado"], datos["codigo_error"]) == ("fallida", "sin_fecha_inicio")
    assert fabrica.llamadas == 0


@pytest.mark.parametrize("ruta", [RUTA, "/api/no-reconocidos/msg-r001/reprocesar"])
def test_sincronizacion_en_curso_409(api, app, sincronizado, ruta):
    candado: threading.Lock = app.state.candado_sincronizacion
    candado.acquire()
    try:
        r = api.post(ruta)
        assert r.status_code == 409
        assert r.json() == {"detalle": "Ya hay una sincronización en curso."}
    finally:
        candado.release()
    assert len(_ids(api)) == 3


def test_el_candado_se_libera(api, app, sincronizado):
    app.state.fabrica_cliente_gmail = Fabrica(error=RuntimeError("inventado"))
    api.post(RUTA)
    api.post("/api/no-reconocidos/id-inventado-inexistente/reprocesar")  # 404
    assert app.state.candado_sincronizacion.acquire(blocking=False)
    app.state.candado_sincronizacion.release()


# --- Seguridad (ítem 10) ----------------------------------------------------------------

@pytest.mark.parametrize("ruta", [RUTA, "/api/no-reconocidos/msg-r001/reprocesar"])
def test_sin_sesion_401(cliente, config, gmail, ruta):
    configurar_saldo(config)
    r = cliente.post(ruta, json={})
    assert r.status_code == 401
    assert gmail.llamadas_obtener == []


@pytest.mark.parametrize("ruta", [RUTA, "/api/no-reconocidos/msg-r001/reprocesar"])
@pytest.mark.parametrize("csrf", [None, "token-inventado-que-no-es-el-de-la-sesion"])
def test_sin_csrf_o_con_otro_403(api, sincronizado, corregir_lector, ruta, csrf):
    corregir_lector()
    sincronizado.llamadas_obtener.clear()
    encabezados = {} if csrf is None else {"X-CSRF-Token": csrf}
    r = api.cliente.post(ruta, json={}, headers=encabezados)
    assert r.status_code == 403
    assert sincronizado.llamadas_obtener == []
    assert len(_ids(api)) == 3


@pytest.mark.parametrize("ruta", [RUTA, "/api/no-reconocidos/msg-r001/reprocesar"])
def test_con_otro_origin_403(api, config, sincronizado, corregir_lector, ruta):
    corregir_lector()
    sincronizado.llamadas_obtener.clear()
    r = api.post(ruta, headers={"Origin": "https://sitio-malo.example"})
    assert r.status_code == 403
    assert "access-control-allow-origin" not in r.headers
    assert sincronizado.llamadas_obtener == []
    assert _movimientos(config) == []


def test_csrf_de_otra_sesion_403(app, config, sincronizado, corregir_lector):
    # El token CSRF está ligado a la sesión: el de otra sesión no sirve.
    from fastapi.testclient import TestClient

    corregir_lector()
    with TestClient(app) as otro:
        csrf_ajeno = otro.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"]
    with TestClient(app) as propio:
        propio.post("/api/sesion", json={"contrasena": CONTRASENA})
        r = ClienteApi(propio, csrf_ajeno).post(RUTA)
    assert r.status_code == 403
    assert _movimientos(config) == []


def test_get_no_lleva_el_cuerpo(api, sincronizado):
    correos = api.get("/api/no-reconocidos").json()["correos"]
    assert all(set(c) == {"gmail_id", "fecha", "asunto"} for c in correos)
