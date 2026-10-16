"""Seguridad y contrato real30 con archivos generados en memoria."""
from datetime import date, datetime
import pytest
from sqlalchemy import text
from finanzas import db
from finanzas.api.rutas_importacion import MIME_XLSX, TAMANO_MAXIMO_BYTES
from tests.soporte.excel_inventado import generar_excel
from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.api_importaciones import analizar, excel, excel_con_primer_dia, primer_dia  # ayudas compartidas






def test_flujo_analizar_confirmar_repetir_deshacer(api, config):
    configurar_saldo(config)
    a = analizar(api)
    assert a.status_code == 200, a.text
    assert api.get("/api/importaciones/ultima").json()["importacion"] is None
    r = api.post("/api/importaciones", json={"token": a.json()["token"]})
    assert r.status_code == 200, r.text
    assert r.json()["resumen"] == a.json()["resumen"]
    assert r.json()["saldo_centavos"] == a.json()["saldo_despues_centavos"]
    assert r.json()["siguiente"] == "categorizar"
    assert r.json()["grupos"][0]["cuantos"] == 1
    assert api.post("/api/importaciones", json={"token": a.json()["token"]}).status_code == 410
    assert api.post(f'/api/importaciones/{r.json()["id"]}/deshacer').status_code == 200


@pytest.mark.parametrize("dia,ofrece", [(date(2026, 7, 31), True), (date(2026, 8, 1), False)])
def test_oferta_extender_historial_preview_y_resultado_sin_cambiar_saldo(api, config, dia, ofrece):
    configurar_saldo(config, centavos=100000)
    archivo = generar_excel([(dia, "COMPRA INVENTADA", None, -5),
        (dia, "INGRESO INVENTADO", None, 5)])
    previo = api.get("/api/saldo").json()["saldo_centavos"]
    respuesta = analizar(api, archivo)
    assert respuesta.status_code == 200, respuesta.text
    vista = respuesta.json()
    assert vista["resumen"]["anteriores"] == (2 if ofrece else 0)
    assert vista["puede_extender_historial"] is ofrece
    assert vista["saldo_antes_centavos"] == vista["saldo_despues_centavos"] == previo
    assert api.get("/api/saldo").json()["saldo_centavos"] == previo
    resultado = api.post("/api/importaciones", json={"token": vista["token"]})
    assert resultado.status_code == 200, resultado.text
    ident = resultado.json()["id"]
    assert resultado.json()["puede_extender_historial"] is ofrece
    assert resultado.json()["saldo_centavos"] == previo
    assert api.get(f"/api/importaciones/{ident}").json()["puede_extender_historial"] is ofrece
    assert api.get("/api/saldo").json()["saldo_centavos"] == previo
    deshecho = api.post(f"/api/importaciones/{ident}/deshacer")
    assert deshecho.status_code == 200, deshecho.text
    assert deshecho.json()["puede_extender_historial"] is False
    assert api.get("/api/saldo").json()["saldo_centavos"] == previo


def test_aviso_tardio_ambiguo_anticipa409_y_conserva_huella(api, config):
    from finanzas import importacion as imp, gestion_importaciones as g
    from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import MovimientoExtraido
    configurar_saldo(config, centavos=100000)
    archivo = generar_excel([(date(2026, 8, 10), "TIENDA EJEMPLO", None, -5)])
    a = analizar(api, archivo).json()
    ident = api.post("/api/importaciones", json={"token": a["token"]}).json()["id"]
    assert api.get(f"/api/importaciones/{ident}").json()["se_puede_deshacer"] is True
    with db.conectar(config.db_path) as conn:
        with db.transaccion(conn):
            assert imp.recibir_aviso(conn, "aviso-ambiguo-inventado", MovimientoExtraido("compra", 510,
                datetime(2026, 8, 10, 10), "OTRO INVENTADO")) == "pregunta"
        antes = g.huella(conn)
    detalle = api.get(f"/api/importaciones/{ident}")
    assert detalle.status_code == 200, detalle.text
    assert detalle.json()["se_puede_deshacer"] is False
    assert detalle.json()["motivo_no_deshacer"] == g.MENSAJE_REVERSION
    pregunta = api.get("/api/conciliacion/preguntas").json()["preguntas"][0]
    assert pregunta["movimiento"]["origen"] == "gmail"
    assert pregunta["candidatos"][0]["origen"] == "extracto"
    assert api.post(f"/api/importaciones/{ident}/deshacer").status_code == 409
    with db.conectar(config.db_path) as conn:
        assert g.huella(conn) == antes


@pytest.mark.parametrize("origen", ["manual", "gmail"])
def test_contrato_origen_ingreso_candidato_y_pregunta_banco(api, config, origen):
    configurar_saldo(config)
    insertar_movimiento(config, monto=510, tipo="ingreso", origen=origen, descripcion="INGRESO ESTELAR")
    archivo = generar_excel([(date(2026, 8, 10), "ABONO LUNAR", None, 5)])
    a = analizar(api, archivo).json()
    assert api.post("/api/importaciones", json={"token": a["token"]}).status_code == 200
    pregunta = api.get("/api/conciliacion/preguntas").json()["preguntas"][0]
    assert pregunta["movimiento"]["origen"] == "extracto"
    assert pregunta["candidatos"][0]["origen"] == origen


def test_contrato_no_en_banco_conserva_origen_correo(api, config):
    configurar_saldo(config)
    insertar_movimiento(config, monto=2000)
    a = analizar(api, excel_con_primer_dia(config)).json()
    assert api.post("/api/importaciones", json={"token": a["token"]}).status_code == 200
    movimiento = api.get("/api/conciliacion/no-esta-en-el-banco").json()["movimientos"][0]
    assert movimiento["movimiento"]["origen"] == "gmail"


def test_referencia_original_no_persistida_ni_logueada(api, config, caplog):
    configurar_saldo(config)
    a = analizar(api).json()
    assert api.post("/api/importaciones", json={"token": a["token"]}).status_code == 200
    with db.conectar(config.db_path) as conn:
        assert conn.execute(text("SELECT referencia FROM movimientos")).scalar_one() == "*0009"
        diario = conn.execute(text("SELECT diario FROM reversiones_importacion")).scalar_one()
        assert "3000000009" not in diario and "reporte-inventado" not in diario
    assert "3000000009" not in caplog.text and "reporte-inventado" not in caplog.text


def test_aceptar_sugerencias_es_explicito_atomico_y_reversible(api, config):
    configurar_saldo(config, centavos=1000000)
    insertar_movimiento(config, monto=51000, descripcion="CORREO INVENTADO", fecha_hora="2026-08-10T10:00:00")
    insertar_movimiento(config, monto=61000, descripcion="OTRO CORREO", fecha_hora="2026-08-11T10:00:00")
    archivo = generar_excel([(date(2026, 8, 10), "BANCO PRIMERO", None, -500),
        (date(2026, 8, 11), "BANCO SEGUNDO", None, -600)])
    a = analizar(api, archivo).json()
    assert api.post("/api/importaciones", json={"token": a["token"]}).status_code == 200
    pendientes = api.get("/api/conciliacion/preguntas").json()
    assert pendientes["total"] == pendientes["con_sugerencia"] == 2
    assert api.get("/api/saldo").json()["saldo_centavos"] == 1000000 - 112000
    respuesta = api.post("/api/conciliacion/preguntas/aceptar-sugerencias")
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["efecto_saldo_centavos"] == 2000
    assert api.get("/api/conciliacion/preguntas").json()["total"] == 0
    assert api.post("/api/conciliacion/deshacer", json={"token": respuesta.json()["deshacer"]["token"]}).status_code == 200
    assert api.get("/api/conciliacion/preguntas").json() == pendientes
    assert api.get("/api/saldo").json()["saldo_centavos"] == 1000000 - 112000


def test_undo_borrado_despues_de_importar_banco_real_es409_sin_duplicar(api, config):
    configurar_saldo(config, centavos=100000)
    mid = insertar_movimiento(config, monto=500)
    ancla = primer_dia(config)  # su correo de $777 ya cuenta en el saldo
    def importar_valor(valor):
        archivo = generar_excel([ancla, (date(2026, 8, 10), "BANCO INVENTADO", None, valor)])
        a = analizar(api, archivo)
        assert a.status_code == 200, a.text
        assert api.post("/api/importaciones", json={"token": a.json()["token"]}).status_code == 200
    importar_valor(-20)
    r = api.post(f"/api/conciliacion/no-esta-en-el-banco/{mid}/respuesta", json={"opcion": "borrar"})
    assert r.status_code == 200, r.text
    importar_valor(-5)
    antes = api.get("/api/saldo").json()
    assert antes["saldo_centavos"] == 97500 - 77700
    with db.conectar(config.db_path) as conn:
        from finanzas.gestion_importaciones import huella
        foto = huella(conn)
    assert api.post("/api/conciliacion/deshacer", json={"token": r.json()["deshacer"]["token"]}).status_code == 409
    despues = api.get("/api/saldo").json()
    # El token de ingreso rota en cada lectura; todos los datos financieros permanecen.
    antes.pop("token_ingreso")
    despues.pop("token_ingreso")
    assert despues == antes
    with db.conectar(config.db_path) as conn:
        assert huella(conn) == foto


def test_undo_respuesta_tras_importacion_idempotente_es409_y_no_reabre(api, config):
    configurar_saldo(config, centavos=100000)
    mid = insertar_movimiento(config, monto=51000, descripcion="OTRO INVENTADO")
    archivo = generar_excel([(date(2026, 8, 10), "BANCO PRIMERO", None, -500)])
    def importar():
        a = analizar(api, archivo)
        assert a.status_code == 200
        assert api.post("/api/importaciones", json={"token": a.json()["token"]}).status_code == 200
    importar()
    p = api.get("/api/conciliacion/preguntas").json()["preguntas"][0]
    r = api.post(f'/api/conciliacion/preguntas/{p["id"]}/respuesta', json={"opcion": f"si:{mid}"})
    assert r.status_code == 200, r.text
    importar()
    with db.conectar(config.db_path) as conn:
        from finanzas.gestion_importaciones import huella
        foto = huella(conn)
    assert api.post("/api/conciliacion/deshacer", json={"token": r.json()["deshacer"]["token"]}).status_code == 409
    assert api.get("/api/conciliacion/preguntas").json()["total"] == 0
    assert api.get("/api/saldo").json()["saldo_centavos"] == 50000
    with db.conectar(config.db_path) as conn:
        assert huella(conn) == foto


@pytest.mark.parametrize("headers,codigo", [({"X-CSRF-Token": ""}, 403),
    ({"Origin": "https://ajeno.invalid"}, 403), ({"Sec-Fetch-Site": "same-site"}, 403),
    ({"Content-Type": "multipart/form-data"}, 415)])
def test_auth_csrf_origin_sin_relajar(api, headers, codigo):
    assert analizar(api, **headers).status_code == codigo


def test_sin_sesion_rechazado(api):
    api.delete("/api/sesion")
    assert analizar(api).status_code == 401


@pytest.mark.parametrize("contenido,headers,codigo", [(b"valor,privado-inventado", {}, 400),
    (b"PKmalformado", {}, 400), (b"texto", {"X-Nombre-Archivo": "privado.xlsm"}, 415),
    (b"x" * (TAMANO_MAXIMO_BYTES + 1), {}, 413),
    (b"texto", {"Content-Length": str(TAMANO_MAXIMO_BYTES + 1)}, 413)], ids=["csv", "zip_roto", "xlsm", "grande", "largo_declarado"])
def test_rechazo_sin_eco_y_sin_escritura(api, config, contenido, headers, codigo):
    configurar_saldo(config)
    r = analizar(api, contenido, **headers)
    assert r.status_code == codigo
    assert "privado" not in r.text
    assert api.get("/api/importaciones/ultima").json()["importacion"] is None


def test_limite_sin_content_length_antes_de_descomprimir(api, config, monkeypatch):
    configurar_saldo(config)
    from finanzas.api import rutas_importacion as rutas
    def no_leer(*args):
        pytest.fail("No se debe abrir ni descomprimir una subida enorme.")
    monkeypatch.setattr(rutas, "leer_excel_movimientos", no_leer)
    r = api.cliente.post("/api/importaciones/analizar", content=iter([b"x" * (TAMANO_MAXIMO_BYTES // 2)] * 3),
        headers={"Content-Type": MIME_XLSX, "X-CSRF-Token": api.csrf})
    assert r.status_code == 413


def test_token_analisis_no_cruza_sesion(api, config):
    configurar_saldo(config)
    a = analizar(api).json()
    api.delete("/api/sesion")
    login = api.cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).json()
    assert api.cliente.post("/api/importaciones", json={"token": a["token"]},
        headers={"X-CSRF-Token": login["csrf_token"]}).status_code == 410


def test_analisis_concurrentes_segundo409_sin_importar(api, config):
    configurar_saldo(config)
    a, b = analizar(api).json(), analizar(api).json()
    assert api.post("/api/importaciones", json={"token": a["token"]}).status_code == 200
    assert api.post("/api/importaciones", json={"token": b["token"]}).status_code == 409
    assert api.post("/api/importaciones", json={"token": b["token"]}).status_code == 410


@pytest.mark.parametrize("ident", ["0", "-1", "9" * 100])
def test_ids_invalidos_no_alcanzan_sqlite(api, ident):
    assert api.get(f"/api/importaciones/{ident}").status_code == 422
    assert api.post(f"/api/importaciones/{ident}/deshacer").status_code == 422
    assert api.post(f"/api/conciliacion/preguntas/{ident}/respuesta", json={"opcion": "no"}).status_code == 422
    assert api.post(f"/api/conciliacion/no-esta-en-el-banco/{ident}/respuesta", json={"opcion": "borrar"}).status_code == 422


def test_sin_configuracion_error_controlado(api):
    assert analizar(api).status_code == 400


def test_descartar_borra_analisis_sin_importar(api, config):
    configurar_saldo(config)
    a = analizar(api).json()
    assert api.cliente.request("DELETE", "/api/importaciones/analisis", json={"token": a["token"]},
        headers={"X-CSRF-Token": api.csrf}).json() == {"descartado": True}
    assert api.post("/api/importaciones", json={"token": a["token"]}).status_code == 410


def test_deshacer_decision_no_cruza_sesion(api, config):
    configurar_saldo(config)
    mid = insertar_movimiento(config, monto=100000, fecha_hora="2026-08-10T10:00:00")
    a = analizar(api, excel_con_primer_dia(config)).json()
    assert api.post("/api/importaciones", json={"token": a["token"]}).status_code == 200
    r = api.post(f"/api/conciliacion/no-esta-en-el-banco/{mid}/respuesta", json={"opcion": "borrar"})
    assert r.status_code == 200, r.text
    token = r.json()["deshacer"]["token"]
    api.delete("/api/sesion")
    nueva = api.cliente.post("/api/sesion", json={"contrasena": CONTRASENA}).json()
    assert api.cliente.post("/api/conciliacion/deshacer", json={"token": token},
        headers={"X-CSRF-Token": nueva["csrf_token"]}).status_code == 410


def test_tokens_bancarios_no_consumen_deshacer38(api, config):
    configurar_saldo(config)
    rid = insertar_regla(config)
    borrado = api.delete(f"/api/reglas/{rid}").json()
    token = borrado["deshacer"]["token"]
    assert api.post("/api/conciliacion/deshacer", json={"token": token}).status_code == 410
    assert api.post("/api/deshacer", json={"token": token}).status_code == 200


def test_tokens_caducan_y_reinicio_pierde_analisis(api, config, app):
    configurar_saldo(config)
    a = analizar(api).json()
    from finanzas.infraestructura.tokens_bancarios_ram import RegistroBancario
    app.state.analisis_importaciones = RegistroBancario(segundos=900)
    assert api.post("/api/importaciones", json={"token": a["token"]}).status_code == 410


def test_singleton_sin_descripcion_se_categoriza_sin_regla(api, config):
    configurar_saldo(config)
    # El lector exige descripción de banco, pero filas históricas pueden
    # no tenerla; la API admite resolver esos pendientes sin inventar regla.
    mid = insertar_movimiento(config, descripcion="", monto=500)
    r = api.post("/api/movimientos/categorizar-grupo", json={"clave": f"sin-descripcion:{mid}", "ids": [mid], "categoria_id": 1})
    assert r.status_code == 200, r.text
    assert r.json()["categorizados"] == 1 and not r.json()["regla_guardada"]


def test_cookie_anterior_de_get_concurrente_no_pierde_analisis(api, config):
    configurar_saldo(config)
    anterior = api.cliente.cookies.get("sesion")
    a = analizar(api).json()
    api.cliente.cookies.set("sesion", anterior, domain="testserver.local", path="/")
    assert api.post("/api/importaciones", json={"token": a["token"]}).status_code == 200


def test_logout_revoca_analisis_incluso_con_cookie_anterior(api, config):
    configurar_saldo(config)
    anterior = api.cliente.cookies.get("sesion")
    a = analizar(api).json()
    api.delete("/api/sesion")
    api.cliente.cookies.set("sesion", anterior, domain="testserver.local", path="/")
    assert api.post("/api/importaciones", json={"token": a["token"]}).status_code == 410


@pytest.mark.parametrize("clase", ["macro", "formula", "bomba", "externo"])
def test_api_rechaza_zip_peligroso_antes_de_guardar(api, config, clase):
    from tests.soporte.excel_bancolombia import reescribir
    configurar_saldo(config)
    if clase == "formula":
        archivo = generar_excel([(date(2026, 8, 10), "TIENDA EJEMPLO", None, "=-500")])
    else:
        nombre, contenido = {"macro": ("xl/vbaProject.bin", b"macro inventada"),
            "bomba": ("docProps/relleno.xml", b" " * (10 * 1024 * 1024 + 1)),
            "externo": ("xl/externalLinks/externalLink1.xml", b"<x/>")}[clase]
        archivo = reescribir(excel(), agregar={nombre: contenido})
    r = analizar(api, archivo)
    assert r.status_code == 400, r.text
    assert api.get("/api/importaciones/ultima").json()["importacion"] is None
