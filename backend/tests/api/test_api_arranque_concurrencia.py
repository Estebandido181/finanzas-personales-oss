"""Cruces deterministas del historial31, sin tiempos de espera arbitrarios."""
from finanzas.flujos.arranque import OperarArranque
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
import pytest
from finanzas import db, gestion_importaciones as g
from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.gmail_falso import ClienteFalso
from tests.soporte.api_arranque import agregar, calcular


@pytest.mark.parametrize("fase", ["gmail", "publicacion"])
@pytest.mark.parametrize("cambio", ["descartar", "quitar", "agregar", "logout", "vencer"])
def test_mutar_historial_en_vuelo_no_publica_ni_importa(api, app, config, monkeypatch, fase, cambio):
    entro, continuar = Event(), Event()
    reloj = [0]
    app.state.archivos_arranque._reloj = lambda: reloj[0]
    app.state.analisis_arranque._reloj = lambda: reloj[0]
    token = agregar(api).json()["token"]
    with db.conectar(config.db_path) as conn:
        antes = g.huella(conn)

    def esperar():
        entro.set()
        assert continuar.wait(10), "La prueba no liberó el cálculo"

    def fabrica():
        if fase == "gmail":
            esperar()
        return ClienteFalso(correos={})

    app.state.fabrica_cliente_gmail = fabrica
    if fase == "publicacion":
        original = OperarArranque.analizar
        def analizar(*args, **kwargs):
            resultado = original(*args, **kwargs)
            esperar()
            return resultado
        monkeypatch.setattr(OperarArranque, "analizar", analizar)

    with ThreadPoolExecutor(max_workers=1) as grupo:
        calculo = grupo.submit(calcular, api, token)
        try:
            assert entro.wait(10), "El cálculo no llegó al punto de cruce"
            if cambio == "descartar":
                respuesta = api.cliente.request("DELETE", "/api/arranque/archivos",
                    json={"token": token}, headers={"X-CSRF-Token": api.csrf})
            elif cambio == "quitar":
                respuesta = api.cliente.request("DELETE", "/api/arranque/archivos/1",
                    json={"token": token}, headers={"X-CSRF-Token": api.csrf})
            elif cambio == "agregar":
                respuesta = agregar(api, token)
            elif cambio == "logout":
                respuesta = api.delete("/api/sesion")
            else:
                reloj[0] = 900
                respuesta = api.get(f"/api/arranque/archivos/{token}")
            esperado = {"vencer": 410, "logout": 204}.get(cambio, 200)
            assert respuesta.status_code == esperado, respuesta.text
        finally:
            continuar.set()
        resultado = calculo.result(timeout=10)
    assert resultado.status_code == 410, resultado.text
    assert "token" not in resultado.json()
    assert not app.state.analisis_arranque._pendientes
    with db.conectar(config.db_path) as conn:
        assert g.huella(conn) == antes


def test_descarte_calculo_invalida_otro_calculo_en_gmail(api, app):
    app.state.fabrica_cliente_gmail = lambda: ClienteFalso(correos={})
    token = agregar(api).json()["token"]
    previo = calcular(api, token).json()["token"]
    def fabrica():
        respuesta = api.cliente.request("DELETE", "/api/arranque/analisis",
            json={"token": previo}, headers={"X-CSRF-Token": api.csrf})
        assert respuesta.status_code == 200
        return ClienteFalso(correos={})
    app.state.fabrica_cliente_gmail = fabrica
    assert calcular(api, token).status_code == 410
    assert api.post("/api/arranque/confirmar", json={"token": previo}).status_code == 410


@pytest.mark.parametrize("estado,esperado", [
    ("vacio", {"mostrar_arranque_inicial": True, "puede_iniciar_arranque": True, "puede_extender_historial": False}),
    ("configurado", {"mostrar_arranque_inicial": False, "puede_iniciar_arranque": True, "puede_extender_historial": True}),
    ("con_movimientos", {"mostrar_arranque_inicial": False, "puede_iniciar_arranque": False, "puede_extender_historial": True}),
])
def test_estado_arranque_comparte_guardas(api, config, fabrica, estado, esperado):
    if estado != "vacio":
        configurar_saldo(config)
    if estado == "con_movimientos":
        insertar_movimiento(config)
    respuesta = api.get("/api/arranque/estado")
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == esperado
    fabrica.cliente = ClienteFalso(correos={})
    token = agregar(api).json()["token"]
    assert calcular(api, token).status_code == (200 if esperado["puede_iniciar_arranque"] else 400)
    token = agregar(api).json()["token"]
    assert calcular(api, token, modo="extension").status_code == (200 if esperado["puede_extender_historial"] else 400)


def test_estado_arranque_requiere_sesion(api):
    api.delete("/api/sesion")
    assert api.get("/api/arranque/estado").status_code == 401


@pytest.mark.parametrize("primero", ["descartar", "confirmar"])
def test_confirmar_y_descartar_ordenan_commit_real(api, app, config, monkeypatch, primero):
    app.state.fabrica_cliente_gmail = lambda: ClienteFalso(correos={})
    token = agregar(api).json()["token"]
    calculo = calcular(api, token).json()["token"]
    entro, continuar, esperando = Event(), Event(), Event()

    def descartar():
        return api.cliente.request("DELETE", "/api/arranque/archivos",
            json={"token": token}, headers={"X-CSRF-Token": api.csrf})
    def confirmar():
        return api.post("/api/arranque/confirmar", json={"token": calculo})

    if primero == "descartar":
        assert descartar().status_code == 200
        assert confirmar().status_code == 410
        with db.conectar(config.db_path) as conn:
            assert g._foto(conn)["configuracion_saldo"] == []
            assert conn.execute(db.importaciones.select()).all() == []
        return

    class CandadoObservado:
        def __init__(self):
            self.candado = Lock()
        def __enter__(self):
            if self.candado.locked():
                esperando.set()
            self.candado.acquire()
        def __exit__(self, *args):
            self.candado.release()
    app.state.historial_arranque._sesiones[api.csrf].candado = CandadoObservado()
    original = OperarArranque.confirmar
    def guardar(*args):
        entro.set()
        assert continuar.wait(10)
        return original(*args)
    monkeypatch.setattr(OperarArranque, "confirmar", guardar)
    with ThreadPoolExecutor(max_workers=2) as grupo:
        confirmacion = grupo.submit(confirmar)
        assert entro.wait(10)
        descarte = grupo.submit(descartar)
        try:
            assert esperando.wait(10)
            assert not descarte.done()
            with db.conectar(config.db_path) as conn:
                assert conn.execute(db.importaciones.select()).all() == []
        finally:
            continuar.set()
        respuesta = confirmacion.result(timeout=10)
        assert respuesta.status_code == 200, respuesta.text
        assert descarte.result(timeout=10).status_code == 200
    with db.conectar(config.db_path) as conn:
        assert len(conn.execute(db.importaciones.select()).all()) == 1
    assert confirmar().status_code == 410
