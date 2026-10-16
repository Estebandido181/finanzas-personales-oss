"""Reglas observables del30: análisis inmutable, conflictos y saldo reversible."""
from finanzas.bootstrap.saldo import componer_saldo
from finanzas.bootstrap.reporte import componer_reporte
from datetime import date, datetime
import pytest
from sqlalchemy import text
from finanzas import db, importacion as imp, gestion_importaciones as g, categorizacion as cat
from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import MovimientoExcel
from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import MovimientoExtraido


@pytest.fixture
def conn(tmp_path):
    c = db.conectar(str(tmp_path / "banco.db"))
    db.inicializar(c)
    componer_saldo(c).configurar(100000, date(2026, 8, 1))
    yield c
    c.close()


def fila(dia=10, monto=-500, descripcion="TIENDA EJEMPLO", referencia=None):
    return MovimientoExcel(date(2026, 8, dia), monto, descripcion, referencia)


def importar(conn, filas):
    return g.confirmar(conn, g.analizar(conn, filas))


def primer_dia(conn):
    """Un correo ya categorizado del día 9 y su fila: el día más antiguo de un
    reporte nunca marca "no está en el banco" (D51), así el día que se prueba
    no es el primero. Se confirma sin mover el saldo ni pedir categoría."""
    with db.transaccion(conn):
        conn.execute(db.movimientos.insert().values(fecha_hora="2026-08-09T10:00:00", tipo="compra",
            monto_centavos=777, descripcion="ANCLA INVENTADA", origen="gmail", gmail_id="inventado-ancla",
            categoria_id=1))
    return fila(9, -777, "ANCLA INVENTADA")


def correo(conn, monto=510, dia=10, descripcion="OTRO INVENTADO"):
    with db.transaccion(conn):
        return int(conn.execute(db.movimientos.insert().values(fecha_hora=f"2026-08-{dia:02}T10:00:00",
            tipo="compra", monto_centavos=monto, descripcion=descripcion, origen="gmail", gmail_id=f"inventado-{dia}-{monto}")).inserted_primary_key[0])


def test_analizar_no_guarda_ninguna_fila_ni_modifica_revision(conn):
    antes = g.huella(conn)
    a = g.analizar(conn, [fila()])
    assert a.vista["saldo_despues_centavos"] == 99500
    assert a.vista["diferencia_centavos"] == -500
    assert g.huella(conn) == antes
    assert conn.execute(text("SELECT COUNT(*) FROM importaciones")).scalar_one() == 0


def test_confirmar_coincide_con_preview_y_doble_importar_no_mueve_saldo(conn):
    a = g.analizar(conn, [fila(), fila(11, 1000)])
    r = g.confirmar(conn, a)
    assert r["resumen"] == a.vista["resumen"]
    assert r["saldo_centavos"] == a.vista["saldo_despues_centavos"]
    assert importar(conn, [fila(), fila(11, 1000)])["saldo_centavos"] == r["saldo_centavos"]
    assert conn.execute(text("SELECT COUNT(*) FROM movimientos")).scalar_one() == 2


@pytest.mark.parametrize("cambio", ["correo", "ajuste", "categoria", "regla"])
def test_cambio_concurrente_exige_reanalizar_sin_escritura(conn, cambio):
    a = g.analizar(conn, [fila()])
    if cambio == "correo":
        correo(conn)
    elif cambio == "ajuste":
        componer_saldo(conn).ajustar_saldo(99000)
    elif cambio == "categoria":
        cat.editar_categoria(conn, 1, nombre="Mercado inventado")
    else:
        with db.transaccion(conn):
            conn.execute(db.reglas.insert().values(campo="comercio", texto="tienda ejemplo", categoria_id=1))
    antes = g.huella(conn)
    with pytest.raises(g.ConflictoImportacion):
        g.confirmar(conn, a)
    assert g.huella(conn) == antes


def test_deshacer_restaura_foto_y_conserva_movimiento_posterior_ajeno(conn):
    antes = g._foto(conn)
    r = importar(conn, [fila()])
    ajeno = correo(conn, dia=20)
    assert g.detalle(conn, r["id"])["se_puede_deshacer"]
    g.deshacer_importacion(conn, r["id"])
    assert conn.execute(text("SELECT id FROM movimientos")).scalars().all() == [ajeno]
    assert componer_saldo(conn).saldo_actual() == 99490


def test_deshacer_no_toca_ajuste_nuevo_y_estado_lo_anticipa(conn):
    r = importar(conn, [fila()])
    componer_saldo(conn).ajustar_saldo(200000)
    foto = g.huella(conn)
    assert not g.detalle(conn, r["id"])["se_puede_deshacer"]
    with pytest.raises(g.ConflictoImportacion):
        g.deshacer_importacion(conn, r["id"])
    assert componer_saldo(conn).saldo_actual() == 200000
    assert g.huella(conn) == foto


def test_deshacer_restaura_ajuste_reducido_hasta_cero(conn):
    with db.transaccion(conn):
        conn.execute(db.movimientos.insert().values(fecha_hora="2026-08-12T10:00:00", monto_centavos=-500,
            tipo="ajuste", descripcion="", origen="manual"))
    r = importar(conn, [fila()])
    assert conn.execute(text("SELECT monto_centavos FROM movimientos WHERE tipo='ajuste'")).scalar_one() == 0
    g.deshacer_importacion(conn, r["id"])
    assert conn.execute(text("SELECT monto_centavos FROM movimientos WHERE tipo='ajuste'")).scalar_one() == -500
    assert componer_saldo(conn).saldo_actual() == 99500


def test_aviso_tardio_bloquea_undo_sin_perder_correo(conn):
    r = importar(conn, [fila()])
    with db.transaccion(conn):
        assert imp.recibir_aviso(conn, "aviso-inventado", MovimientoExtraido("compra", 500,
            datetime(2026, 8, 10, 10), "TIENDA EJEMPLO")) == "confirmado"
    with pytest.raises(g.ConflictoImportacion):
        g.deshacer_importacion(conn, r["id"])
    assert conn.execute(text("SELECT gmail_id FROM movimientos")).scalar_one() == "aviso-inventado"


def test_aviso_tardio_ambiguo_bloquea_undo_en_detalle_sin_escritura(conn):
    r = importar(conn, [fila()])
    with db.transaccion(conn):
        assert imp.recibir_aviso(conn, "aviso-ambiguo-inventado", MovimientoExtraido("compra", 510,
            datetime(2026, 8, 10, 10), "OTRO INVENTADO")) == "pregunta"
    antes = g.huella(conn)
    detalle = g.detalle(conn, r["id"])
    assert detalle["se_puede_deshacer"] is False
    assert detalle["motivo_no_deshacer"] == g.MENSAJE_REVERSION
    assert g.huella(conn) == antes
    with pytest.raises(g.ConflictoImportacion, match="hay cambios posteriores"):
        g.deshacer_importacion(conn, r["id"])
    assert g.huella(conn) == antes
    assert componer_saldo(conn).saldo_actual() == 99500


def test_undo_detecta_candidato_ajeno_por_clave_compuesta(conn):
    correo(conn)
    r = importar(conn, [fila()])
    pregunta = g.preguntas(conn)["preguntas"][0]["id"]
    ajeno = correo(conn, dia=20)
    with db.transaccion(conn):
        conn.execute(db.candidatos_pregunta.insert().values(pregunta_id=pregunta, movimiento_id=ajeno))
    antes = g.huella(conn)
    assert g.detalle(conn, r["id"])["se_puede_deshacer"] is False
    with pytest.raises(g.ConflictoImportacion):
        g.deshacer_importacion(conn, r["id"])
    assert g.huella(conn) == antes


def test_respuesta_es_reversible_y_pregunta_get_no_guarda(conn):
    correo(conn)
    r = importar(conn, [fila()])
    antes = g.huella(conn)
    p = g.preguntas(conn)["preguntas"][0]
    assert g.huella(conn) == antes
    assert p["sugerencia"]["opcion"] == "si:1"
    assert g.preguntas(conn)["con_sugerencia"] == 1
    respuesta, copia = g.responder(conn, [(p["id"], "si:1")])
    assert respuesta["efecto_saldo_centavos"] == 10
    assert not g.preguntas(conn)["preguntas"]
    g.deshacer_decision(conn, copia)
    assert g.huella(conn) == antes
    assert g.preguntas(conn)["total"] == 1


def test_respuesta_y_undo_importacion_dejan_correo_original(conn):
    correo(conn)
    antes = g._foto(conn)
    r = importar(conn, [fila()])
    p = g.preguntas(conn)["preguntas"][0]
    g.responder(conn, [(p["id"], "si:1")])
    assert g.detalle(conn, r["id"])["se_puede_deshacer"]
    g.deshacer_importacion(conn, r["id"])
    assert g._foto(conn) == antes


def test_borrar_no_en_banco_oculta_en_saldo_reporte_bandeja_y_se_deshace(conn):
    ident = correo(conn, monto=2000)
    importar(conn, [primer_dia(conn), fila(10)])
    assert len(g.no_en_banco(conn)["movimientos"]) == 1
    resultado, copia = g.decidir_no_en_banco(conn, ident, "borrar")
    assert resultado["efecto_saldo_centavos"] == 2000
    assert cat.contar_sin_categorizar(conn) == 1
    from finanzas.flujos import reporte
    assert [m.id for m in componer_reporte(conn).reporte_mensual(2026, 8).movimientos] != [ident]
    assert not g.no_en_banco(conn)["movimientos"]
    g.deshacer_decision(conn, copia)
    assert len(g.no_en_banco(conn)["movimientos"]) == 1
    assert cat.contar_sin_categorizar(conn) == 2


def test_borrado_que_aparece_en_banco_mueve_saldo_y_conserva_gmail_dedupe(conn):
    ident = correo(conn, monto=2000)
    ancla = primer_dia(conn)
    importar(conn, [ancla, fila(10)])
    g.decidir_no_en_banco(conn, ident, "borrar")
    antes = componer_saldo(conn).saldo_actual()
    importar(conn, [ancla, fila(10, -2000), fila(10)])
    assert componer_saldo(conn).saldo_actual() == antes - 2000
    assert conn.execute(text("SELECT gmail_id FROM movimientos WHERE id=:id"), {"id": ident}).scalar_one()


def test_regla_empieza_por_categoriza_siguiente_importacion_sin_tocar_correo(conn):
    r = importar(conn, [fila(descripcion="COBRO EJEMPLO")])
    grupo = r["grupos"][0]
    cat.categorizar_grupo(conn, grupo["clave"], grupo["ids"], 3, "empieza_por")
    assert cat.regla_que_coincide(conn, "compra", "COBRO EJEMPLO NUEVO", 500, "gmail") is None
    a = g.analizar(conn, [fila(12, descripcion="COBRO EJEMPLO NUEVO")])
    assert a.vista["entran_categorizados"] == 1
    r2 = g.confirmar(conn, a)
    assert r2["sin_categoria"] == 0
    assert conn.execute(text("SELECT categoria_id FROM movimientos ORDER BY id DESC LIMIT 1")).scalar_one() == 3


def test_fallo_parcial_no_deja_importacion_ni_diario(conn, monkeypatch):
    a = g.analizar(conn, [fila()])
    antes = g.huella(conn)
    def fallar(*args, **kwargs):
        raise RuntimeError("fallo inventado")
    from finanzas.modulos.importaciones import gestion_sqlite
    monkeypatch.setattr(gestion_sqlite, "_categorizar_nuevos", fallar)
    with pytest.raises(RuntimeError):
        g.confirmar(conn, a)
    assert g.huella(conn) == antes


def test_recordatorio_por_cien_o_cuatro_semanas_desaparece_importando(conn, monkeypatch):
    monkeypatch.setattr(hora := g.hora, "hoy_colombia", lambda: date(2026, 8, 30))
    assert g.estado(conn)["mostrar_recordatorio"]
    importar(conn, [fila()])
    assert not g.estado(conn)["mostrar_recordatorio"]


def test_regla_destino_se_aplica_a_referencia_del_banco(conn):
    with db.transaccion(conn):
        conn.execute(db.reglas.insert().values(campo="cuenta_destino", texto="*0009", categoria_id=3))
    a = g.analizar(conn, [fila(referencia="*0009", descripcion="TRANSFERENCIA EJEMPLO")])
    assert a.vista["entran_categorizados"] == 1
    r = g.confirmar(conn, a)
    assert r["sin_categoria"] == 0


def test_lote_invalido_no_guarda_primera_respuesta(conn):
    correo(conn)
    importar(conn, [fila()])
    p = g.preguntas(conn)["preguntas"][0]
    antes = g.huella(conn)
    with pytest.raises(g.ConflictoImportacion):
        g.responder(conn, [(p["id"], "si:1"), (999, "no")])
    assert g.huella(conn) == antes


def test_deshacer_decision_no_pisa_categorizacion_posterior(conn):
    mid = correo(conn, monto=2000)
    importar(conn, [primer_dia(conn), fila()])
    _, copia = g.decidir_no_en_banco(conn, mid, "dejar")
    cat.asignar_categoria(conn, mid, 1, False)
    antes = g.huella(conn)
    with pytest.raises(g.ConflictoImportacion):
        g.deshacer_decision(conn, copia)
    assert g.huella(conn) == antes


def test_recordatorio_al_llegar_a_cien_movimientos(conn, monkeypatch):
    monkeypatch.setattr(g.hora, "hoy_colombia", lambda: date(2026, 8, 10))
    importar(conn, [fila()])
    with db.transaccion(conn):
        for i in range(100):
            conn.execute(db.movimientos.insert().values(fecha_hora="2026-08-11T10:00:00", tipo="compra",
                monto_centavos=1000, descripcion="TIENDA INVENTADA", origen="gmail", gmail_id=f"aviso-cien-{i}"))
    assert g.estado(conn)["mostrar_recordatorio"]
    assert g.estado(conn)["movimientos_desde_ultima"] == 100


def test_recordatorio_y_fecha_de_importacion_usan_dia_colombiano(conn, monkeypatch):
    r = importar(conn, [fila()])
    with db.transaccion(conn):
        conn.execute(db.importaciones.update().where(db.importaciones.c.id == r["id"]).values(
            hecha_en="2026-08-11T03:00:00"))
    monkeypatch.setattr(g.hora, "hoy_colombia", lambda: date(2026, 9, 7))
    assert g.detalle(conn, r["id"])["hecha_en"] == "2026-08-10T22:00:00"
    assert g.estado(conn)["semanas_desde_ultima"] == 4
    assert g.estado(conn)["mostrar_recordatorio"]


def test_sugerencia_ambiguas_no_se_responden_solas(conn):
    correo(conn)
    importar(conn, [fila(), fila()])
    lista = g.preguntas(conn)
    assert lista["total"] == 2
    assert lista["con_sugerencia"] == 0
    assert all(p["sugerencia"]["opcion"] is None for p in lista["preguntas"])
    assert componer_saldo(conn).saldo_actual() == 99490


def test_pregunta_dia_ajuste_no_sugiere_sin_hora_del_banco(conn):
    with db.transaccion(conn):
        conn.execute(db.movimientos.insert().values(fecha_hora="2026-08-10T10:00:00", monto_centavos=500,
            tipo="ajuste", descripcion="", origen="manual"))
    importar(conn, [fila()])
    lista = g.preguntas(conn)
    assert lista["total"] == 1 and lista["con_sugerencia"] == 0
    assert lista["preguntas"][0]["tipo"] == "mismo_dia_ajuste"


def test_grupo_y_regla_conservan_texto_original_y_rango_real(conn):
    r = importar(conn, [fila(10, descripcion="COBRO EJEMPLO"), fila(13, descripcion="COBRO EJEMPLO")])
    grupo = r["grupos"][0]
    assert grupo["desde"] == "2026-08-10" and grupo["hasta"] == "2026-08-13"
    assert grupo["regla"]["texto"] == "cobro ejemplo"
    assert "«COBRO EJEMPLO»" in grupo["regla"]["frase"]
    assert all("«COBRO EJEMPLO»" in p["frase"] for p in grupo["reglas_propuestas"])
    asignacion = cat.categorizar_grupo(conn, grupo["clave"], grupo["ids"], 3, "empieza_por")
    regla = cat.buscar_regla(conn, asignacion.regla_id)
    assert regla["texto"] == "cobro ejemplo" and regla["texto_visible"] == "COBRO EJEMPLO"
    copia = cat.borrar_regla_con_copia(conn, asignacion.regla_id)
    cat.restaurar_regla(conn, copia)
    assert cat.buscar_regla(conn, asignacion.regla_id)["texto_visible"] == "COBRO EJEMPLO"


def test_grupos_no_incluyen_avisos_ausentes_y_solo_proponen_modos_validos(conn):
    ausente = correo(conn, monto=2000)
    r = importar(conn, [primer_dia(conn), fila()])
    assert r["sin_categoria"] == 1
    assert ausente not in r["grupos"][0]["ids"]
    assert r["no_en_banco_pendientes"] == 1
    confirmado = correo(conn, monto=1000, dia=11)
    r2 = importar(conn, [fila(11, -1000)])
    assert r2["grupos"][0]["ids"] == [confirmado]
    assert [p["modo"] for p in r2["grupos"][0]["reglas_propuestas"]] == ["exacta"]


def test_undo_borrado_tras_banco_real_rechaza_sin_duplicar_saldo(conn):
    mid = correo(conn, monto=500)
    ancla = primer_dia(conn)  # su correo de $7,77 ya cuenta en el saldo
    importar(conn, [ancla, fila(monto=-2000)])
    _, copia = g.decidir_no_en_banco(conn, mid, "borrar")
    importar(conn, [ancla, fila(monto=-500)])
    antes = g.huella(conn)
    assert componer_saldo(conn).saldo_actual() == 97500 - 777
    with pytest.raises(g.ConflictoImportacion):
        g.deshacer_decision(conn, copia)
    assert g.huella(conn) == antes and componer_saldo(conn).saldo_actual() == 97500 - 777


def test_undo_respuesta_tras_nueva_importacion_rechaza_sin_reabrir_pregunta(conn):
    correo(conn)
    importar(conn, [fila()])
    p = g.preguntas(conn)["preguntas"][0]
    _, copia = g.responder(conn, [(p["id"], "si:1")])
    importar(conn, [fila()])
    antes = g.huella(conn)
    with pytest.raises(g.ConflictoImportacion):
        g.deshacer_decision(conn, copia)
    assert g.huella(conn) == antes and not g.preguntas(conn)["preguntas"]


def test_opciones_identifican_candidatos_con_monto_y_datos_humanos(conn):
    correo(conn, monto=510, descripcion="PRIMER LOCAL", dia=10)
    with db.transaccion(conn):
        conn.execute(db.movimientos.insert().values(fecha_hora="2026-08-10T10:00:00", tipo="compra",
            monto_centavos=510, descripcion="SEGUNDO LOCAL", origen="gmail", gmail_id="segundo-local-inventado"))
    importar(conn, [fila()])
    p = g.preguntas(conn)["preguntas"][0]
    opciones = [o["texto"] for o in p["opciones"] if o["id"].startswith("si:")]
    assert len(opciones) == 2
    assert "PRIMER LOCAL" in opciones[0] and "SEGUNDO LOCAL" in opciones[1]
    assert all("$5,10" in o and "2026-08-10 a las 10:00" in o for o in opciones)
    assert all("movimiento 1" not in o and "movimiento 2" not in o for o in opciones)


def test_candidatos_identicos_tienen_etiquetas_visibles_coherentes(conn):
    correo(conn)
    with db.transaccion(conn):
        conn.execute(db.movimientos.insert().values(fecha_hora="2026-08-10T10:00:00", tipo="compra",
            monto_centavos=510, descripcion="OTRO INVENTADO", origen="gmail", gmail_id="otra-copia-inventada"))
    importar(conn, [fila()])
    p = g.preguntas(conn)["preguntas"][0]
    assert [c["etiqueta"] for c in p["candidatos"]] == ["Candidato 1", "Candidato 2"]
    for candidato in p["candidatos"]:
        opcion = next(o for o in p["opciones"] if o["id"] == f'si:{candidato["id"]}')
        assert candidato["etiqueta"] in opcion["texto"]


def test_opcion_aviso_tardio_nombra_el_monto_del_banco(conn):
    importar(conn, [fila()])
    with db.transaccion(conn):
        assert imp.recibir_aviso(conn, "aviso-tardio-inventado", MovimientoExtraido("compra", 510,
            datetime(2026, 8, 10, 10), "OTRO INVENTADO")) == "pregunta"
    p = g.preguntas(conn)["preguntas"][0]
    assert p["fuente"] == "correo"
    opcion = next(o for o in p["opciones"] if o["id"].startswith("si:"))
    assert opcion["texto"] == "Es el mismo: quedarse con $5"
    assert "$5,10" not in opcion["texto"]
