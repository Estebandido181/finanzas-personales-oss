"""Arranque31 atómico: mismo cálculo guardado, historia y configuración reversibles."""
from finanzas.bootstrap.saldo import componer_saldo
from datetime import date, datetime
import pytest
from sqlalchemy import text
from hypothesis import given, settings, HealthCheck, strategies as st
from finanzas import db, gestion_importaciones as g, sincronizacion
from finanzas.flujos import historial as a
from finanzas.bootstrap.arranque import componer_arranque, preparar_avisos
from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import MovimientoExcel
from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import MovimientoExtraido


@pytest.fixture
def conn(tmp_path):
    c = db.conectar(str(tmp_path / "arranque-inventado.db"))
    db.inicializar(c)
    yield c
    c.close()


def fila(dia=10, monto=-500, desc="TIENDA INVENTADA"):
    return MovimientoExcel(date(2026, 7, dia), monto, desc)


def aviso(dia=10, monto=500, ident="aviso-inventado"):
    return a.AvisoNormalizado(ident, MovimientoExtraido("compra", monto, datetime(2026, 7, dia, 12), "TIENDA INVENTADA"))


def test_arranque_previo_no_configura_y_confirmar_guarda_mismo_saldo(conn):
    antes = g.huella(conn)
    analisis = componer_arranque(conn).analizar([[fila(), fila(11, 1000)], [fila()]], 100000, modo="arranque", avisos=[aviso()])
    assert analisis.vista["saldo_inicial_centavos"] == 99500
    assert analisis.vista["saldo_despues_centavos"] == 100000
    assert g.huella(conn) == antes
    r = componer_arranque(conn).confirmar(analisis)
    assert r["saldo_inicial_centavos"] == analisis.vista["saldo_inicial_centavos"]
    assert r["importacion"]["saldo_centavos"] == 100000
    assert conn.execute(text("SELECT COUNT(*) FROM movimientos")).scalar_one() == 2
    assert conn.execute(text("SELECT estado FROM movimientos WHERE gmail_id='aviso-inventado'")).scalar_one() == "confirmado"
    g.deshacer_importacion(conn, r["importacion"]["id"])
    assert componer_saldo(conn).leer_configuracion() is None
    assert g._foto(conn) == {nombre: [] for nombre in g._foto(conn)}
    assert componer_arranque(conn).resultado_arranque(r["importacion"]["id"])["fase"] == "deshecho"


def test_avisos_no_respaldados_no_se_ocultan_ni_cambian_inicial_al_confirmar(conn):
    analisis = componer_arranque(conn).analizar([[fila(10)]], 100000, modo="arranque", avisos=[aviso(11, 200)])
    assert analisis.vista["saldo_inicial_centavos"] == 100700
    assert analisis.vista["otros_movimientos_netos_centavos"] == -200
    assert componer_arranque(conn).confirmar(analisis)["saldo_inicial_centavos"] == 100700
    assert componer_saldo(conn).saldo_actual() == 100000


def test_extender_preserva_saldo_y_undo_restauraconfig_y_no_reconocidos(conn):
    componer_saldo(conn).configurar(100000, date(2026, 8, 1))
    componer_saldo(conn).registrar_ingreso(1000, datetime(2026, 8, 2, 12), "INGRESO INVENTADO")
    antes = g._foto(conn)
    conf = componer_saldo(conn).leer_configuracion()
    objetivo = componer_saldo(conn).saldo_actual()
    correos = [aviso(), a.AvisoNormalizado("no-reconocido-inventado", None, "2026-07-11T12:00:00", "Aviso inventado")]
    analisis = componer_arranque(conn).analizar([[fila()]], 0, modo="extension", avisos=correos)
    assert g._foto(conn) == antes
    r = componer_arranque(conn).confirmar(analisis)
    assert componer_saldo(conn).saldo_actual() == objetivo
    assert componer_saldo(conn).leer_configuracion().fecha_inicio == date(2026, 7, 10)
    g.deshacer_importacion(conn, r["importacion"]["id"])
    assert componer_saldo(conn).leer_configuracion() == conf
    assert componer_saldo(conn).saldo_actual() == objetivo
    assert g._foto(conn) == antes


def test_importar_historia_extendida_no_duplica_ids_y_la_reextension_se_rechaza(conn):
    componer_saldo(conn).configurar(100000, date(2026, 8, 1))
    analisis = componer_arranque(conn).analizar([[fila()]], 0, modo="extension", avisos=[aviso()])
    componer_arranque(conn).confirmar(analisis)
    antes = g._foto(conn)
    with pytest.raises(a.ErrorArranque, match="anteriores"):
        componer_arranque(conn).analizar([[fila()]], 0, modo="extension", avisos=[aviso()])
    assert g._foto(conn) == antes
    importado = g.confirmar(conn, g.analizar(conn, [fila()]))
    assert importado["saldo_centavos"] == 100000
    assert conn.execute(text("SELECT COUNT(*) FROM movimientos")).scalar_one() == 1


def test_fallo_sql_guardado_revierte_configuracion_y_correo(conn):
    analisis = componer_arranque(conn).analizar([[fila()]], 100000, modo="arranque", avisos=[aviso()])
    with db.transaccion(conn):
        conn.execute(text("CREATE TRIGGER fallar_reversion BEFORE INSERT ON reversiones_importacion BEGIN SELECT RAISE(ABORT,'fallo inventado'); END"))
    antes = g.huella(conn)
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        componer_arranque(conn).confirmar(analisis)
    assert g.huella(conn) == antes
    assert componer_saldo(conn).leer_configuracion() is None


def test_cambio_concurrente_da_conflicto_sin_datos_parciales(conn):
    analisis = componer_arranque(conn).analizar([[fila()]], 100000, modo="arranque")
    componer_saldo(conn).configurar(50, date(2026, 8, 1))
    antes = g.huella(conn)
    with pytest.raises(g.ConflictoImportacion):
        componer_arranque(conn).confirmar(analisis)
    assert g.huella(conn) == antes


def test_undo_arranque_rechaza_movimiento_posterior_sin_pisarlo(conn):
    r = componer_arranque(conn).confirmar(componer_arranque(conn).analizar([[fila()]], 100000, modo="arranque"))
    componer_saldo(conn).registrar_ingreso(1000, datetime(2026, 8, 1, 12), "INGRESO INVENTADO")
    antes = g.huella(conn)
    assert g.detalle(conn, r["importacion"]["id"])["se_puede_deshacer"] is False
    with pytest.raises(g.ConflictoImportacion):
        g.deshacer_importacion(conn, r["importacion"]["id"])
    assert g.huella(conn) == antes and componer_saldo(conn).saldo_actual() == 101000


def test_estado_sincronizacion_real_no_se_guarda_preview_y_undo_lo_restaurara(conn):
    analisis = componer_arranque(conn).analizar([[fila()]], 100000, modo="arranque", avisos=[aviso(),
        a.AvisoNormalizado("desconocido-inventado", None, "2026-07-11T12:00:00", "Aviso inventado"),
        a.AvisoNormalizado("rechazado-inventado", None, "2026-07-11T12:00:00", "Aviso inventado", True)])
    assert sincronizacion.leer_estado(conn) is None
    assert analisis.vista["contadores_gmail"] == {"nuevos": 1, "duplicados": 0, "no_reconocidos": 1,
        "errores": 0, "rechazados_autenticacion": 1}
    resultado = componer_arranque(conn).confirmar(analisis)
    estado = sincronizacion.leer_estado(conn)
    assert estado.estado == "ok" and estado.resultado.nuevos == 1
    assert estado.resultado.no_reconocidos == estado.resultado.rechazados_autenticacion == 1
    g.deshacer_importacion(conn, resultado["importacion"]["id"])
    assert sincronizacion.leer_estado(conn) is None


def test_fallo_al_guardar_estado_revierte_historial_config_y_correo(conn):
    analisis = componer_arranque(conn).analizar([[fila()]], 100000, modo="arranque", avisos=[aviso()])
    with db.transaccion(conn):
        conn.execute(text("CREATE TRIGGER fallar_estado BEFORE INSERT ON estado_sincronizacion BEGIN SELECT RAISE(ABORT,'fallo inventado'); END"))
    antes = g.huella(conn)
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        componer_arranque(conn).confirmar(analisis)
    assert g.huella(conn) == antes and componer_saldo(conn).leer_configuracion() is None


def test_estado_posterior_bloquea_undo_sin_pisarlo(conn):
    resultado = componer_arranque(conn).confirmar(componer_arranque(conn).analizar([[fila()]], 100000, modo="arranque"))
    sincronizacion.guardar_estado(conn, "comando", resultado=sincronizacion.ResultadoSincronizacion(duplicados=1))
    antes = g.huella(conn)
    assert g.detalle(conn, resultado["importacion"]["id"])["se_puede_deshacer"] is False
    with pytest.raises(g.ConflictoImportacion):
        g.deshacer_importacion(conn, resultado["importacion"]["id"])
    assert g.huella(conn) == antes
    assert sincronizacion.leer_estado(conn).origen == "comando"


def test_cobertura_intermedia_truncada_no_marca_ausencias_falsas(conn):
    componer_saldo(conn).configurar(100000, date(2026, 8, 1))
    correos = [aviso(1, 333, "frontera-uno"), aviso(20, 333, "frontera-dos"), aviso(8, 333, "hueco-inventado"), aviso(21, 333, "ausente-acreditado")]
    archivos = [[fila(1)] * 119 + [fila(2)], [fila(20)] * 119 + [fila(21)]]
    analisis = componer_arranque(conn).analizar(archivos, 0, modo="extension", avisos=correos)
    componer_arranque(conn).confirmar(analisis)
    estados = dict(conn.execute(text("SELECT gmail_id,no_en_banco FROM movimientos WHERE origen='gmail'")).all())
    assert estados == {"frontera-uno": 0, "frontera-dos": 0, "hueco-inventado": 0, "ausente-acreditado": 1}


def test_preview_y_confirm_con_ajuste_ultimo_preservan_objetivo_y_ajuste_reversible(conn):
    componer_saldo(conn).configurar(100000, date(2026, 8, 1))
    componer_saldo(conn).ajustar_saldo(120000)
    antes = g._foto(conn)
    analisis = componer_arranque(conn).analizar([[fila()]], 0, modo="extension", avisos=[aviso()])
    r = componer_arranque(conn).confirmar(analisis)
    assert componer_saldo(conn).saldo_actual() == 120000
    assert analisis.vista["saldo_inicial_centavos"] == r["saldo_inicial_centavos"]
    assert r["saldo_inicial_centavos"] == 100500
    assert conn.execute(text("SELECT monto_centavos FROM movimientos WHERE tipo='ajuste'")).scalar_one() == 20000
    g.deshacer_importacion(conn, r["importacion"]["id"])
    assert g._foto(conn) == antes


def test_ajuste_compensa_solo_filas_del_periodo_viejo_y_inicial_solo_historia_nueva(conn):
    componer_saldo(conn).configurar(100000, date(2026, 7, 15))
    componer_saldo(conn).ajustar_saldo(120000)
    analisis = componer_arranque(conn).analizar([[fila(10), fila(20)]], 0, modo="extension")
    r = componer_arranque(conn).confirmar(analisis)
    assert r["saldo_inicial_centavos"] == 100500
    assert conn.execute(text("SELECT monto_centavos FROM movimientos WHERE tipo='ajuste'")).scalar_one() == 20500
    assert componer_saldo(conn).saldo_actual() == 120000


def test_correccion_historica_no_reduce_ajuste_y_compensa_monto_real_en_inicial(conn):
    componer_saldo(conn).configurar(100000, date(2026, 8, 1))
    componer_saldo(conn).ajustar_saldo(120000)
    analisis = componer_arranque(conn).analizar([[fila(10, -510)]], 0, modo="extension", avisos=[aviso(10, 500)])
    r = componer_arranque(conn).confirmar(analisis)
    assert r["saldo_inicial_centavos"] == 100510
    assert r["importacion"]["resumen"]["corregidos"] == 1
    assert conn.execute(text("SELECT monto_centavos FROM movimientos WHERE tipo='ajuste'")).scalar_one() == 20000
    assert componer_saldo(conn).saldo_actual() == 120000


def test_ajuste_cero_se_conserva_y_correo_tardio_no_duplica_historia(conn):
    componer_saldo(conn).configurar(100000, date(2026, 8, 1))
    with db.transaccion(conn):
        conn.execute(db.movimientos.insert().values(tipo="ajuste", origen="manual", monto_centavos=0,
            descripcion="AJUSTE INVENTADO", fecha_hora="2026-08-02T12:00:00"))
    r = componer_arranque(conn).confirmar(componer_arranque(conn).analizar([[fila()]], 0, modo="extension"))
    assert r["saldo_inicial_centavos"] == 100500
    assert conn.execute(text("SELECT monto_centavos FROM movimientos WHERE tipo='ajuste'")).scalar_one() == 0
    sincronizacion._guardar_movimiento(conn, "tardio-inventado", aviso().movimiento)
    assert conn.execute(text("SELECT COUNT(*) FROM movimientos WHERE tipo <> 'ajuste'")).scalar_one() == 1
    assert componer_saldo(conn).saldo_actual() == 100000
    antes = g.huella(conn)
    assert sincronizacion._guardar_movimiento(conn, "tardio-inventado", aviso().movimiento) is False
    assert g.huella(conn) == antes


def test_staging_rechaza_autenticacion_y_citado_sin_retener_cuerpos():
    from finanzas.gmail import CorreoGmail
    from finanzas.compartido.hora import ZONA_COLOMBIA
    from tests.soporte.gmail_falso import ClienteFalso, LEGITIMO
    fecha = datetime(2026, 7, 10, 12, tzinfo=ZONA_COLOMBIA)
    cuerpo = "Bancolombia: Compraste $5,00 en TIENDA INVENTADA con tu T.Deb *1234, el 10/07/2026 a las 12:00."
    correos = {"bueno": CorreoGmail("bueno", fecha, "Aviso", cuerpo, **LEGITIMO),
        "falso": CorreoGmail("falso", fecha, "Aviso", cuerpo),
        "citado": CorreoGmail("citado", fecha, "Aviso", "Reenvío inventado " + cuerpo, **LEGITIMO)}
    salida = preparar_avisos(ClienteFalso(correos=correos), date(2026, 7, 1), set())
    assert salida[0].movimiento.monto_centavos == 500
    assert salida[1].movimiento is None and salida[1].rechazado is True
    assert salida[2].movimiento is None and salida[2].rechazado is False
    assert all(not isinstance(f, CorreoGmail) and not hasattr(f, "texto") for f in salida)


def test_lectura_staging_no_descarga_ids_ya_registrados():
    from tests.soporte.gmail_falso import ClienteFalso
    cliente = ClienteFalso(correos={}, fallan={"registrado-inventado": RuntimeError("no debe descargarse")})
    assert preparar_avisos(cliente, date(2026, 7, 1), {"registrado-inventado"}) == ()
    assert cliente.llamadas_obtener == []


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.integers(-2000, 2000).filter(bool), st.integers(-2000, 2000).filter(bool))
def test_oraculo_extension_compensa_cada_periodo_una_sola_vez(conn, historico, vigente):
    # Cada ejemplo empieza en la misma foto independiente: initial100000,
    # ajuste+20000, saldo120000. Dos efectos: pasado excluido y periodo viejo.
    with db.transaccion(conn):
        for tabla in reversed(g.TABLAS_DIARIO):
            if tabla.name == "movimientos":
                conn.execute(text("DELETE FROM reversiones_importacion"))
                conn.execute(text("DELETE FROM importaciones"))
            conn.execute(tabla.delete())
    componer_saldo(conn).configurar(100000, date(2026, 8, 1))
    componer_saldo(conn).ajustar_saldo(120000)
    historia = [[fila(10, historico), MovimientoExcel(date(2026, 8, 2), vigente, "BANCO INVENTADO")]]
    analisis = componer_arranque(conn).analizar(historia, 0, modo="extension")
    resultado = componer_arranque(conn).confirmar(analisis)
    assert resultado["saldo_inicial_centavos"] == 100000 - historico
    assert conn.execute(text("SELECT monto_centavos FROM movimientos WHERE tipo='ajuste'")).scalar_one() == 20000 - vigente
    assert componer_saldo(conn).saldo_actual() == 120000
    g.deshacer_importacion(conn, resultado["importacion"]["id"])
    assert componer_saldo(conn).leer_configuracion().saldo_inicial_centavos == 100000
    assert componer_saldo(conn).leer_configuracion().fecha_inicio == date(2026, 8, 1)
    assert componer_saldo(conn).saldo_actual() == 120000
