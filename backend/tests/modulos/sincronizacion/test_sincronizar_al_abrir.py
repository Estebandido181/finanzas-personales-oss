"""Ítem 38: sincronizar al abrir la app (``debe_sincronizar_al_abrir``). Datos inventados."""

from __future__ import annotations

import dataclasses
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from finanzas import sincronizacion
from finanzas.compartido import hora
from finanzas.sincronizacion import EstadoSincronizacion, ResultadoSincronizacion, debe_sincronizar_al_abrir
from finanzas.web.app import crear_app

from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.ayudas_api import CONTRASENA, ClienteApi, Fabrica, configurar_saldo, ejecutar_sql

AHORA = datetime(2026, 9, 15, 12, 0, 0)


def _estado(terminada_en="2026-09-15T10:00:00", estado="ok", codigo_error=None):
    resultado = None if estado == "fallida" else ResultadoSincronizacion()
    return EstadoSincronizacion(
        terminada_en=terminada_en, estado=estado, origen="web", resultado=resultado, codigo_error=codigo_error
    )


def _decide(estado, **cambios):
    datos = {"gmail_configurado": True, "fecha_configurada": True, "en_curso": False, "ahora": AHORA}
    datos.update(cambios)
    return debe_sincronizar_al_abrir(estado, **datos)


# --- La regla -------------------------------------------------------------------------------

def test_nunca_sincronizado_debe_sincronizar():
    assert _decide(None) is True


@pytest.mark.parametrize(
    "terminada_en, esperado",
    [
        ("2026-09-15T10:59:59", True),  # 1 h y 1 s
        ("2026-09-15T11:00:00", False),  # justo 1 h: no "más de una hora"
        ("2026-09-15T11:30:00", False),
        ("2026-09-14T23:00:00", True),  # el día anterior
        ("2026-09-15T12:30:00", False),  # en el futuro (reloj cambiado): cuenta como reciente
    ],
)
def test_mas_de_una_hora(terminada_en, esperado):
    assert _decide(_estado(terminada_en)) is esperado


@pytest.mark.parametrize("cambio", [{"gmail_configurado": False}, {"fecha_configurada": False}, {"en_curso": True}])
def test_sin_gmail_sin_fecha_o_en_curso_no(cambio):
    assert _decide(None, **cambio) is False
    assert _decide(_estado("2026-09-14T00:00:00"), **cambio) is False


@pytest.mark.parametrize("codigo", sorted(sincronizacion.CODIGOS_QUE_NO_SE_ARREGLAN_SOLOS))
def test_fallo_que_no_se_arregla_solo_no_reintenta(codigo):
    assert codigo in {"gmail_no_configurado", "autorizacion_gmail"}
    assert _decide(_estado("2026-09-01T00:00:00", "fallida", codigo)) is False


def test_error_inesperado_se_reintenta_pasada_la_hora():
    assert _decide(_estado("2026-09-15T11:30:00", "fallida", "error_inesperado")) is False
    assert _decide(_estado("2026-09-15T10:00:00", "fallida", "error_inesperado")) is True


def test_sin_fecha_inicio_se_reintenta_en_cuanto_hay_fecha():
    viejo = _estado("2026-09-15T10:00:00", "fallida", "sin_fecha_inicio")
    assert _decide(viejo, fecha_configurada=False) is False
    assert _decide(viejo) is True


def test_con_errores_cuenta_como_terminada():
    assert _decide(_estado("2026-09-15T11:30:00", "con_errores")) is False
    assert _decide(_estado("2026-09-15T10:30:00", "con_errores")) is True


def test_terminada_en_ilegible_cuenta_como_nunca():
    assert _decide(_estado("no-es-una-fecha")) is True


def test_usa_la_hora_de_colombia_por_omision(monkeypatch):
    monkeypatch.setattr(hora, "ahora_colombia", lambda: AHORA)
    datos = {"gmail_configurado": True, "fecha_configurada": True, "en_curso": False}
    assert debe_sincronizar_al_abrir(_estado("2026-09-15T10:00:00"), **datos) is True
    assert debe_sincronizar_al_abrir(_estado("2026-09-15T11:30:00"), **datos) is False


def test_gmail_configurado_es_la_misma_condicion_que_crear_el_cliente(config):
    assert sincronizacion.gmail_configurado(config) is False
    with pytest.raises(sincronizacion.SincronizacionNoConfigurada):
        sincronizacion.cliente_desde_config(config)
    assert sincronizacion.gmail_configurado(dataclasses.replace(config, gmail_token="/ruta/inventada")) is True


# --- La API ---------------------------------------------------------------------------------

@pytest.fixture
def reloj(monkeypatch):
    class Reloj:
        actual = AHORA

    r = Reloj()
    monkeypatch.setattr(hora, "ahora_colombia", lambda: r.actual)
    return r


@pytest.fixture
def api_gmail(config, reloj):
    """Sesión iniciada en una app con ``GMAIL_TOKEN`` (el cliente de Gmail sigue siendo falso)."""
    app = crear_app(dataclasses.replace(config, gmail_token="/ruta/inventada/token.json"), Fabrica())
    with TestClient(app, follow_redirects=False) as cliente:
        csrf = cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"]
        yield ClienteApi(cliente, csrf)


def _campo(api):
    r = api.get("/api/sincronizacion")
    assert r.status_code == 200
    return r.json()["debe_sincronizar_al_abrir"]


def test_api_sin_gmail_configurado_es_false(api, config):
    configurar_saldo(config)
    assert _campo(api) is False


def test_api_sin_fecha_de_inicio_es_false(api_gmail):
    assert _campo(api_gmail) is False


def test_api_ciclo_completo(api_gmail, config, reloj):
    configurar_saldo(config)
    assert _campo(api_gmail) is True  # nunca sincronizó
    assert api_gmail.post("/api/sincronizacion").json()["estado"] == "ok"
    assert _campo(api_gmail) is False  # recién sincronizado
    reloj.actual = datetime(2026, 9, 15, 13, 0, 0)
    assert _campo(api_gmail) is False  # justo una hora
    reloj.actual = datetime(2026, 9, 15, 13, 0, 1)
    assert _campo(api_gmail) is True


def test_api_en_curso_es_false(api_gmail, config):
    configurar_saldo(config)
    candado = api_gmail.cliente.app.state.candado_sincronizacion
    with candado:
        datos = api_gmail.get("/api/sincronizacion").json()
    assert datos["en_curso"] is True
    assert datos["debe_sincronizar_al_abrir"] is False


def test_api_fallo_de_autorizacion_no_reintenta(api_gmail, config, reloj):
    configurar_saldo(config)
    ejecutar_sql(
        config,
        "INSERT INTO estado_sincronizacion (id, terminada_en, estado, origen, codigo_error) "
        "VALUES (1, '2026-09-01T08:00:00', 'fallida', 'comando', 'autorizacion_gmail')",
    )
    assert _campo(api_gmail) is False


def test_api_exige_sesion(cliente):
    r = cliente.get("/api/sincronizacion")
    assert r.status_code == 401
    assert "debe_sincronizar_al_abrir" not in r.text
