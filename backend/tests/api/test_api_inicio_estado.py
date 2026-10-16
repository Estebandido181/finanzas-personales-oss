"""Indicador de acciones pendientes: todos los datos son inventados."""
from finanzas.bootstrap.saldo import componer_saldo
from finanzas import db, sincronizacion
from tests.soporte.ayudas_api import *  # noqa: F401,F403


def leer(api):
    respuesta = api.get("/api/inicio/estado")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def pregunta(config):
    return ejecutar_sql(config, "INSERT INTO preguntas_conciliacion (tipo, fuente, fecha, monto_centavos) VALUES ('es_el_mismo', 'banco', '2026-08-10', -12300)").lastrowid


def test_vacio_no_configura_y_get_no_muta(api, config):
    assert leer(api) == dict(todo_al_dia=True, total_acciones=0, texto="Todo al día", areas=[])
    with db.conectar(config.db_path) as conn:
        assert componer_saldo(conn).leer_configuracion() is None
        assert sincronizacion.leer_estado(conn) is None


def test_mezcla_cuenta_acciones_sin_duplicar_flag_importacion(api, config):
    configurar_saldo(config)
    movimiento = insertar_movimiento(config)
    ejecutar_sql(config, "UPDATE movimientos SET no_en_banco=1 WHERE id=?", (movimiento,))
    ejecutar_sql(config, "INSERT INTO correos_no_reconocidos (gmail_id, fecha, asunto) VALUES ('correo-inventado', '2026-08-01', 'AVISO INVENTADO')")
    pregunta(config)
    with db.conectar(config.db_path) as conn:
        sincronizacion.guardar_estado(conn, "web", codigo_error="autorizacion_gmail")
        antes = componer_saldo(conn).saldo_actual()
    estado = leer(api)
    assert estado["total_acciones"] == 5
    assert estado["texto"] == "5 cosas por revisar"
    assert not estado["todo_al_dia"]
    assert {a["codigo"]: a["cantidad"] for a in estado["areas"]} == {
        "sin_categoria": 1, "no_reconocidos": 1, "sincronizacion_fallida": 1,
        "preguntas": 1, "no_en_banco": 1,
    }
    assert sum(a["cantidad"] for a in estado["areas"]) == estado["total_acciones"]
    assert all(a["href"].startswith("/") for a in estado["areas"])
    with db.conectar(config.db_path) as conn:
        assert componer_saldo(conn).saldo_actual() == antes


def test_ingreso_antiguo_singular_y_ajuste_excluido(api, config):
    configurar_saldo(config)
    insertar_movimiento(config, fecha_hora="2025-01-01T10:00:00", tipo="ingreso", monto=12300)
    insertar_movimiento(config, tipo="ajuste", monto=0, origen="manual")
    estado = leer(api)
    assert estado["total_acciones"] == 1
    assert estado["texto"] == "1 cosa por revisar"
    assert estado["areas"] == [dict(codigo="sin_categoria", titulo="Sin categoría", cantidad=1, href="/movimientos?vista=sin-categorizar")]


def test_resueltos_borrados_y_contadores_historicos_no_son_pendientes(api, config):
    movimiento = insertar_movimiento(config)
    ejecutar_sql(config, "UPDATE movimientos SET no_en_banco=1, revisado_no_en_banco=1, borrado_en='2026-08-11T10:00:00' WHERE id=?", (movimiento,))
    identificador = pregunta(config)
    ejecutar_sql(config, "UPDATE preguntas_conciliacion SET respuesta='no', respondida_en='2026-08-11T10:00:00' WHERE id=?", (identificador,))
    ejecutar_sql(config, "INSERT INTO correos_no_reconocidos (gmail_id, fecha, asunto) VALUES ('resuelto-inventado', '2026-08-01', 'AVISO INVENTADO')")
    ejecutar_sql(config, "DELETE FROM correos_no_reconocidos WHERE gmail_id='resuelto-inventado'")
    with db.conectar(config.db_path) as conn:
        sincronizacion.guardar_estado(conn, "web", resultado=sincronizacion.ResultadoSincronizacion(no_reconocidos=9, errores=2))
    assert leer(api)["total_acciones"] == 0


def test_sin_sesion_no_expone_conteos(cliente, config):
    insertar_movimiento(config)
    respuesta = cliente.get("/api/inicio/estado")
    assert respuesta.status_code == 401
    assert "total_acciones" not in respuesta.json()
