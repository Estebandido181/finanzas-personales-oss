"""Contrato31: varios XLSX, sesión, original efímero y cálculo aprobado."""
from datetime import date
import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient
from finanzas import db, gestion_importaciones as g
from finanzas.api.rutas_importacion import MIME_XLSX, TAMANO_MAXIMO_BYTES
from tests.soporte.excel_inventado import generar_excel
from tests.soporte.gmail_falso import ClienteFalso
from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.api_arranque import agregar, calcular  # ayudas compartidas






def test_varios_archivos_solapados_calcular_confirmar_undo_y_estado_real(api, config, fabrica):
    fabrica.cliente = ClienteFalso(correos={})
    archivo1 = agregar(api)
    assert archivo1.status_code == 200, archivo1.text
    token1 = archivo1.json()["token"]
    archivo2 = agregar(api, token1)
    assert archivo2.status_code == 200, archivo2.text
    token2 = archivo2.json()["token"]
    assert api.get(f"/api/arranque/archivos/{token1}").status_code == 410
    assert api.get(f"/api/arranque/archivos/{token2}").json()["puede_calcular"] is True
    calculo = calcular(api, token2)
    assert calculo.status_code == 200, calculo.text
    vista = calculo.json()
    assert vista["filas"] == vista["filas_solapadas"] == 1
    assert vista["saldo_inicial_centavos"] == 100500
    assert api.get("/api/saldo").json()["configuracion"] is None
    confirmado = api.post("/api/arranque/confirmar", json={"token": vista["token"]})
    assert confirmado.status_code == 200, confirmado.text
    ident = confirmado.json()["importacion"]["id"]
    assert confirmado.json()["calculo"]["saldo_inicial_centavos"] == 100500
    assert confirmado.json()["importacion"]["saldo_centavos"] == 100000
    assert confirmado.json()["sincronizacion"]["estado"] == "ok"
    assert fabrica.cliente.llamadas_listar == [date(2026, 7, 10)]
    assert api.post("/api/arranque/confirmar", json={"token": vista["token"]}).status_code == 410
    deshecho = api.post(f"/api/arranque/{ident}/deshacer")
    assert deshecho.status_code == 200, deshecho.text
    assert deshecho.json()["fase"] == "deshecho"
    assert deshecho.json()["importacion"]["saldo_centavos"] is None
    assert deshecho.json()["sincronizacion"] is None
    assert api.get("/api/saldo").json()["configuracion"] is None
    assert api.get(f"/api/importaciones/{ident}").status_code == 200
    with db.conectar(config.db_path) as conn:
        diario = conn.execute(text("SELECT diario FROM reversiones_importacion")).scalar_one()
        assert "3000000009" not in diario and "*0009" in diario


@pytest.mark.parametrize("headers,codigo", [({"X-CSRF-Token": ""}, 403),
    ({"Origin": "https://ajeno.invalid"}, 403), ({"Sec-Fetch-Site": "same-site"}, 403),
    ({"Content-Type": "multipart/form-data"}, 415), ({"X-Nombre-Archivo": "reporte.csv"}, 415)])
def test_upload_sesion_csrf_origin_y_tipo_estrictos(api, headers, codigo):
    assert agregar(api, **headers).status_code == codigo


def test_upload_sin_login_no_lee_archivo(api):
    api.delete("/api/sesion")
    assert agregar(api).status_code == 401


def test_rechazo_tipo_y_limite_sin_conservar_contenido(api):
    # Tamaño verificado antes del lector incluso con cabecera engañosa.
    assert agregar(api, contenido=b"PK" + b"a" * TAMANO_MAXIMO_BYTES, **{"Content-Length": "1"}).status_code == 413
    assert agregar(api, contenido=b"contenido inventado CSV").status_code == 400
    assert len(api.cliente.app.state.archivos_arranque._pendientes) == 0


@pytest.mark.parametrize("clase", ["macro", "formula", "bomba", "externo"])
def test_subida_rechaza_zip_peligroso_antes_de_staging(api, clase):
    from tests.soporte.excel_bancolombia import reescribir
    archivo = generar_excel([(date(2026, 7, 10), "TIENDA INVENTADA", None, "=-5" if clase == "formula" else -5)])
    if clase != "formula":
        nombre, contenido = {"macro": ("xl/vbaProject.bin", b"macro inventada"),
            "bomba": ("docProps/relleno.xml", b" " * (10 * 1024 * 1024 + 1)),
            "externo": ("xl/externalLinks/externalLink1.xml", b"<x/>")}[clase]
        archivo = reescribir(archivo, agregar={nombre: contenido})
    respuesta = agregar(api, contenido=archivo)
    assert respuesta.status_code == 400, respuesta.text
    assert len(api.cliente.app.state.archivos_arranque._pendientes) == 0


def test_archivos_y_preview_no_cruzan_sesiones_y_logout_revoca(api, app, fabrica):
    fabrica.cliente = ClienteFalso(correos={})
    token = agregar(api).json()["token"]
    with TestClient(app, base_url="http://testserver") as otro:
        login = otro.post("/api/sesion", json={"contrasena": CONTRASENA})
        csrf = login.json()["csrf_token"]
        assert otro.get(f"/api/arranque/archivos/{token}").status_code == 410
        assert otro.post("/api/arranque/calcular", json={"token": token, "modo": "arranque", "saldo_actual_centavos": 100000}, headers={"X-CSRF-Token": csrf}).status_code == 410
    preview = calcular(api, token).json()["token"]
    api.delete("/api/sesion")
    assert not app.state.archivos_arranque._pendientes
    assert not app.state.analisis_arranque._pendientes
    assert api.cliente.post("/api/arranque/confirmar", json={"token": preview}, headers={"X-CSRF-Token": api.csrf}).status_code == 401


def test_fallo_gmail_no_guarda_configuracion_ni_importa(api, fabrica, config):
    fabrica.error = RuntimeError("contenido privado inventado")
    token = agregar(api).json()["token"]
    with db.conectar(config.db_path) as conn:
        antes = g.huella(conn)
    respuesta = calcular(api, token)
    assert respuesta.status_code == 503
    assert "privado" not in respuesta.text
    with db.conectar(config.db_path) as conn:
        assert g.huella(conn) == antes


def test_upload_invalido_no_consume_lista_anterior_y_puede_descartar(api):
    token = agregar(api).json()["token"]
    assert agregar(api, token, contenido=b"inventado").status_code == 400
    assert api.get(f"/api/arranque/archivos/{token}").status_code == 200
    assert api.cliente.request("DELETE", "/api/arranque/archivos", json={"token": token}, headers={"X-CSRF-Token": api.csrf}).status_code == 200
    assert api.get(f"/api/arranque/archivos/{token}").status_code == 410


@pytest.mark.parametrize("saldo", [True, 1.5, "100", -1])
def test_saldo_strict_centavos_no_llega_a_gmail(api, fabrica, saldo):
    token = agregar(api).json()["token"]
    assert calcular(api, token, saldo=saldo).status_code == 422
    assert fabrica.llamadas == 0


def test_red_no_sostiene_lock_y_cambio_concurrente_no_importa(api, config, fabrica):
    def escribir_mientras_red():
        # Otra conexión puede escribir mientras se crea el cliente de Gmail.
        # La huella exige reanalizar después, sin pisar esa configuración.
        from finanzas.bootstrap.saldo import componer_saldo
        with db.conectar(config.db_path) as otra:
            componer_saldo(otra).configurar(42, date(2026, 8, 1))
        return ClienteFalso(correos={})
    api.cliente.app.state.fabrica_cliente_gmail = escribir_mientras_red
    token = agregar(api).json()["token"]
    resultado = calcular(api, token)
    assert resultado.status_code == 409, resultado.text
    with db.conectar(config.db_path) as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM movimientos")).scalar_one() == 0
        assert conn.execute(text("SELECT saldo_inicial_centavos FROM configuracion_saldo")).scalar_one() == 42


def test_quitar_archivo_invalida_preview_y_lista_anterior(api, fabrica):
    fabrica.cliente = ClienteFalso(correos={})
    token = agregar(api).json()["token"]
    previo = calcular(api, token).json()["token"]
    respuesta = api.cliente.request("DELETE", "/api/arranque/archivos/1", json={"token": token}, headers={"X-CSRF-Token": api.csrf})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["archivos"] == [] and respuesta.json()["puede_calcular"] is False
    assert api.get(f"/api/arranque/archivos/{token}").status_code == 410
    assert api.post("/api/arranque/confirmar", json={"token": previo}).status_code == 410


def test_archivos_y_analisis_vencen_sin_extender_ttl_por_get(api, app, fabrica):
    fabrica.cliente = ClienteFalso(correos={})
    reloj = [0]
    app.state.archivos_arranque._reloj = lambda: reloj[0]
    app.state.analisis_arranque._reloj = lambda: reloj[0]
    token = agregar(api).json()["token"]
    preview = calcular(api, token).json()["token"]
    reloj[0] = 899
    assert api.get(f"/api/arranque/archivos/{token}").status_code == 200
    reloj[0] = 900
    assert api.get(f"/api/arranque/archivos/{token}").status_code == 410
    assert api.post("/api/arranque/confirmar", json={"token": preview}).status_code == 410


def test_cookie_anterior_no_pierde_lista_o_preview(api, fabrica):
    fabrica.cliente = ClienteFalso(correos={})
    anterior = api.cliente.cookies.get("sesion")
    token = agregar(api).json()["token"]
    preview = calcular(api, token).json()["token"]
    api.cliente.cookies.set("sesion", anterior, domain="testserver.local", path="/")
    assert api.get(f"/api/arranque/archivos/{token}").status_code == 200
    assert api.post("/api/arranque/confirmar", json={"token": preview}).status_code == 200
