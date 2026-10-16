"""Guardado de la conciliación (ítem 29): importar, aviso tardío y respuestas.

Base SQLite de verdad (migrada hasta la 0008) y datos inventados: comercios
"EJEMPLO", celulares 300000000N y cuentas en ceros.
"""

from __future__ import annotations
from finanzas.bootstrap.saldo import componer_saldo
from finanzas.modulos.saldo import contratos as saldo_contratos

from datetime import date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from finanzas.modulos.importaciones import motor as c
from finanzas import db, gestion_importaciones, importacion
from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import MovimientoExcel, leer_excel_movimientos
from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import MovimientoExtraido
from finanzas.gmail import CorreoGmail
from finanzas.compartido.hora import ZONA_COLOMBIA
from finanzas.sincronizacion import sincronizar
from tests.soporte import excel_inventado
from tests.soporte.ayudas_db import sql as _sql
from tests.soporte.gmail_falso import LEGITIMO as autenticacion
from tests.soporte.gmail_falso import ClienteFalso
from tests.soporte.importacion import _compra, ajuste_el_dia, conn, del_correo, fila, foto, movimiento, primer_dia, sql  # ayudas compartidas

SALDO_INICIAL = 100_000_000






_gmail = iter(range(1, 100_000))












# --- Importar dos veces no cambia nada -------------------------------------------------------

def test_importar_dos_veces_el_mismo_reporte_no_cambia_nada(conn):
    compra = del_correo(conn, 25, "compra", 3150000, "RESTAURANTE EJEMPLO")
    nequi = del_correo(conn, 4, "transferencia", 620000, "*3000000001")
    filas = leer_excel_movimientos(excel_inventado.generar_excel())

    primero = importacion.importar(conn, filas).conteos
    assert primero.confirmados == 2 and primero.agregados == 61 and primero.preguntas == 0
    assert movimiento(conn, compra)["estado"] == "confirmado"
    assert movimiento(conn, nequi)["referencia"] == "*0001"
    antes, saldo_antes = foto(conn), componer_saldo(conn).saldo_actual()

    segundo = importacion.importar(conn, filas).conteos
    assert foto(conn) == antes and componer_saldo(conn).saldo_actual() == saldo_antes
    assert (segundo.ya_estaban, segundo.agregados, segundo.confirmados, segundo.no_en_banco) == (63, 0, 0, 0)
    assert [f[0] for f in sql(conn, "SELECT COUNT(*) FROM importaciones")] == [2]


def test_el_saldo_queda_con_todo_lo_del_banco_una_sola_vez(conn):
    del_correo(conn, 25, "compra", 3150000, "RESTAURANTE EJEMPLO")
    importacion.importar(conn, leer_excel_movimientos(excel_inventado.generar_excel()))
    assert componer_saldo(conn).saldo_actual() == SALDO_INICIAL + excel_inventado.TOTAL_CENTAVOS
    gasto = componer_saldo(conn).gasto_entre(datetime(2026, 8, 1), datetime(2026, 9, 1))
    assert gasto == -excel_inventado.GASTOS_CENTAVOS  # Transmilenio incluido, sin duplicar


def test_cobro_acumulado_entra_una_vez_por_dia(conn):
    filas = [fila(5, -1065000, "COBRO VIAJE TRANSPORTE MASIVO"), fila(6, -1065000, "COBRO VIAJE TRANSPORTE MASIVO")]
    importacion.importar(conn, filas)
    importacion.importar(conn, filas)
    assert [tuple(f) for f in sql(conn, "SELECT substr(fecha_hora, 1, 10), monto_centavos, tipo, origen, estado "
                                        "FROM movimientos ORDER BY id")] == [
        ("2026-08-05", 1065000, "compra", "extracto", "sin_aviso"),
        ("2026-08-06", 1065000, "compra", "extracto", "sin_aviso"),
    ]


def test_cruce_de_dias_confirma_todos_los_avisos_sin_duplicar(conn):
    ayer = del_correo(conn, 9, "transferencia", 620000, "*3000000001")
    hoy = del_correo(conn, 10, "transferencia", 620000, "*3000000001")
    filas = [fila(10, -620000, referencia="*0001"), fila(11, -620000, referencia="*0001")]
    antes = componer_saldo(conn).saldo_actual()
    resumen = importacion.importar(conn, filas).conteos
    assert (resumen.confirmados, resumen.agregados) == (2, 0)
    assert movimiento(conn, ayer)["fecha_banco"] == "2026-08-10"
    assert movimiento(conn, hoy)["fecha_banco"] == "2026-08-11"
    assert componer_saldo(conn).saldo_actual() == antes
    guardado = foto(conn)
    importacion.importar(conn, filas)
    assert foto(conn) == guardado


@pytest.mark.parametrize("con_pregunta", [False, True])
def test_reportes_solapados_distinguen_destinos_del_mismo_dia_y_monto(conn, con_pregunta):
    if con_pregunta:
        ajuste_el_dia(conn, 10, -1240000)
    primera = fila(10, -620000, referencia="*0001")
    segunda = fila(10, -620000, referencia="*0002")
    importacion.importar(conn, [primera])
    resumen = importacion.importar(conn, [segunda]).conteos
    assert (resumen.ya_estaban, resumen.ya_preguntadas) == (0, 0)
    assert (resumen.agregados, resumen.preguntas) == ((0, 1) if con_pregunta else (1, 0))
    if con_pregunta:
        assert {p["referencia"] for p in importacion.preguntas_pendientes(conn)} == {"*0001", "*0002"}
    else:
        assert componer_saldo(conn).saldo_actual() == SALDO_INICIAL - 1240000
    guardado = foto(conn)
    resumen = importacion.importar(conn, [segunda, primera]).conteos
    assert foto(conn) == guardado
    assert resumen.ya_estaban + resumen.ya_preguntadas == 2


# --- El saldo cuadrado sigue igual -----------------------------------------------------------

def test_saldo_cuadrado_antes_de_importar_sigue_igual_despues(conn):
    del_correo(conn, 5, "compra", 2590000)
    real = SALDO_INICIAL - 2590000 - 1065000 - 4000  # falta Transmilenio y el 4x1000
    componer_saldo(conn).ajustar_saldo(real)  # el ajuste es de hoy: todo agosto es anterior
    assert componer_saldo(conn).saldo_actual() == real

    resumen = importacion.importar(conn, [fila(5, -2590000), fila(6, -1065000, "COBRO VIAJE TRANSPORTE MASIVO"),
                                          fila(7, -4000, "IMPTO GOBIERNO 4X1000")]).conteos
    assert (resumen.confirmados, resumen.agregados, resumen.ajuste_reducido) == (1, 2, True)
    assert componer_saldo(conn).saldo_actual() == real
    [ajuste] = sql(conn, "SELECT monto_centavos FROM movimientos WHERE tipo = 'ajuste'")
    assert ajuste[0] == 0  # quedó en 0 y no se borró (D45)


def test_solo_se_reduce_el_ultimo_ajuste(conn):
    viejo = ajuste_el_dia(conn, 10, -7000)
    ultimo = ajuste_el_dia(conn, 20, -5000)
    importacion.importar(conn, [fila(15, -3000, "CUOTA MANEJO")])
    assert movimiento(conn, viejo)["monto_centavos"] == -7000
    assert movimiento(conn, ultimo)["monto_centavos"] == -2000


def test_lo_posterior_al_ajuste_mueve_el_saldo(conn):
    ajuste_el_dia(conn, 10, -7000)
    antes = componer_saldo(conn).saldo_actual()
    importacion.importar(conn, [fila(15, -3000, "CUOTA MANEJO")])
    assert componer_saldo(conn).saldo_actual() == antes - 3000


def test_lo_del_mismo_dia_del_ajuste_se_pregunta_y_la_respuesta_decide(conn):
    ajuste = ajuste_el_dia(conn, 20, -5000)
    antes = componer_saldo(conn).saldo_actual()
    resumen = importacion.importar(conn, [fila(20, -3000, "CUOTA MANEJO"), fila(20, -1500, "IMPTO GOBIERNO 4X1000")])
    assert resumen.conteos.preguntas_ajuste == 2 and resumen.conteos.agregados == 0
    assert componer_saldo(conn).saldo_actual() == antes  # lo dudoso no mueve el saldo
    p1, p2 = importacion.preguntas_pendientes(conn)
    assert p1["tipo"] == c.PREGUNTA_YA_ESTABA and p1["candidatos"] == []

    importacion.responder_pregunta(conn, p1["id"], si=True)  # ya estaba: reduce el ajuste
    assert componer_saldo(conn).saldo_actual() == antes and movimiento(conn, ajuste)["monto_centavos"] == -2000
    importacion.responder_pregunta(conn, p2["id"], si=False)  # no estaba: mueve el saldo
    assert componer_saldo(conn).saldo_actual() == antes - 1500
    assert importacion.preguntas_pendientes(conn) == []
    # Reimportar no vuelve a preguntar ni a agregar.
    otra = foto(conn)
    importacion.importar(conn, [fila(20, -3000, "CUOTA MANEJO"), fila(20, -1500, "IMPTO GOBIERNO 4X1000")])
    assert foto(conn) == otra


def test_reimportar_con_preguntas_pendientes_no_las_repite(conn):
    ajuste_el_dia(conn, 20, -5000)
    importacion.importar(conn, [fila(20, -3000)])
    antes = foto(conn)
    resumen = importacion.importar(conn, [fila(20, -3000)]).conteos
    assert foto(conn) == antes and resumen.ya_preguntadas == 1


# --- Ingresos manuales (D39) -----------------------------------------------------------------

def test_ingreso_manual_consignado_e_importado_se_cuenta_una_sola_vez(conn):
    ingreso = componer_saldo(conn).registrar_ingreso(16000000, datetime(2026, 8, 22, 9, 0), "Consignación")
    assert movimiento(conn, ingreso)["estado"] == "provisional"
    antes = componer_saldo(conn).saldo_actual()
    resumen = importacion.importar(conn, [fila(23, 16000000, "TRANSFERENCIA CTA SUC VIRTUAL", "*0002")]).conteos
    assert resumen.confirmados == 1 and resumen.agregados == 0
    assert componer_saldo(conn).saldo_actual() == antes
    assert componer_saldo(conn).ingresos_entre(datetime(2026, 8, 1), datetime(2026, 9, 1)) == 16000000
    assert movimiento(conn, ingreso)["estado"] == "confirmado"


def test_ingreso_manual_que_no_aparece_queda_como_esta(conn):
    ingreso = componer_saldo(conn).registrar_ingreso(5000000, datetime(2026, 8, 10, 9, 0), "")
    importacion.importar(conn, [fila(5, -100), fila(20, -200)])
    m = movimiento(conn, ingreso)
    assert (m["estado"], m["no_en_banco"]) == ("provisional", 0)


# --- Destinos y montos parecidos ---------------------------------------------------------------

def test_transferencias_del_mismo_dia_y_monto_a_destinos_distintos(conn):
    a = del_correo(conn, 4, "transferencia", 620000, "*3000000001")
    b = del_correo(conn, 4, "transferencia", 620000, "*3000000002")
    importacion.importar(conn, [fila(4, -620000, "TRANSFERENCIAS A NEQUI", "*0002"),
                                fila(4, -620000, "TRANSFERENCIAS A NEQUI", "*0001")])
    assert movimiento(conn, a)["referencia"] == "*0001" and movimiento(conn, b)["referencia"] == "*0002"
    assert sql(conn, "SELECT COUNT(*) FROM movimientos")[0][0] == 2


def test_monto_parecido_con_nombre_en_comun_queda_con_el_monto_del_banco(conn):
    m = del_correo(conn, 18, "compra", 950000, "WOMPI EJEMPLO")
    resumen = importacion.importar(conn, [fila(18, -980000, "COMPRA EN  WOMPI EJEMPLO")]).conteos
    assert resumen.corregidos == 1
    assert (movimiento(conn, m)["monto_centavos"], movimiento(conn, m)["estado"]) == (980000, "confirmado")
    [cambio] = sql(conn, "SELECT accion, monto_anterior FROM cambios_importacion")
    assert tuple(cambio) == ("corregido", 950000)


def test_monto_parecido_sin_apoyo_queda_como_pregunta_y_se_responde(conn):
    m = del_correo(conn, 18, "compra", 950000, "SUPERMERCADO INVENTADO")
    antes = componer_saldo(conn).saldo_actual()
    resumen = importacion.importar(conn, [fila(18, -980000, "COMPRA EN  WOMPI EJEMPLO")]).conteos
    assert resumen.preguntas_es_el_mismo == 1 and componer_saldo(conn).saldo_actual() == antes
    assert movimiento(conn, m)["no_en_banco"] == 0
    [p] = importacion.preguntas_pendientes(conn)
    assert p["candidatos"] == [m]
    importacion.responder_pregunta(conn, p["id"], si=True)
    assert movimiento(conn, m)["monto_centavos"] == 980000
    assert componer_saldo(conn).saldo_actual() == antes - 30000


def test_responder_que_no_es_el_mismo_agrega_la_fila(conn):
    m = del_correo(conn, 18, "compra", 950000, "SUPERMERCADO INVENTADO")
    importacion.importar(conn, [fila(18, -980000, "COMPRA EN  WOMPI EJEMPLO")])
    [p] = importacion.preguntas_pendientes(conn)
    antes = componer_saldo(conn).saldo_actual()
    importacion.responder_pregunta(conn, p["id"], si=False)
    assert componer_saldo(conn).saldo_actual() == antes - 980000
    assert movimiento(conn, m)["monto_centavos"] == 950000
    with pytest.raises(importacion.ErrorConciliacion):
        importacion.responder_pregunta(conn, p["id"], si=False)  # ya respondida


def test_con_varios_candidatos_hay_que_elegir(conn):
    a = del_correo(conn, 18, "compra", 950000, "WOMPI EJEMPLO")
    b = del_correo(conn, 18, "compra", 960000, "WOMPI EJEMPLO")
    importacion.importar(conn, [fila(18, -980000, "COMPRA EN  WOMPI EJEMPLO")])
    [p] = importacion.preguntas_pendientes(conn)
    assert p["candidatos"] == [a, b]
    with pytest.raises(importacion.ErrorConciliacion):
        importacion.responder_pregunta(conn, p["id"], si=True)
    importacion.responder_pregunta(conn, p["id"], si=True, movimiento_id=b)
    assert movimiento(conn, b)["monto_centavos"] == 980000 and movimiento(conn, a)["monto_centavos"] == 950000


def test_parecido_del_mismo_dia_del_ajuste_pide_las_dos_respuestas(conn):
    m = del_correo(conn, 20, "compra", 950000, "SUPERMERCADO INVENTADO")
    ajuste = ajuste_el_dia(conn, 20, -5000)
    importacion.importar(conn, [fila(20, -980000, "COMPRA EN  WOMPI EJEMPLO")])
    [p] = importacion.preguntas_pendientes(conn)
    with pytest.raises(importacion.ErrorConciliacion):
        importacion.responder_pregunta(conn, p["id"], si=True)
    antes = componer_saldo(conn).saldo_actual()
    importacion.responder_pregunta(conn, p["id"], si=True, ya_estaba_en_ajuste=True)
    assert componer_saldo(conn).saldo_actual() == antes
    assert movimiento(conn, ajuste)["monto_centavos"] == -5000 + 30000
    assert movimiento(conn, m)["monto_centavos"] == 980000


# --- Lo que el banco no trae -----------------------------------------------------------------

def test_lo_del_correo_que_el_banco_no_trae_queda_marcado_y_no_se_borra(conn):
    falta = del_correo(conn, 10, "compra", 123400, "TIENDA EJEMPLO")
    ids_antes = {f[0] for f in sql(conn, "SELECT id FROM movimientos")}
    resumen = importacion.importar(conn, [fila(5, -100), fila(20, -200)]).conteos
    assert resumen.no_en_banco == 1
    assert movimiento(conn, falta)["no_en_banco"] == 1
    assert ids_antes <= {f[0] for f in sql(conn, "SELECT id FROM movimientos")}
    # Un reporte posterior que sí lo trae lo confirma y quita la marca.
    importacion.importar(conn, [fila(10, -123400)])
    m = movimiento(conn, falta)
    assert (m["no_en_banco"], m["estado"]) == (0, "confirmado")


# --- Fecha de inicio, referencia y base --------------------------------------------------------

def test_filas_anteriores_a_la_fecha_de_inicio_no_se_importan(conn):
    filas = [MovimientoExcel(date(2026, 7, 30), -100, "COMPRA EJEMPLO"), fila(2, -200)]
    resumen = importacion.importar(conn, filas).conteos
    assert (resumen.anteriores, resumen.agregados) == (1, 1)
    assert sql(conn, "SELECT COUNT(*) FROM movimientos")[0][0] == 1


def test_sin_fecha_de_inicio_no_importa_nada(tmp_path):
    conexion = db.conectar(str(tmp_path / "vacia.db"))
    db.inicializar(conexion)
    try:
        with pytest.raises(importacion.SinConfiguracion):
            importacion.importar(conexion, [fila(2, -200)])
        assert sql(conexion, "SELECT COUNT(*) FROM importaciones")[0][0] == 0
    finally:
        conexion.close()


def test_en_la_base_nunca_queda_un_numero_de_referencia_completo(conn):
    filas = leer_excel_movimientos(excel_inventado.generar_excel(
        [(date(2026, 8, 4), "TRANSFERENCIAS A NEQUI", "3000000001", -6200),
         (date(2026, 8, 5), "TRANSFERENCIA CTA SUC VIRTUAL", "00000000002", 1600),
         (date(2026, 8, 6), "PAGO PSE EMPRESA EJEMPLO", "PSE0000003", -500)]))
    importacion.importar(conn, filas)
    texto = repr(db_completa(conn))
    for completo in ("3000000001", "00000000002", "PSE0000003", "0000003"):
        assert completo not in texto
    assert sorted(f[0] or "-" for f in sql(conn, "SELECT referencia FROM movimientos")) == ["*0001", "*0002", "-"]
    assert sql(conn, "SELECT sin_formato FROM importaciones")[0][0] == 1


def test_la_base_rechaza_una_referencia_completa(conn):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaccion(conn):
            sql(conn, "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, origen, estado, referencia, "
                      "fecha_banco) VALUES ('2026-08-04T00:00:00', 1, 'compra', 'extracto', 'sin_aviso', "
                      "'3000000001', '2026-08-04')")


def db_completa(conn) -> dict:
    tablas = [f[0] for f in sql(conn, "SELECT name FROM sqlite_master WHERE type = 'table'")]
    return {t: [tuple(f) for f in sql(conn, f'SELECT * FROM "{t}"')] for t in tablas}


# --- Aviso que llega después de importar (D45) --------------------------------------------------



def test_aviso_que_llega_despues_de_importar_confirma_y_no_duplica(conn):
    importacion.importar(conn, [fila(12, -8735000, "COMPRA EN  SUPERMERCADO INVENTA")])
    antes = componer_saldo(conn).saldo_actual()
    correos = {"tarde": _compra("tarde", "87.350,00", "SUPERMERCADO INVENTADO", 12)}
    sincronizar(conn, ClienteFalso(correos))
    [m] = sql(conn, "SELECT origen, estado, gmail_id, monto_centavos FROM movimientos")
    assert tuple(m) == ("extracto", "confirmado", "tarde", 8735000)
    assert componer_saldo(conn).saldo_actual() == antes
    sincronizar(conn, ClienteFalso(correos))  # sincronizar otra vez tampoco duplica
    assert sql(conn, "SELECT COUNT(*) FROM movimientos")[0][0] == 1


def test_aviso_tardio_dudoso_espera_en_una_pregunta(conn):
    importacion.importar(conn, [fila(12, -9000000, "COMPRA EN  WOMPI EJEMPLO")])
    antes = componer_saldo(conn).saldo_actual()
    correos = {"duda": _compra("duda", "87.350,00", "SUPERMERCADO INVENTADO", 12)}
    sincronizar(conn, ClienteFalso(correos))
    assert sql(conn, "SELECT COUNT(*) FROM movimientos")[0][0] == 1 and componer_saldo(conn).saldo_actual() == antes
    [p] = importacion.preguntas_pendientes(conn)
    assert p["fuente"] == "correo"
    sincronizar(conn, ClienteFalso(correos))  # no se vuelve a descargar ni a preguntar
    assert len(importacion.preguntas_pendientes(conn)) == 1
    importacion.responder_pregunta(conn, p["id"], si=False)
    assert componer_saldo(conn).saldo_actual() == antes - 8735000
    assert sql(conn, "SELECT origen FROM movimientos WHERE gmail_id = 'duda'")[0][0] == "gmail"
    sincronizar(conn, ClienteFalso(correos))
    assert sql(conn, "SELECT COUNT(*) FROM movimientos")[0][0] == 2


def test_aviso_tardio_respondido_que_si_confirma_el_del_banco(conn):
    importacion.importar(conn, [fila(12, -9000000, "COMPRA EN  WOMPI EJEMPLO")])
    sincronizar(conn, ClienteFalso({"duda": _compra("duda", "87.350,00", "SUPERMERCADO INVENTADO", 12)}))
    [p] = importacion.preguntas_pendientes(conn)
    importacion.responder_pregunta(conn, p["id"], si=True)
    [m] = sql(conn, "SELECT origen, estado, gmail_id, monto_centavos FROM movimientos")
    assert tuple(m) == ("extracto", "confirmado", "duda", 9000000)


def test_aviso_sin_nada_del_banco_se_guarda_como_siempre(conn):
    sincronizar(conn, ClienteFalso({"normal": _compra("normal", "87.350,00", "SUPERMERCADO INVENTADO", 12)}))
    [m] = sql(conn, "SELECT origen, estado, gmail_id FROM movimientos")
    assert tuple(m) == ("gmail", None, "normal")


# --- Registro para el "deshacer" del ítem 30 ------------------------------------------------------

def test_cada_cambio_queda_registrado_con_sus_valores_anteriores(conn):
    confirmado = del_correo(conn, 5, "compra", 2590000)
    marcado = del_correo(conn, 10, "compra", 123400)
    ajuste = ajuste_el_dia(conn, 25, -9000)
    resumen = importacion.importar(conn, [fila(5, -2590000), fila(20, -4000, "IMPTO GOBIERNO 4X1000")])
    cambios = {tuple(f) for f in sql(conn, "SELECT movimiento_id, accion, monto_anterior, estado_anterior, "
                                           "no_en_banco_anterior FROM cambios_importacion WHERE importacion_id = ?",
                                     (resumen.importacion_id,))}
    nuevo = sql(conn, "SELECT id FROM movimientos WHERE origen = 'extracto'")[0][0]
    assert cambios == {
        (confirmado, "confirmado", 2590000, None, 0),
        (marcado, "marcado", 123400, None, 0),
        (nuevo, "agregado", None, None, None),
        (ajuste, "ajuste_reducido", -9000, None, 0),
    }
    [imp] = sql(conn, "SELECT desde, hasta, filas, confirmados, agregados, no_en_banco FROM importaciones")
    assert tuple(imp) == ("2026-08-05", "2026-08-20", 2, 1, 1, 1)


# --- Revisión: aviso tardío con preguntas abiertas (no duplicar) --------------------------------

def test_aviso_de_una_fila_que_espera_es_el_mismo_queda_reservado_y_no_duplica(conn):
    """El caso del revisor: la fila espera "¿es el mismo?", llega su aviso y el dueño dice "no"."""
    descartado = del_correo(conn, 18, "compra", 950000, "SUPERMERCADO INVENTADO")
    ancla = primer_dia(conn)
    inicial = componer_saldo(conn).saldo_actual()
    importacion.importar(conn, [ancla, fila(18, -980000, "COMPRA EN  WOMPI EJEMPLO")])
    sincronizar(conn, ClienteFalso({"tarde": _compra("tarde", "9.800,00", "WOMPI EJEMPLO", 18)}))
    aviso = sql(conn, "SELECT id FROM movimientos WHERE gmail_id = 'tarde'")[0][0]
    [p] = importacion.preguntas_pendientes(conn)
    assert aviso in p["candidatos"]
    assert [tuple(f) for f in sql(conn, "SELECT de_aviso FROM candidatos_pregunta WHERE movimiento_id = ?",
                                  (aviso,))] == [(1,)]
    assert componer_saldo(conn).saldo_actual() == inicial - 980000  # el aviso es real; la fila sigue esperando

    importacion.responder_pregunta(conn, p["id"], si=False)
    assert componer_saldo(conn).saldo_actual() == inicial - 980000  # no se agregó la fila otra vez
    m = movimiento(conn, aviso)
    assert (m["estado"], m["fecha_banco"]) == ("confirmado", "2026-08-18")
    # Al reimportar, el del correo que el dueño descartó ya no está reservado
    # y queda marcado "no está en el banco"; nada más cambia, y luego nada.
    importacion.importar(conn, [ancla, fila(18, -980000, "COMPRA EN  WOMPI EJEMPLO")])
    assert movimiento(conn, descartado)["no_en_banco"] == 1
    assert componer_saldo(conn).saldo_actual() == inicial - 980000
    antes = foto(conn)
    importacion.importar(conn, [ancla, fila(18, -980000, "COMPRA EN  WOMPI EJEMPLO")])
    sincronizar(conn, ClienteFalso({"tarde": _compra("tarde", "9.800,00", "WOMPI EJEMPLO", 18)}))
    assert foto(conn) == antes


def test_aviso_reservado_tambien_se_puede_elegir_como_el_mismo(conn):
    del_correo(conn, 18, "compra", 950000, "SUPERMERCADO INVENTADO")
    importacion.importar(conn, [fila(18, -980000, "COMPRA EN  WOMPI EJEMPLO")])
    sincronizar(conn, ClienteFalso({"tarde": _compra("tarde", "9.800,00", "WOMPI EJEMPLO", 18)}))
    aviso = sql(conn, "SELECT id FROM movimientos WHERE gmail_id = 'tarde'")[0][0]
    [p] = importacion.preguntas_pendientes(conn)
    antes = componer_saldo(conn).saldo_actual()
    importacion.responder_pregunta(conn, p["id"], si=True, movimiento_id=aviso)
    assert componer_saldo(conn).saldo_actual() == antes and movimiento(conn, aviso)["estado"] == "confirmado"


def test_aviso_de_una_fila_que_espera_ya_estaba_en_el_ajuste(conn):
    ajuste = ajuste_el_dia(conn, 20, -5000)
    cuadrado = componer_saldo(conn).saldo_actual()
    importacion.importar(conn, [fila(20, -300000, "CUOTA MANEJO")])
    sincronizar(conn, ClienteFalso({"tarde": _compra("tarde", "3.000,00", "CUOTA EJEMPLO", 20)}))
    [p] = importacion.preguntas_pendientes(conn)
    assert p["tipo"] == c.PREGUNTA_YA_ESTABA and len(p["candidatos"]) == 1
    importacion.responder_pregunta(conn, p["id"], si=True)  # ya estaba en el saldo ajustado
    assert componer_saldo(conn).saldo_actual() == cuadrado  # ni la fila ni el aviso lo descuadran
    assert movimiento(conn, ajuste)["monto_centavos"] == -5000 + 300000
    assert sql(conn, "SELECT COUNT(*) FROM movimientos WHERE origen = 'extracto'")[0][0] == 0


def test_aviso_de_una_fila_que_espera_y_no_estaba_en_el_ajuste(conn):
    ajuste_el_dia(conn, 20, -5000)
    cuadrado = componer_saldo(conn).saldo_actual()
    importacion.importar(conn, [fila(20, -300000, "CUOTA MANEJO")])
    sincronizar(conn, ClienteFalso({"tarde": _compra("tarde", "3.000,00", "CUOTA EJEMPLO", 20)}))
    [p] = importacion.preguntas_pendientes(conn)
    importacion.responder_pregunta(conn, p["id"], si=False)
    assert componer_saldo(conn).saldo_actual() == cuadrado - 300000  # una sola vez


def test_aviso_de_una_fila_que_espera_anterior_al_ajuste(conn):
    """El ajuste ya tenía el movimiento real; el aviso llegó después: no se cuenta dos veces."""
    del_correo(conn, 18, "compra", 950000, "SUPERMERCADO INVENTADO")
    componer_saldo(conn).ajustar_saldo(componer_saldo(conn).saldo_actual() - 980000 + 950000 - 980000)
    cuadrado = componer_saldo(conn).saldo_actual()
    importacion.importar(conn, [fila(18, -980000, "COMPRA EN  WOMPI EJEMPLO")])
    sincronizar(conn, ClienteFalso({"tarde": _compra("tarde", "9.800,00", "WOMPI EJEMPLO", 18)}))
    [p] = importacion.preguntas_pendientes(conn)
    importacion.responder_pregunta(conn, p["id"], si=False)
    assert componer_saldo(conn).saldo_actual() == cuadrado


def test_aviso_cuyo_unico_candidato_ya_esta_reservado_se_pregunta(conn):
    # Dos avisos llegan para la misma fila sin aviso: el primero (parecido) la
    # deja en pregunta, reservada, y el segundo (exacto) no entra como nuevo.
    importacion.importar(conn, [fila(12, -9000000, "COMPRA EN  WOMPI EJEMPLO")])
    sincronizar(conn, ClienteFalso({"duda": _compra("duda", "87.350,00", "SUPERMERCADO INVENTADO", 12)}))
    antes = componer_saldo(conn).saldo_actual()
    sincronizar(conn, ClienteFalso({"exacto": _compra("exacto", "90.000,00", "OTRO EJEMPLO", 12)}))
    assert componer_saldo(conn).saldo_actual() == antes
    assert sql(conn, "SELECT COUNT(*) FROM movimientos")[0][0] == 1
    assert [p["fuente"] for p in importacion.preguntas_pendientes(conn)] == ["correo", "correo"]


def test_dos_avisos_iguales_eligen_filas_exacta_y_parecida_sin_duplicar(conn):
    """Un exacto no consume la fila de un aviso indistinguible que llega después."""
    importacion.importar(conn, [fila(3, -100000), fila(3, -98000)])
    cien, noventa_y_ocho = [f[0] for f in sql(conn, "SELECT id FROM movimientos ORDER BY id")]
    saldo_banco = componer_saldo(conn).saldo_actual()
    aviso = MovimientoExtraido("compra", 98000, datetime(2026, 8, 3, 12), "AVISO INVENTADO")

    with db.transaccion(conn, inmediata=True):
        assert importacion.recibir_aviso(conn, "tarde-inventado-1", aviso) == importacion.AVISO_PREGUNTA
        assert importacion.recibir_aviso(conn, "tarde-inventado-2", aviso) == importacion.AVISO_PREGUNTA
    primero, segundo = importacion.preguntas_pendientes(conn)
    assert primero["candidatos"] == [cien, noventa_y_ocho]
    assert segundo["candidatos"] == [cien, noventa_y_ocho]

    importacion.responder_pregunta(conn, primero["id"], si=True, movimiento_id=cien)
    importacion.responder_pregunta(conn, segundo["id"], si=True, movimiento_id=noventa_y_ocho)
    assert [tuple(f) for f in sql(conn, "SELECT gmail_id, monto_centavos, fecha_banco FROM movimientos ORDER BY id")] == [
        ("tarde-inventado-1", 100000, "2026-08-03"),
        ("tarde-inventado-2", 98000, "2026-08-03"),
    ]
    assert componer_saldo(conn).saldo_actual() == saldo_banco
    asentado = foto(conn)
    with db.transaccion(conn, inmediata=True):
        assert importacion.recibir_aviso(conn, "tarde-inventado-1", aviso) == importacion.AVISO_YA_ESTABA
        assert importacion.recibir_aviso(conn, "tarde-inventado-2", aviso) == importacion.AVISO_YA_ESTABA
    importacion.importar(conn, [fila(3, -100000), fila(3, -98000)])
    assert foto(conn) == asentado and componer_saldo(conn).saldo_actual() == saldo_banco


# --- Revisión: un ajuste más nuevo antes de responder ---------------------------------------------

def test_ya_estaba_con_un_ajuste_mas_nuevo_usa_el_ultimo(conn):
    fijo = ajuste_el_dia(conn, 20, -5000)
    importacion.importar(conn, [fila(20, -300000, "CUOTA MANEJO")])
    nuevo = ajuste_el_dia(conn, 25, -1000)  # el dueño cuadró otra vez antes de responder
    cuadrado = componer_saldo(conn).saldo_actual()
    [p] = importacion.preguntas_pendientes(conn)
    importacion.responder_pregunta(conn, p["id"], si=False)
    # La fila es anterior al día del ajuste nuevo: lo reduce, aunque dijera que no.
    assert componer_saldo(conn).saldo_actual() == cuadrado
    assert movimiento(conn, fijo)["monto_centavos"] == -5000
    assert movimiento(conn, nuevo)["monto_centavos"] == -1000 + 300000


def test_ya_estaba_sin_ajuste_mas_nuevo_usa_el_de_la_pregunta(conn):
    fijo = ajuste_el_dia(conn, 20, -5000)
    importacion.importar(conn, [fila(20, -300000, "CUOTA MANEJO")])
    [p] = importacion.preguntas_pendientes(conn)
    importacion.responder_pregunta(conn, p["id"], si=True)
    assert movimiento(conn, fijo)["monto_centavos"] == -5000 + 300000


# --- Revisión: borrar o restaurar un ingreso ya conciliado ------------------------------------------

def test_no_se_borra_un_ingreso_que_ya_confirmo_el_banco(conn):
    ingreso = componer_saldo(conn).registrar_ingreso(5000000, datetime(2026, 8, 10, 9, 0), "")
    importacion.importar(conn, [fila(10, 5000000, "ABONO EJEMPLO")])
    with pytest.raises(saldo_contratos.BorradoNoPermitido, match="reporte del banco"):
        componer_saldo(conn).borrar_ingreso(ingreso)
    with pytest.raises(saldo_contratos.BorradoNoPermitido, match="reporte del banco"):
        componer_saldo(conn).borrar_ingreso_con_copia(ingreso)
    filas = componer_saldo(conn).ingresos_y_ajustes_entre(datetime(2026, 8, 1), datetime(2026, 9, 1))
    assert [f["se_puede_borrar"] for f in filas] == [False]


def test_no_se_borra_un_ingreso_que_es_candidato_de_una_pregunta(conn):
    ingreso = componer_saldo(conn).registrar_ingreso(5000000, datetime(2026, 8, 10, 9, 0), "")
    importacion.importar(conn, [fila(10, 5100000, "TRANSFERENCIA CTA SUC VIRTUAL")])
    assert importacion.preguntas_pendientes(conn)[0]["candidatos"] == [ingreso]
    with pytest.raises(saldo_contratos.BorradoNoPermitido, match="pregunta"):
        componer_saldo(conn).borrar_ingreso(ingreso)


def test_un_ingreso_sin_conciliar_se_sigue_borrando_y_restaurando(conn):
    ingreso = componer_saldo(conn).registrar_ingreso(5000000, datetime(2026, 8, 10, 9, 0), "")
    copia, _ = componer_saldo(conn).borrar_ingreso_con_copia(ingreso)
    nuevo_id, _ = componer_saldo(conn).restaurar_ingreso(copia)
    assert movimiento(conn, nuevo_id)["estado"] == "provisional"


def test_no_se_restaura_un_ingreso_si_se_importo_despues_de_borrarlo(conn):
    ingreso = componer_saldo(conn).registrar_ingreso(5000000, datetime(2026, 8, 10, 9, 0), "")
    copia, _ = componer_saldo(conn).borrar_ingreso_con_copia(ingreso)
    importacion.importar(conn, [fila(10, 5000000, "ABONO EJEMPLO")])  # entró sin aviso
    antes = componer_saldo(conn).saldo_actual()
    with pytest.raises(saldo_contratos.RestauracionNoPermitida, match="importaste"):
        componer_saldo(conn).restaurar_ingreso(copia)
    assert componer_saldo(conn).saldo_actual() == antes


def test_ya_estaba_prefiere_el_aviso_exacto_al_parecido_del_motor(conn):
    """El motor propuso corregir un parecido; llega el aviso con el monto exacto: gana el aviso."""
    parecido = del_correo(conn, 20, "compra", 100000, "TIENDA EJEMPLO")
    ajuste_el_dia(conn, 20, -5000)
    importacion.importar(conn, [fila(20, -101000, "COMPRA EN  TIENDA EJEMPLO")])
    [p] = importacion.preguntas_pendientes(conn)
    assert p["tipo"] == c.PREGUNTA_YA_ESTABA and p["candidatos"] == [parecido]
    sincronizar(conn, ClienteFalso({"tarde": _compra("tarde", "1.010,00", "TIENDA EJEMPLO", 20)}))
    antes = componer_saldo(conn).saldo_actual()
    importacion.responder_pregunta(conn, p["id"], si=False)
    aviso = sql(conn, "SELECT id FROM movimientos WHERE gmail_id = 'tarde'")[0][0]
    assert movimiento(conn, aviso)["estado"] == "confirmado"
    assert movimiento(conn, parecido)["monto_centavos"] == 100000 and movimiento(conn, parecido)["estado"] is None
    assert componer_saldo(conn).saldo_actual() == antes  # el aviso ya contaba; no se agrega nada


def test_ya_estaba_que_si_con_el_aviso_exacto_reduce_el_ajuste_con_la_fila_completa(conn):
    """Variante "sí": el aviso llegó después del ajuste, que ya tenía el cobro real."""
    parecido = del_correo(conn, 20, "compra", 100000, "TIENDA EJEMPLO")
    ajuste = ajuste_el_dia(conn, 20, -5000)
    cuadrado = componer_saldo(conn).saldo_actual()
    importacion.importar(conn, [fila(20, -101000, "COMPRA EN  TIENDA EJEMPLO")])
    [p] = importacion.preguntas_pendientes(conn)
    sincronizar(conn, ClienteFalso({"tarde": _compra("tarde", "1.010,00", "TIENDA EJEMPLO", 20)}))
    importacion.responder_pregunta(conn, p["id"], si=True)
    aviso = sql(conn, "SELECT id FROM movimientos WHERE gmail_id = 'tarde'")[0][0]
    assert movimiento(conn, aviso)["estado"] == "confirmado"
    assert movimiento(conn, parecido)["monto_centavos"] == 100000
    assert movimiento(conn, ajuste)["monto_centavos"] == -5000 + 101000
    assert componer_saldo(conn).saldo_actual() == cuadrado


def test_aviso_exacto_con_las_filas_reservadas_puede_elegir_cualquiera_libre(conn):
    """Un aviso parecido reserva dos filas iguales; el exacto de la otra no queda sin salida."""
    importacion.importar(conn, [fila(12, -102000, "COMPRA EN  TIENDA EJEMPLO"),
                                fila(12, -102000, "COMPRA EN  TIENDA EJEMPLO")])
    e1, e2 = [f[0] for f in sql(conn, "SELECT id FROM movimientos ORDER BY id")]
    sincronizar(conn, ClienteFalso({"parecido": _compra("parecido", "1.009,80", "AVISO INVENTADO", 12)}))
    sincronizar(conn, ClienteFalso({"exacto": _compra("exacto", "1.020,00", "AVISO INVENTADO", 12)}))
    p1, p2 = importacion.preguntas_pendientes(conn)
    assert p1["candidatos"] == [e1, e2] and p2["candidatos"] == [e1, e2]
    antes = componer_saldo(conn).saldo_actual()
    importacion.responder_pregunta(conn, p1["id"], si=True, movimiento_id=e1)
    importacion.responder_pregunta(conn, p2["id"], si=True, movimiento_id=e2)
    assert componer_saldo(conn).saldo_actual() == antes
    assert sql(conn, "SELECT COUNT(*) FROM movimientos")[0][0] == 2


def test_dos_filas_iguales_que_esperan_y_sus_dos_avisos_quedan_una_con_cada_uno(conn):
    ajuste_el_dia(conn, 2, -1000)
    cuadrado = componer_saldo(conn).saldo_actual()
    importacion.importar(conn, [fila(2, -102000, "COMPRA EN  TIENDA EJEMPLO"),
                                fila(2, -102000, "COMPRA EN  TIENDA EJEMPLO")])
    sincronizar(conn, ClienteFalso({"a1": _compra("a1", "1.020,00", "AVISO INVENTADO", 2),
                                    "a2": _compra("a2", "1.020,00", "AVISO INVENTADO", 2)}))
    p1, p2 = importacion.preguntas_pendientes(conn)
    assert len(p1["candidatos"]) == len(p2["candidatos"]) == 1 and p1["candidatos"] != p2["candidatos"]
    importacion.responder_pregunta(conn, p1["id"], si=False)
    importacion.responder_pregunta(conn, p2["id"], si=False)
    assert componer_saldo(conn).saldo_actual() == cuadrado - 2 * 102000  # dos cobros reales, cada uno una vez
    assert sql(conn, "SELECT COUNT(*) FROM movimientos WHERE tipo <> 'ajuste'")[0][0] == 2


def test_no_a_una_fila_deja_el_aviso_que_solo_se_le_parece_para_la_suya(conn):
    """Ítem 44: el aviso exacto de una fila que espera también es un parecido sin
    apoyo de otra del mismo día, y queda reservado en las dos. "No" a la otra la
    agrega sin aviso (antes exigía elegir y no había "son distintos")."""
    del_correo(conn, 1, "compra", 355000)
    cuadrado = componer_saldo(conn).saldo_actual()
    importacion.importar(conn, [fila(1, -358550), fila(1, -344350)])
    sincronizar(conn, ClienteFalso({"a1": _compra("a1", "3.443,50", "AVISO INVENTADO", 1)}))
    aviso = sql(conn, "SELECT id FROM movimientos WHERE gmail_id = 'a1'")[0][0]
    parecida, exacta = importacion.preguntas_pendientes(conn)
    assert aviso in parecida["candidatos"] and aviso in exacta["candidatos"]

    importacion.responder_pregunta(conn, parecida["id"], si=False)
    assert movimiento(conn, aviso)["fecha_banco"] is None  # sigue esperando a su fila
    importacion.responder_pregunta(conn, exacta["id"], si=False)
    assert movimiento(conn, aviso)["estado"] == "confirmado"
    assert movimiento(conn, aviso)["monto_centavos"] == 344350
    # El correo de $3.550 queda como estaba y cada cobro del banco entra una vez.
    assert componer_saldo(conn).saldo_actual() == cuadrado - 358550 - 344350
    saldo = componer_saldo(conn).saldo_actual()
    importacion.importar(conn, [fila(1, -358550), fila(1, -344350)])  # solo marca el correo sin fila
    antes = foto(conn)
    otra = importacion.importar(conn, [fila(1, -358550), fila(1, -344350)]).conteos
    assert foto(conn) == antes and componer_saldo(conn).saldo_actual() == saldo
    assert otra.ya_estaban == 2 and otra.agregados == otra.confirmados == otra.preguntas == 0


def _aviso_tarde(conn, gmail_id, monto, dia, esperado):
    with db.transaccion(conn, inmediata=True):
        aviso = MovimientoExtraido("compra", monto, datetime(2026, 8, dia, 12), "AVISO INVENTADO")
        assert importacion.recibir_aviso(conn, gmail_id, aviso) == esperado


def test_no_a_la_pregunta_del_aviso_confirma_la_fila_que_entro_mientras_esperaba(conn):
    """Ítem 44: el aviso exacto de una fila que espera es parecido, sin apoyo, de
    otra que entró sin aviso, y espera en "¿es el mismo?". La fila que espera se
    responde primero ("no": entra sin aviso) y luego "no" al aviso: lo confirma."""
    del_correo(conn, 1, "transferencia", 950000, "*3000000001")
    importacion.importar(conn, [fila(1, -1009400), fila(1, -969000)])
    _aviso_tarde(conn, "tarde-inventado-1", 969000, 1, importacion.AVISO_PREGUNTA)
    de_la_fila, del_aviso = importacion.preguntas_pendientes(conn)
    assert del_aviso["fuente"] == "correo"
    importacion.responder_pregunta(conn, de_la_fila["id"], si=False)
    saldo = componer_saldo(conn).saldo_actual()
    importacion.responder_pregunta(conn, del_aviso["id"], si=False)
    [confirmado] = sql(conn, "SELECT id FROM movimientos WHERE gmail_id = 'tarde-inventado-1'")
    assert movimiento(conn, confirmado[0])["origen"] == "extracto"
    assert movimiento(conn, confirmado[0])["estado"] == "confirmado"
    assert componer_saldo(conn).saldo_actual() == saldo  # el aviso no se suma otra vez


def test_el_aviso_que_sobra_de_dos_filas_iguales_queda_para_la_otra(conn):
    """Ítem 44: dos cobros iguales del día del ajuste y sus dos avisos (uno
    parecido). Si el dueño usa el parecido para la primera, el exacto queda para
    la segunda en vez de quedar suelto mientras ella entra aparte."""
    ajuste_el_dia(conn, 4, -1000)
    cuadrado = componer_saldo(conn).saldo_actual()
    filas = [fila(4, -355000), fila(4, -355000)]
    importacion.importar(conn, filas)
    _aviso_tarde(conn, "tarde-inventado-1", 351450, 4, importacion.AVISO_EN_PREGUNTA)
    _aviso_tarde(conn, "tarde-inventado-2", 355000, 4, importacion.AVISO_EN_PREGUNTA)
    parecido, exacto = (sql(conn, "SELECT id FROM movimientos WHERE gmail_id = ?", (g,))[0][0]
                        for g in ("tarde-inventado-1", "tarde-inventado-2"))
    p1, p2 = importacion.preguntas_pendientes(conn)
    importacion.responder_pregunta(conn, p1["id"], si=False, movimiento_id=parecido)
    assert exacto in importacion.preguntas_pendientes(conn)[0]["candidatos"]
    importacion.responder_pregunta(conn, p2["id"], si=False)
    assert movimiento(conn, parecido)["estado"] == movimiento(conn, exacto)["estado"] == "confirmado"
    assert sql(conn, "SELECT COUNT(*) FROM movimientos WHERE tipo <> 'ajuste'")[0][0] == 2
    assert componer_saldo(conn).saldo_actual() == cuadrado - 2 * 355000
    antes = foto(conn)
    importacion.importar(conn, filas)
    assert foto(conn) == antes


def _ingreso_tarde(conn, gmail_id, monto, dia):
    with db.transaccion(conn, inmediata=True):
        aviso = MovimientoExtraido("ingreso", monto, datetime(2026, 8, dia, 12), "AVISO INVENTADO")
        return importacion.recibir_aviso(conn, gmail_id, aviso)


def test_el_aviso_ve_tambien_la_fila_reservada_y_elegirla_la_quita_de_la_otra_pregunta(conn):
    """Ítem 45, caso C (D50): la fila de $9.996 es candidata (dudosa) del primer
    aviso; el segundo aviso, parecido a ella, la ve igual. Al elegirla, la
    pregunta del primer aviso deja de ofrecerla: nunca dos avisos en una fila."""
    importacion.importar(conn, [fila(19, 950600), fila(19, 999600), fila(19, 1065000)])
    exacta, parecida, otra = (sql(conn, "SELECT id FROM movimientos WHERE monto_centavos = ?", (m,))[0][0]
                              for m in (950600, 999600, 1065000))
    saldo = componer_saldo(conn).saldo_actual()
    assert _ingreso_tarde(conn, "tarde-inventado-1", 950600, 19) == importacion.AVISO_PREGUNTA
    assert _ingreso_tarde(conn, "tarde-inventado-2", 1019592, 19) == importacion.AVISO_PREGUNTA
    primera, segunda = importacion.preguntas_pendientes(conn)
    assert primera["candidatos"] == [exacta, parecida]
    assert segunda["candidatos"] == [parecida, otra]  # antes: solo [otra]

    importacion.responder_pregunta(conn, segunda["id"], si=True, movimiento_id=parecida)
    [primera] = importacion.preguntas_pendientes(conn)
    assert primera["candidatos"] == [exacta]
    with pytest.raises(importacion.ErrorConciliacion):
        importacion.responder_pregunta(conn, primera["id"], si=True, movimiento_id=parecida)
    importacion.responder_pregunta(conn, primera["id"], si=True, movimiento_id=exacta)
    assert movimiento(conn, parecida)["gmail_id"] == "tarde-inventado-2"
    assert movimiento(conn, exacta)["gmail_id"] == "tarde-inventado-1"
    assert componer_saldo(conn).saldo_actual() == saldo
    assert sql(conn, "SELECT COUNT(*) FROM movimientos")[0][0] == 3


def test_no_que_deja_otro_candidato_dudoso_vuelve_a_preguntar(conn):
    """Ítem 45, caso D (D50): el aviso de $9.593,10 espera en "¿es el mismo?" con
    la fila de $10.094. Su fila ($9.690) espera su propia pregunta; el dueño le
    dice "no" (entra sin aviso) y después "no" al aviso: en vez de guardarlo
    como nuevo, se le vuelve a preguntar con la fila de $9.690."""
    del_correo(conn, 1, "transferencia", 950000, "*3000000001")
    importacion.importar(conn, [fila(1, -1009400), fila(1, -969000)])
    _aviso_tarde(conn, "tarde-inventado-1", 959310, 1, importacion.AVISO_PREGUNTA)
    de_la_fila, del_aviso = importacion.preguntas_pendientes(conn)
    importacion.responder_pregunta(conn, de_la_fila["id"], si=False)
    [agregada] = sql(conn, "SELECT id FROM movimientos WHERE monto_centavos = 969000")
    saldo = componer_saldo(conn).saldo_actual()

    importacion.responder_pregunta(conn, del_aviso["id"], si=False)
    [otra_vez] = importacion.preguntas_pendientes(conn)
    # La misma pregunta, con lo ya rechazado (historial) y la fila nueva.
    assert otra_vez["id"] == del_aviso["id"] and otra_vez["candidatos"] == del_aviso["candidatos"] + [agregada[0]]
    assert not sql(conn, "SELECT 1 FROM movimientos WHERE gmail_id = 'tarde-inventado-1'")
    assert componer_saldo(conn).saldo_actual() == saldo

    importacion.responder_pregunta(conn, del_aviso["id"], si=True, movimiento_id=agregada[0])
    assert movimiento(conn, agregada[0])["gmail_id"] == "tarde-inventado-1"
    assert componer_saldo(conn).saldo_actual() == saldo  # el aviso no se suma otra vez
    assert not importacion.preguntas_pendientes(conn)


def test_lo_ya_rechazado_nunca_se_empareja_solo_al_volver_a_preguntar(conn):
    """Ítem 45, caso D (revisión): A=$10.000 y X=$10.300 son candidatas de los
    avisos G1 ($10.000) y G2 ($10.300). Entra C=$9.800; "no" a G1 vuelve a
    preguntar sin olvidar A y X; G2 se queda con X; otro "no" a G1 no empareja
    sola la fila A, que el dueño ya rechazó (D38)."""
    importacion.importar(conn, [fila(10, -1000000), fila(10, -1030000)])
    [a] = sql(conn, "SELECT id FROM movimientos WHERE monto_centavos = 1000000")
    [x] = sql(conn, "SELECT id FROM movimientos WHERE monto_centavos = 1030000")
    _aviso_tarde(conn, "g1", 1000000, 10, importacion.AVISO_PREGUNTA)
    _aviso_tarde(conn, "g2", 1030000, 10, importacion.AVISO_PREGUNTA)
    g1, g2 = importacion.preguntas_pendientes(conn)
    importacion.importar(conn, [fila(10, -980000)])
    [fila_c] = sql(conn, "SELECT id FROM preguntas_conciliacion WHERE fuente = 'banco'")
    importacion.responder_pregunta(conn, fila_c[0], si=False)
    [c] = sql(conn, "SELECT id FROM movimientos WHERE monto_centavos = 980000")
    importacion.responder_pregunta(conn, g1["id"], si=False)
    assert importacion.preguntas_pendientes(conn)[0]["candidatos"] == sorted([a[0], x[0], c[0]])
    importacion.responder_pregunta(conn, g2["id"], si=True, movimiento_id=x[0])
    assert importacion.preguntas_pendientes(conn)[0]["candidatos"] == sorted([a[0], c[0]])
    importacion.responder_pregunta(conn, g1["id"], si=False)
    assert movimiento(conn, a[0])["gmail_id"] is None and movimiento(conn, c[0])["gmail_id"] is None
    assert not importacion.preguntas_pendientes(conn)
    [guardado] = sql(conn, "SELECT origen FROM movimientos WHERE gmail_id = 'g1'")
    assert guardado[0] == "gmail"


def test_la_pregunta_que_se_queda_sin_candidatos_los_recalcula(conn):
    """Ítem 45, caso C (revisión): si otro aviso toma la única fila de una
    pregunta, sus candidatos se recalculan con las reglas de llegada."""
    importacion.importar(conn, [fila(10, -10300)])
    [x] = sql(conn, "SELECT id FROM movimientos WHERE monto_centavos = 10300")
    _aviso_tarde(conn, "g1", 10000, 10, importacion.AVISO_PREGUNTA)
    _aviso_tarde(conn, "g2", 10200, 10, importacion.AVISO_PREGUNTA)
    g1, g2 = importacion.preguntas_pendientes(conn)
    assert g1["candidatos"] == g2["candidatos"] == [x[0]]
    importacion.importar(conn, [fila(11, -10200)])  # otro reporte
    [y] = sql(conn, "SELECT id FROM movimientos WHERE monto_centavos = 10200")
    importacion.responder_pregunta(conn, g1["id"], si=True, movimiento_id=x[0])
    [g2] = importacion.preguntas_pendientes(conn)
    assert g2["candidatos"] == [y[0]]
    assert movimiento(conn, y[0])["gmail_id"] is None  # solo se propone


def test_el_resumen_avisa_cuando_se_vuelve_a_preguntar(conn):
    del_correo(conn, 1, "transferencia", 950000, "*3000000001")
    importacion.importar(conn, [fila(1, -1009400), fila(1, -969000)])
    _aviso_tarde(conn, "tarde-inventado-1", 959310, 1, importacion.AVISO_PREGUNTA)
    de_la_fila, del_aviso = importacion.preguntas_pendientes(conn)
    gestion_importaciones.responder(conn, [(de_la_fila["id"], "no")])
    resultado, _ = gestion_importaciones.responder(conn, [(del_aviso["id"], "no")])
    assert resultado["resumen"] == "Hay otro movimiento que podría ser ese aviso: te lo preguntamos de nuevo."
    assert [p["id"] for p in importacion.preguntas_pendientes(conn)] == [del_aviso["id"]]


def test_no_otra_vez_al_aviso_lo_guarda_sin_repetir_la_pregunta(conn):
    """Ítem 45, caso D: tras volver a preguntar, un segundo "no" no ofrece de nuevo
    lo ya descartado; el aviso se guarda como nuevo."""
    del_correo(conn, 1, "transferencia", 950000, "*3000000001")
    importacion.importar(conn, [fila(1, -1009400), fila(1, -969000)])
    _aviso_tarde(conn, "tarde-inventado-1", 959310, 1, importacion.AVISO_PREGUNTA)
    de_la_fila, del_aviso = importacion.preguntas_pendientes(conn)
    importacion.responder_pregunta(conn, de_la_fila["id"], si=False)
    importacion.responder_pregunta(conn, del_aviso["id"], si=False)
    importacion.responder_pregunta(conn, del_aviso["id"], si=False)
    assert not importacion.preguntas_pendientes(conn)
    [guardado] = sql(conn, "SELECT origen, fecha_banco FROM movimientos WHERE gmail_id = 'tarde-inventado-1'")
    assert tuple(guardado) == ("gmail", None)


@pytest.mark.parametrize("eleccion", ["aviso", "ninguno"])
@pytest.mark.parametrize("montos", [(9500,), (9500, 10200)])
def test_respuesta_del_ajuste_no_elige_un_aviso_parecido_sin_confirmacion(conn, montos, eleccion):
    ajuste_el_dia(conn, 20, -10000)
    importacion.importar(conn, [fila(20, -10000, "COBRO BANCO")])
    [pregunta] = importacion.preguntas_pendientes(conn)
    avisos = []
    for i, monto in enumerate(montos):
        with db.transaccion(conn, inmediata=True):
            aviso = MovimientoExtraido("compra", monto, datetime(2026, 8, 20, 11 + i), "AVISO INVENTADO")
            assert importacion.recibir_aviso(conn, f"tarde-inventado-{i}", aviso) == importacion.AVISO_EN_PREGUNTA
        avisos.append(sql(conn, "SELECT id FROM movimientos WHERE gmail_id = ?", (f"tarde-inventado-{i}",))[0][0])
    antes, balance = foto(conn), componer_saldo(conn).saldo_actual()
    with pytest.raises(importacion.ErrorConciliacion, match=importacion.MENSAJE_CANDIDATO):
        importacion.responder_pregunta(conn, pregunta["id"], si=False)
    assert foto(conn) == antes and componer_saldo(conn).saldo_actual() == balance
    # La pantalla ofrece "ninguno de estos" en vez de elegir sola (D50, caso B).
    opciones = {o["id"]: o["texto"] for o in gestion_importaciones.preguntas(conn)["preguntas"][0]["opciones"]}
    assert opciones["no:ninguno"] == "No estaba en mi saldo: no es ninguno de estos avisos"
    assert opciones["si:ninguno"] == "Ya estaba en mi saldo: no es ninguno de estos avisos"
    assert "no" not in opciones and "si" not in opciones
    if eleccion == "aviso":
        importacion.responder_pregunta(conn, pregunta["id"], si=False, movimiento_id=avisos[-1])
        assert movimiento(conn, avisos[-1])["estado"] == "confirmado"
        assert movimiento(conn, avisos[-1])["monto_centavos"] == 10000
        return
    importacion.responder_pregunta(conn, pregunta["id"], si=False, ninguno=True)
    # La fila entra sola y los avisos siguen esperando, sin emparejarse.
    assert all(movimiento(conn, a)["fecha_banco"] is None for a in avisos)
    assert sql(conn, "SELECT COUNT(*) FROM movimientos WHERE origen = 'extracto'")[0][0] == 1
    assert componer_saldo(conn).saldo_actual() == balance - 10000


def test_correccion_conserva_categoria_elegida_a_mano(conn):
    ident = del_correo(conn, 10, "compra", 100000, "TIENDA EJEMPLO")
    categoria = sql(conn, "SELECT id FROM categorias ORDER BY id LIMIT 1")[0][0]
    with db.transaccion(conn):
        sql(conn, "UPDATE movimientos SET categoria_id = ?, origen_categoria = 'manual' WHERE id = ?",
            (categoria, ident))
    importacion.importar(conn, [fila(10, -102000, "COMPRA TIENDA EJEMPLO")])
    actual = movimiento(conn, ident)
    assert (actual["categoria_id"], actual["origen_categoria"], actual["monto_centavos"], actual["estado"]) == (
        categoria, "manual", 102000, "confirmado")


def test_fallo_intermedio_revierte_movimientos_saldo_y_registro(conn):
    del_correo(conn, 10, "compra", 100000)
    with db.transaccion(conn):
        sql(conn, "CREATE TRIGGER fallo_inventado BEFORE INSERT ON cambios_importacion "
                  "BEGIN SELECT RAISE(ABORT, 'fallo inventado'); END")
    antes, balance = foto(conn), componer_saldo(conn).saldo_actual()
    with pytest.raises(IntegrityError, match="fallo inventado"):
        importacion.importar(conn, [fila(10, -100000), fila(11, -200000)])
    assert foto(conn) == antes and componer_saldo(conn).saldo_actual() == balance
    assert sql(conn, "SELECT COUNT(*) FROM importaciones")[0][0] == 0


@pytest.mark.parametrize("cantidad", [50, 120, 146])
def test_el_dia_mas_antiguo_del_reporte_nunca_marca_no_esta_en_el_banco(conn, cantidad):
    """D51 (ítem 46): con reportes de cualquier tamaño, lo del correo del día más
    antiguo no se marca (puede venir incompleto); lo de los demás días sí."""
    del_primer_dia = del_correo(conn, 3, "compra", 777700)
    del_medio = del_correo(conn, 10, "compra", 777700)
    del_ultimo = del_correo(conn, 20, "compra", 777700)
    reporte = [fila(3, -100)] + [fila(4 + i % 17, -(i + 200)) for i in range(cantidad - 1)]
    assert len(reporte) == cantidad and max(f.fecha for f in reporte).day == 20
    r = importacion.importar(conn, reporte).conteos
    assert r.no_en_banco == 2
    assert movimiento(conn, del_primer_dia)["no_en_banco"] == 0
    assert movimiento(conn, del_medio)["no_en_banco"] == 1
    assert movimiento(conn, del_ultimo)["no_en_banco"] == 1
    antes = foto(conn)
    importacion.importar(conn, reporte)
    assert foto(conn) == antes
    # Otro reporte que empieza antes sí puede marcar ese día.
    otro = [fila(2, -100), fila(3, -100)]
    importacion.importar(conn, otro)
    assert movimiento(conn, del_primer_dia)["no_en_banco"] == 1
