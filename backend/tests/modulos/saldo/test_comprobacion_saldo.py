"""Referencia manual inventada: diagnóstico exacto, efímero y protegido."""
from finanzas.modulos.saldo import politica as saldo_politica
from datetime import date, datetime
from decimal import Decimal
import json
from fastapi.testclient import TestClient
from sqlalchemy import text

from finanzas import db, gestion_importaciones as g
from finanzas.compartido import hora
from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.excel_inventado import generar_excel
from tests.soporte.gmail_falso import ClienteFalso
from tests.soporte.api_importaciones import analizar
from tests.soporte.api_arranque import agregar, calcular


def comprobar(api, real, token=None, tipo=None):
    return api.post("/api/saldo/comprobar", json={"saldo_real_centavos": real,
        **({"token_analisis": token, "tipo_analisis": tipo} if token else {})})


def huella(config):
    with db.conectar(config.db_path) as conn:
        return g.huella(conn)


def test_actual_centavos_desglose_hora_y_ninguna_mutacion(api, config, monkeypatch):
    configurar_saldo(config, centavos=10000)
    insertar_movimiento(config, monto=201, tipo="ingreso")
    insertar_movimiento(config, monto=100, tipo="compra")
    insertar_movimiento(config, monto=-1, tipo="ajuste", origen="manual")
    monkeypatch.setattr(hora, "ahora_colombia", lambda: datetime(2026, 10, 6, 13, 14, 15))
    antes = huella(config)
    for real, diferencia in [(10100, 0), (10101, 1), (0, -10100)]:
        r = comprobar(api, real)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["saldo_app_centavos"] == 10100
        assert d["diferencia_centavos"] == d["resto_no_explicado_centavos"] == diferencia
        assert d["coincide"] is (diferencia == 0)
        assert d["recibido_en"] == "2026-10-06T13:14:15"
        assert d["huella"] == antes
        assert d["desglose_despues"] == {"saldo_inicial_centavos": 10000,
            "ingresos_centavos": 201, "gastos_centavos": 100, "ajustes_centavos": -1}
        assert d["contribuciones"] is None
        assert d["cobertura"]["cobertura_hasta_consulta_verificada"] is False
    assert huella(config) == antes


def test_sin_configuracion_no_se_compara_como_cero(api, config):
    antes = huella(config)
    d = comprobar(api, 0).json()
    assert d["estado"] == "sin_configuracion"
    assert d["saldo_app_centavos"] is d["diferencia_centavos"] is d["coincide"] is None
    assert d["desglose_despues"] is None and d["verificacion_independiente"] is False
    assert huella(config) == antes
    configurar_saldo(config, centavos=0)
    d = comprobar(api, 0).json()
    assert d["estado"] == "disponible" and d["coincide"] is True


def test_entrada_estricta_y_sesion_csrf_origin(api, config):
    configurar_saldo(config, centavos=0)
    antes = huella(config)
    for invalido in [True, 1.5, "100", -1, saldo_politica.MAXIMO_CENTAVOS + 1]:
        assert comprobar(api, invalido).status_code == 422
    assert api.post("/api/saldo/comprobar", json={"saldo_real_centavos": 0, "recibido_en": "x"}).status_code == 422
    assert api.post("/api/saldo/comprobar", json={"saldo_real_centavos": 0, "token_analisis": "inventado"}).status_code == 422
    assert comprobar(api, saldo_politica.MAXIMO_CENTAVOS).status_code == 200
    assert api.cliente.post("/api/saldo/comprobar", json={"saldo_real_centavos": 0}).status_code == 403
    assert api.post("/api/saldo/comprobar", json={"saldo_real_centavos": 0}, headers={"Origin": "https://ajeno.invalid"}).status_code == 403
    api.delete("/api/sesion")
    assert comprobar(api, 0).status_code == 401
    assert huella(config) == antes


def test_preview_importacion_agregados_corregidos_y_confirmacion_sin_consumir(api, config):
    configurar_saldo(config, centavos=100000)
    insertar_movimiento(config, monto=500, descripcion="TIENDA INVENTADA")
    archivo = generar_excel([(date(2026, 8, 10), "TIENDA INVENTADA", None, Decimal("-5.10")),
        (date(2026, 8, 12), "ABONO INVENTADO", None, 2)])
    a = analizar(api, archivo).json()
    antes = huella(config)
    r = comprobar(api, 99690, a["token"], "importacion")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["saldo_antes_centavos"] == 99500 and d["saldo_despues_centavos"] == 99690
    assert d["coincide"] and d["efecto_conciliacion_centavos"] == 190
    assert d["contribuciones"] == {"agregados_centavos": 200, "corregidos_centavos": -10,
        "ajustes_centavos": 0, "cambio_inicial_centavos": 0, "otros_centavos": 0}
    assert sum(d["contribuciones"].values()) == d["efecto_conciliacion_centavos"]
    assert huella(config) == antes
    assert comprobar(api, 99691, a["token"], "importacion").json()["diferencia_centavos"] == 1
    r = api.post("/api/importaciones", json={"token": a["token"]})
    assert r.status_code == 200 and r.json()["saldo_centavos"] == 99690
    assert comprobar(api, 99690, a["token"], "importacion").status_code == 410


def test_preview_importacion_propietario_ttl_y_huella(api, app, config):
    configurar_saldo(config, centavos=100000)
    reloj = [0]
    app.state.analisis_importaciones._reloj = lambda: reloj[0]
    token = analizar(api, generar_excel([(date(2026, 8, 10), "TIENDA INVENTADA", None, -5)])).json()["token"]
    with TestClient(app, base_url="http://testserver") as otro:
        csrf = otro.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"]
        assert otro.post("/api/saldo/comprobar", json={"saldo_real_centavos": 0,
            "token_analisis": token, "tipo_analisis": "importacion"}, headers={"X-CSRF-Token": csrf}).status_code == 410
    reloj[0] = 899
    assert comprobar(api, 99500, token, "importacion").status_code == 200
    insertar_movimiento(config, monto=1, origen="manual", tipo="ingreso")
    antes = huella(config)
    assert comprobar(api, 99500, token, "importacion").status_code == 409
    assert huella(config) == antes
    reloj[0] = 900
    assert comprobar(api, 99500, token, "importacion").status_code == 410


def test_respuesta_de_duda_actualiza_comparacion_con_efecto_exacto(api, config):
    configurar_saldo(config, centavos=100000)
    mid = insertar_movimiento(config, monto=500, descripcion="TIENDA INVENTADA")
    a = analizar(api, generar_excel([(date(2026, 8, 10), "OTRO INVENTADO", None, Decimal("-5.10"))])).json()
    assert api.post("/api/importaciones", json={"token": a["token"]}).status_code == 200
    antes = comprobar(api, 99490).json()
    assert antes["diferencia_centavos"] == -10 and antes["pendientes"]["preguntas"] == 1
    pregunta = api.get("/api/conciliacion/preguntas").json()["preguntas"][0]
    respuesta = api.post(f'/api/conciliacion/preguntas/{pregunta["id"]}/respuesta', json={"opcion": f"si:{mid}"})
    assert respuesta.status_code == 200, respuesta.text
    despues = comprobar(api, 99490).json()
    assert despues["diferencia_centavos"] == antes["diferencia_centavos"] - respuesta.json()["efecto_saldo_centavos"] == 0
    assert despues["pendientes"]["preguntas"] == 0 and despues["coincide"] is True


def test_reportes_de_cualquier_tamano_sin_prometer_cobertura(api, config):
    """D51: el tope de filas del banco no se conoce; la protección del primer
    día aplica siempre y no se cuentan "archivos de 120 filas"."""
    configurar_saldo(config, centavos=1000000)
    for cantidad in (50, 120, 146):
        archivo = generar_excel([(date(2026, 8, 10), "TIENDA INVENTADA", None, -1)] * cantidad)
        a = analizar(api, archivo)
        assert a.status_code == 200, a.text
        r = comprobar(api, 1000000 - cantidad * 100, a.json()["token"], "importacion")
        assert r.status_code == 200, r.text
        cobertura = r.json()["cobertura"]
        assert cobertura["archivos_de_120_filas"] is None
        assert cobertura["proteccion_ausencias_conservadora"] is True
        assert cobertura["cobertura_verificada"] is False


def test_extension_referencia_independiente_preserva_objetivo_y_no_persiste(api, config, fabrica):
    fabrica.cliente = ClienteFalso(correos={})
    configurar_saldo(config, centavos=100000)
    token = agregar(api).json()["token"]
    antes = huella(config)
    r = api.post("/api/arranque/calcular", json={"token": token, "modo": "extension",
        "saldo_actual_centavos": 0, "saldo_real_centavos": 100001})
    assert r.status_code == 200, r.text
    vista = r.json()
    d = vista["comprobacion_saldo"]
    assert d["saldo_antes_centavos"] == d["saldo_despues_centavos"] == 100000
    assert d["diferencia_centavos"] == 1 and d["verificacion_independiente"] is True
    assert d["coincide"] is False and d["diferencia_forzada_por_inicial"] is False
    assert d["contribuciones"]["cambio_inicial_centavos"] == 500
    assert d["contribuciones"]["agregados_centavos"] == -500
    assert huella(config) == antes
    assert comprobar(api, 100001, vista["token"], "arranque").json()["diferencia_centavos"] == 1
    confirmado = api.post("/api/arranque/confirmar", json={"token": vista["token"]})
    assert confirmado.status_code == 200, confirmado.text
    assert confirmado.json()["saldo_inicial_centavos"] == 100500
    assert api.get("/api/saldo").json()["saldo_centavos"] == 100000
    with db.conectar(config.db_path) as conn:
        guardado = json.loads(conn.execute(text("SELECT arranque FROM reversiones_importacion")).scalar_one())
        assert "comprobacion_saldo" not in guardado and "saldo_real_centavos" not in guardado


def test_primer_arranque_igualdad_por_calculo_y_referencia_unica(api, config, fabrica):
    fabrica.cliente = ClienteFalso(correos={})
    token = agregar(api).json()["token"]
    antes = huella(config)
    r = api.post("/api/arranque/calcular", json={"token": token, "modo": "arranque",
        "saldo_actual_centavos": 100000, "saldo_real_centavos": 100001})
    assert r.status_code == 400
    vista = calcular(api, token).json()
    d = vista["comprobacion_saldo"]
    assert d["saldo_antes_centavos"] is None
    assert d["diferencia_centavos"] == 0 and d["coincide"] is True
    assert d["verificacion_independiente"] is False and d["diferencia_forzada_por_inicial"] is True
    assert huella(config) == antes


def test_preview31_generacion_owner_ttl_huella_sin_consumir(api, app, config, fabrica):
    fabrica.cliente = ClienteFalso(correos={})
    reloj = [0]
    app.state.archivos_arranque._reloj = lambda: reloj[0]
    app.state.analisis_arranque._reloj = lambda: reloj[0]
    token = agregar(api).json()["token"]
    vista = calcular(api, token).json()
    with TestClient(app, base_url="http://testserver") as otro:
        csrf = otro.post("/api/sesion", json={"contrasena": CONTRASENA}).json()["csrf_token"]
        assert otro.post("/api/saldo/comprobar", json={"saldo_real_centavos": 0,
            "token_analisis": vista["token"], "tipo_analisis": "arranque"}, headers={"X-CSRF-Token": csrf}).status_code == 410
    reloj[0] = 899
    assert comprobar(api, 100000, vista["token"], "arranque").status_code == 200
    reloj[0] = 900
    assert comprobar(api, 100000, vista["token"], "arranque").status_code == 410
    reloj[0] = 1000
    token = agregar(api).json()["token"]
    vista = calcular(api, token).json()
    configurar_saldo(config, centavos=10)
    antes = huella(config)
    assert comprobar(api, 0, vista["token"], "arranque").status_code == 409
    assert huella(config) == antes
    assert api.cliente.request("DELETE", "/api/arranque/archivos/1", json={"token": token},
        headers={"X-CSRF-Token": api.csrf}).status_code == 200
    assert comprobar(api, 0, vista["token"], "arranque").status_code == 410
