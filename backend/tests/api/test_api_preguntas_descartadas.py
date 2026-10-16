"""Adaptador de sombras descartadas: datos y Excel generados inventados."""
from datetime import date
from finanzas.bootstrap.descartes import componer_descartes
from finanzas.modulos.movimientos.descartes_contratos import DescarteNoPermitido
from finanzas import db, gestion_importaciones as gestion
from tests.soporte.ayudas_api import *  # noqa: F401,F403
from tests.soporte.excel_inventado import generar_excel
from tests.soporte.api_importaciones import analizar


def preparar(api, config, *, mixto=False, con_regla=False):
    configurar_saldo(config, centavos=100000)
    sombra = insertar_movimiento(config,monto=10000,descripcion="COMERCIO UNO INVENTADO")
    if con_regla:
        semilla = insertar_movimiento(config,monto=5000,descripcion="COMERCIO UNO INVENTADO")
        categoria = api.put(f"/api/movimientos/{semilla}/categoria",
            json={"categoria_id":1, "recordar":True})
        assert categoria.status_code == 200, categoria.text
    assert api.post(f"/api/movimientos/{sombra}/descartar").status_code == 200
    activo = insertar_movimiento(config,monto=10000,descripcion="COMERCIO DOS INVENTADO") if mixto else None
    archivo = generar_excel([(date(2026,8,10),"PAGO",None,-100 if mixto else -103)])
    a = analizar(api,archivo)
    assert a.status_code == 200, a.text
    r = api.post("/api/importaciones",json={"token":a.json()["token"]})
    assert r.status_code == 200, r.text
    return sombra, activo


def huella(config):
    with db.conectar(config.db_path) as conn:
        return gestion.huella(conn)


def test_preview_sombra_foto_intacta_y_confirmacion_cero_restauracion_explicita(api,config):
    sombra, _ = preparar(api,config)
    antes = huella(config)
    r = api.get("/api/conciliacion/preguntas")
    assert r.status_code == 200, r.text
    [p] = r.json()["preguntas"]
    [c] = p["candidatos"]
    assert c["id"] == sombra and c["origen"] == "gmail" and c["descartado"]
    assert c["nota_descartado"] == "Sigue descartado; confirmar no lo devuelve al saldo."
    opcion = next(o for o in p["opciones"] if o["id"] == f"si:{sombra}")
    assert opcion["consecuencia"].endswith("El saldo no cambia.")
    assert huella(config) == antes
    respuesta = api.post(f'/api/conciliacion/preguntas/{p["id"]}/respuesta',json={"opcion":opcion["id"]})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["efecto_saldo_centavos"] == 0
    assert respuesta.json()["saldo_centavos"] == 100000
    with db.conectar(config.db_path) as conn:
        f = conn.exec_driver_sql("SELECT id,monto_centavos,borrado_en FROM movimientos").one()
        assert f.id == sombra and f.monto_centavos == 10300 and f.borrado_en
    assert api.get("/api/movimientos?mes=2026-08").json()["movimientos"] == []
    restaurar = api.post(f"/api/movimientos/{sombra}/restaurar")
    assert restaurar.status_code == 200, restaurar.text
    assert restaurar.json()["saldo_despues_centavos"] == 89700


def test_candidatos_mixtos_marcados_y_opciones_mismos_ids(api,config):
    sombra, activo = preparar(api,config,mixto=True)
    antes = huella(config)
    [p] = api.get("/api/conciliacion/preguntas").json()["preguntas"]
    candidatos = {c["id"]:c for c in p["candidatos"]}
    assert set(candidatos) == {sombra,activo}
    assert candidatos[sombra]["descartado"] and candidatos[sombra]["nota_descartado"]
    assert not candidatos[activo]["descartado"] and candidatos[activo]["nota_descartado"] is None
    assert {o["id"] for o in p["opciones"]} >= {f"si:{sombra}",f"si:{activo}"}
    assert "descartado" in next(o["texto"] for o in p["opciones"] if o["id"] == f"si:{sombra}")
    assert huella(config) == antes


def test_otro_borrado_sin_reserva_no_es_candidato_ni_opcion(api,config):
    sombra, _ = preparar(api,config)
    p = ejecutar_sql(config,"SELECT id FROM preguntas_conciliacion WHERE respuesta IS NULL").fetchone()[0]
    legado = insertar_movimiento(config,monto=10000,descripcion="COMERCIO LEGADO INVENTADO")
    ejecutar_sql(config,"UPDATE movimientos SET borrado_en='2026-08-11T10:00:00' WHERE id=?",(legado,))
    ejecutar_sql(config,"INSERT INTO candidatos_pregunta (pregunta_id,movimiento_id) VALUES (?,?)",(p,legado))
    antes = huella(config)
    respuesta = api.get("/api/conciliacion/preguntas")
    assert respuesta.status_code == 200, respuesta.text
    [pregunta] = respuesta.json()["preguntas"]
    assert [c["id"] for c in pregunta["candidatos"]] == [sombra]
    assert all(o["id"] != f"si:{legado}" for o in pregunta["opciones"])
    assert huella(config) == antes


def test_sombra_no_puede_confirmarse_sin_csrf_y_get_exige_sesion(api,config):
    sombra, _ = preparar(api,config)
    [p] = api.get("/api/conciliacion/preguntas").json()["preguntas"]
    antes = huella(config)
    ruta = f'/api/conciliacion/preguntas/{p["id"]}/respuesta'
    assert api.cliente.post(ruta,json={"opcion":f"si:{sombra}"}).status_code == 403
    assert api.post(ruta,json={"opcion":f"si:{sombra}"},headers={"Origin":"https://sitio-inventado.invalid"}).status_code == 403
    api.cliente.cookies.clear()
    assert api.cliente.get("/api/conciliacion/preguntas").status_code == 401
    assert huella(config) == antes


def test_borrar_regla_retira_opcion_incompatible_sin_error_ni_mutacion(api,config):
    sombra, _ = preparar(api,config,con_regla=True)
    regla = ejecutar_sql(config,"SELECT regla_id FROM movimientos WHERE id=?",(sombra,)).fetchone()[0]
    assert api.delete(f"/api/reglas/{regla}").status_code == 200
    antes = huella(config)
    respuesta = api.get("/api/conciliacion/preguntas")
    assert respuesta.status_code == 200, respuesta.text
    [p] = respuesta.json()["preguntas"]
    assert p["candidatos"][0]["id"] == sombra and p["candidatos"][0]["descartado"]
    assert all(o["id"] != f"si:{sombra}" for o in p["opciones"])
    assert huella(config) == antes
    respuesta = api.post(f'/api/conciliacion/preguntas/{p["id"]}/respuesta',json={"opcion":f"si:{sombra}"})
    assert respuesta.status_code == 409, respuesta.text
    assert huella(config) == antes


def test_respuesta_traduce_contexto_incompatible_y_revierte_mutacion(api,config,monkeypatch):
    sombra, _ = preparar(api,config)
    [p] = api.get("/api/conciliacion/preguntas").json()["preguntas"]
    opcion = f"si:{sombra}"
    # La opción era válida, pero la aplicación descubre una incompatibilidad.
    from finanzas.modulos.importaciones import gestion_aplicacion
    from finanzas.modulos.importaciones.preguntas_aplicacion import OperarPreguntas
    monkeypatch.setattr(gestion_aplicacion,"_preguntas",lambda registro:([],{p["id"]:{opcion:(True,sombra,None)}}))
    def rechazar(conn,*args,**kwargs):
        conn.exec_driver_sql("UPDATE movimientos SET descripcion='CAMBIO INVENTADO' WHERE id=?",(sombra,))
        raise DescarteNoPermitido("Detalle interno inventado que no se publica")
    monkeypatch.setattr(OperarPreguntas, 'responder_pregunta',
        lambda self, *args, **kwargs: rechazar(self._unidad._conn, *args, **kwargs))
    antes = huella(config)
    respuesta = api.post(f'/api/conciliacion/preguntas/{p["id"]}/respuesta',json={"opcion":opcion})
    assert respuesta.status_code == 409
    assert respuesta.json() == {"detalle":"El movimiento descartado cambió. Recarga las diferencias antes de responder."}
    assert huella(config) == antes
