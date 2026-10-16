"""Reservas por ocurrencia; datos inventados, sin archivos bancarios guardados."""
from finanzas.bootstrap.saldo import componer_saldo
from datetime import date, datetime

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from finanzas.modulos.importaciones import motor as c
from finanzas.bootstrap.descartes import componer_descartes
from finanzas.modulos.movimientos.descartes_contratos import DescarteNoPermitido
from finanzas import db, importacion, gestion_importaciones as gestion
from finanzas.modulos.importaciones import elecciones_sqlite as elecciones_banco
from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import MovimientoExtraido
from tests.soporte.importacion import conn, del_correo, fila, foto, movimiento, sql, ajuste_el_dia, _compra, primer_dia  # noqa: F401
from tests.soporte.conciliacion_propiedades import Base, plantilla  # noqa: F401
from tests.soporte.gmail_falso import ClienteFalso
from finanzas.sincronizacion import sincronizar


def aviso(monto=10000, descripcion="TIENDA EJEMPLO", tipo="compra"):
    return MovimientoExtraido(tipo, monto, datetime(2026, 8, 10, 12), descripcion, None)


def recibir(conn, gmail_id="aviso-inventado", **kwargs):
    with db.transaccion(conn, inmediata=True):
        return importacion.recibir_aviso(conn, gmail_id, aviso(**kwargs))


def banco(conn, filas):
    importacion.importar(conn, filas)
    return [r[0] for r in sql(conn, "SELECT id FROM movimientos WHERE origen='extracto' ORDER BY id")]


def reservas(conn):
    return [tuple(r) for r in conn.execute(select(db.descartes_movimientos).order_by(db.descartes_movimientos.c.id))]


@pytest.mark.parametrize("tipo,firmado,descripcion,referencia", [
    ("compra", -10000, "TIENDA EJEMPLO", None),
    ("ingreso", 10000, "PERSONA EJEMPLO", None),
    ("transferencia", -10000, "*0001", "*0001"),
])
def test_correo_descartado_se_confirma_sin_reactivar_y_se_restaura_misma_fila(conn, tipo, firmado, descripcion, referencia):
    ident = del_correo(conn, 10, tipo, 10000, descripcion)
    componer_descartes(conn).cambiar(ident)
    antes = componer_saldo(conn).saldo_actual()
    reporte = [fila(10, firmado, referencia=referencia)]
    r = importacion.importar(conn, reporte).conteos
    assert r.ya_estaban == 1 and not r.agregados and not r.ajuste_reducido
    m = movimiento(conn, ident)
    assert m["borrado_en"] and m["estado"] == "confirmado" and m["fecha_banco"] == "2026-08-10"
    assert componer_saldo(conn).saldo_actual() == antes
    guardado, historial = foto(conn), reservas(conn)
    importacion.importar(conn, reporte)
    assert foto(conn) == guardado and reservas(conn) == historial
    componer_descartes(conn).cambiar(ident, restaurar=True)
    assert movimiento(conn, ident)["borrado_en"] is None
    assert componer_saldo(conn).saldo_actual() == antes + firmado
    assert len(sql(conn, "SELECT id FROM movimientos")) == 1


def test_importado_descartado_reimportar_no_reaparece_ni_cambia_ajuste_cero(conn):
    [ident] = banco(conn, [fila(10, -10000)])
    componer_descartes(conn).cambiar(ident)
    ajuste = ajuste_el_dia(conn, 20, 0)
    antes, guardado, historial = componer_saldo(conn).saldo_actual(), foto(conn), reservas(conn)
    r = importacion.importar(conn, [fila(10, -10000)]).conteos
    assert r.ya_estaban == 1 and not r.agregados and not r.ajuste_reducido
    assert componer_saldo(conn).saldo_actual() == antes and foto(conn) == guardado and reservas(conn) == historial
    assert movimiento(conn, ajuste)["monto_centavos"] == 0


def test_un_ajuste_posterior_no_absorbe_correccion_de_sombra(conn):
    ident = del_correo(conn, 10, "compra", 10000)
    componer_descartes(conn).cambiar(ident)
    ajuste = ajuste_el_dia(conn, 20, -1000)
    antes = componer_saldo(conn).saldo_actual()
    r = importacion.importar(conn, [fila(10, -10300)]).conteos
    assert r.ya_estaban == 1 and not r.ajuste_reducido
    assert movimiento(conn, ident)["monto_centavos"] == 10300
    assert movimiento(conn, ajuste)["monto_centavos"] == -1000
    assert componer_saldo(conn).saldo_actual() == antes


def test_parecido_seguro_banco_autoritativo_al_restaurar(conn):
    ident = del_correo(conn, 10, "transferencia", 10000, "*0001")
    componer_descartes(conn).cambiar(ident)
    antes = componer_saldo(conn).saldo_actual()
    reporte = [fila(10, -10300, referencia="*0001")]
    importacion.importar(conn, reporte)
    assert movimiento(conn, ident)["monto_centavos"] == 10300
    assert componer_saldo(conn).saldo_actual() == antes
    componer_descartes(conn).cambiar(ident, restaurar=True)
    assert componer_saldo(conn).saldo_actual() == antes - 10300
    guardado = foto(conn)
    importacion.importar(conn, reporte)
    assert foto(conn) == guardado


@pytest.mark.parametrize("referencia", [None, "*0001"])
def test_repeticiones_con_sombra_consume_solo_una_ocurrencia_y_admite_excedentes(conn, referencia):
    reporte = [fila(10, -10000, referencia=referencia)] * 2
    ids = banco(conn, reporte)
    componer_descartes(conn).cambiar(ids[0])
    antes = componer_saldo(conn).saldo_actual()
    r = importacion.importar(conn, reporte + [reporte[0]]).conteos
    assert r.ya_estaban == 2 and r.agregados == 1 and not r.preguntas
    assert componer_saldo(conn).saldo_actual() == antes - 10000
    guardado = foto(conn)
    importacion.importar(conn, reporte + [reporte[0]])
    assert foto(conn) == guardado and len(sql(conn, "SELECT id FROM movimientos")) == 3


def test_destinos_distintos_no_consumen_la_sombra_equivocada(conn):
    [ident] = banco(conn, [fila(10, -10000, referencia="*0001")])
    componer_descartes(conn).cambiar(ident)
    r = importacion.importar(conn, [fila(10, -10000, referencia="*0002")]).conteos
    assert r.agregados == 1 and not r.preguntas
    assert movimiento(conn, ident)["referencia"] == "*0001" and movimiento(conn, ident)["borrado_en"]


def test_destino_ausente_entre_activo_y_descarte_se_pregunta(conn):
    ids = banco(conn, [fila(10, -10000, referencia="*0001"), fila(10, -10000, referencia="*0002")])
    componer_descartes(conn).cambiar(ids[0])
    antes = componer_saldo(conn).saldo_actual()
    r = importacion.importar(conn, [fila(10, -10000)]).conteos
    assert r.preguntas == 1 and not r.agregados and componer_saldo(conn).saldo_actual() == antes
    [p] = importacion.preguntas_pendientes(conn)
    assert set(p["candidatos"]) == set(ids)
    guardado = foto(conn)
    importacion.importar(conn, [fila(10, -10000)])
    assert foto(conn) == guardado


@pytest.mark.parametrize("elegir_sombra", [False, True])
def test_pregunta_exacta_sin_respaldo_responde_same_id_y_reimport_no_pregunta(conn, elegir_sombra):
    ids = [del_correo(conn, 10, "compra", 10000) for _ in range(2)]
    componer_descartes(conn).cambiar(ids[0])
    reporte = [primer_dia(conn), fila(10, -10000)]
    antes = componer_saldo(conn).saldo_actual()
    assert importacion.importar(conn, reporte).conteos.preguntas == 1
    [p] = importacion.preguntas_pendientes(conn)
    importacion.responder_pregunta(conn, p["id"], True, ids[0 if elegir_sombra else 1])
    assert componer_saldo(conn).saldo_actual() == antes and movimiento(conn, ids[0])["borrado_en"]
    guardado = foto(conn)
    assert not importacion.importar(conn, reporte).conteos.preguntas
    # Elegir la sombra deja el aviso competidor sin respaldo; la primera
    # revisión completa puede marcarlo ausente, pero la siguiente es idéntica.
    if elegir_sombra:
        assert movimiento(conn, ids[1])["no_en_banco"]
        guardado = foto(conn)
        assert not importacion.importar(conn, reporte).conteos.preguntas
    assert foto(conn) == guardado


@pytest.mark.parametrize("elegir_sombra", [False, True])
@pytest.mark.parametrize("con_respaldo,monto_banco", [(False, 10000), (False, 10300), (True, 10000)],
                         ids=["correo-exacto", "correo-parecido", "respaldado-exacto"])
def test_reporte_ampliado_no_duplica_candidatos_reservados(conn, elegir_sombra, con_respaldo, monto_banco):
    ids = (banco(conn, [fila(10, -10000)] * 2) if con_respaldo else
           [del_correo(conn, 10, "compra", 10000) for _ in range(2)])
    componer_descartes(conn).cambiar(ids[0])
    banco_uno = [fila(10, -monto_banco)]
    assert importacion.importar(conn, banco_uno).conteos.preguntas == 1
    [primera] = importacion.preguntas_pendientes(conn)
    assert set(primera["candidatos"]) == set(ids)
    antes = componer_saldo(conn).saldo_actual()
    reporte_ampliado = banco_uno * 2
    ampliado = importacion.importar(conn, reporte_ampliado).conteos
    assert ampliado.ya_preguntadas == 1 and not ampliado.agregados
    assert componer_saldo(conn).saldo_actual() == antes and len(sql(conn, "SELECT id FROM movimientos")) == 2
    assert len(importacion.preguntas_pendientes(conn)) == 2
    guardado = foto(conn)
    assert not importacion.importar(conn, reporte_ampliado).conteos.agregados
    assert foto(conn) == guardado
    importacion.responder_pregunta(conn, primera["id"], True, ids[0 if elegir_sombra else 1])
    esperado = antes if elegir_sombra else antes - (monto_banco - 10000)
    assert componer_saldo(conn).saldo_actual() == esperado
    assert movimiento(conn, ids[0])["borrado_en"] is not None
    guardado = foto(conn)
    ultimo = importacion.importar(conn, reporte_ampliado).conteos
    assert not ultimo.agregados and not ultimo.preguntas
    assert foto(conn) == guardado and componer_saldo(conn).saldo_actual() == esperado
    assert len(sql(conn, "SELECT id FROM movimientos")) == 2
    restante = ids[1 if elegir_sombra else 0]
    [pendiente] = gestion.preguntas(conn)["preguntas"]
    assert [m["id"] for m in pendiente["candidatos"]] == [restante]
    assert pendiente["candidatos"][0]["descartado"] == (not elegir_sombra)
    assert any(opcion["id"] == f"si:{restante}" for opcion in pendiente["opciones"])
    assert any(opcion["id"] == "no" for opcion in pendiente["opciones"])
    assert foto(conn) == guardado and componer_saldo(conn).saldo_actual() == esperado
    gestion.responder(conn, [(pendiente["id"], f"si:{restante}")])
    esperado_final = antes - (monto_banco - 10000)
    assert componer_saldo(conn).saldo_actual() == esperado_final
    assert len(sql(conn, "SELECT id FROM movimientos")) == 2
    assert movimiento(conn, ids[0])["borrado_en"] is not None
    guardado = foto(conn)
    final = importacion.importar(conn, reporte_ampliado).conteos
    assert not final.agregados and not final.preguntas and not final.confirmados
    assert foto(conn) == guardado and componer_saldo(conn).saldo_actual() == esperado_final


@pytest.mark.parametrize("opcion", ["activo", "descarte", "nuevo"])
def test_cobertura_parcial_respeta_eleccion_reimportacion_restauracion_y_excedentes(conn, opcion):
    ids = banco(conn, [fila(10, -10000)] * 2)
    componer_descartes(conn).cambiar(ids[0])
    reporte = [fila(10, -10000)]
    assert importacion.importar(conn, reporte).conteos.preguntas == 1
    [p] = importacion.preguntas_pendientes(conn)
    antes = componer_saldo(conn).saldo_actual()
    if opcion == "nuevo":
        importacion.responder_pregunta(conn, p["id"], False)
        elegido = sql(conn, "SELECT MAX(id) FROM movimientos")[0][0]
        assert componer_saldo(conn).saldo_actual() == antes - 10000
    else:
        elegido = ids[0 if opcion == "descarte" else 1]
        importacion.responder_pregunta(conn, p["id"], True, elegido)
        assert componer_saldo(conn).saldo_actual() == antes
    [d] = elecciones_banco.listar_elecciones_banco(conn)
    assert d["movimiento_elegido_id"] == elegido and d["ocurrencia_banco"] == 1
    guardado, historial, antes = foto(conn), reservas(conn), componer_saldo(conn).saldo_actual()
    r = importacion.importar(conn, reporte).conteos
    assert r.ya_estaban == 1 and not r.preguntas and not r.agregados
    assert foto(conn) == guardado and reservas(conn) == historial and componer_saldo(conn).saldo_actual() == antes
    componer_descartes(conn).cambiar(ids[0], restaurar=True)
    guardado = foto(conn)
    assert not importacion.importar(conn, reporte).conteos.preguntas and foto(conn) == guardado
    conocidos = len(sql(conn, "SELECT id FROM movimientos"))
    r = importacion.importar(conn, reporte * (conocidos + 1)).conteos
    assert r.agregados == 1 and not r.preguntas


def test_ordinal_por_identidad_no_por_descripcion_ni_posicion_global(conn):
    # Esta otra identidad ordena antes y no desplaza el ordinal de la pregunta.
    ids = banco(conn, [fila(10, -10000)] * 2)
    componer_descartes(conn).cambiar(ids[0])
    importacion.importar(conn, [fila(9, -30000), fila(10, -10000, "PRIMER EJEMPLO")])
    [p] = importacion.preguntas_pendientes(conn)
    assert sql(conn, "SELECT ocurrencia_banco FROM preguntas_conciliacion WHERE id=?", (p["id"],))[0][0] == 1
    importacion.responder_pregunta(conn, p["id"], True, ids[0])
    guardado = foto(conn)
    r = importacion.importar(conn, [fila(10, -10000, "OTRA DESCRIPCION EJEMPLO"), fila(9, -30000)]).conteos
    assert not r.agregados and not r.preguntas and foto(conn) == guardado


def test_eleccion_obsoleta_y_dos_ordinales_con_mismo_id_preguntan_sin_fallback():
    fecha = date(2026, 8, 10)
    f = c.FilaBanco(fecha, -10000, "EJEMPLO")
    activo = c.MovimientoApp(1, fecha, "compra", 10000, "EJEMPLO", "extracto", "sin_aviso", fecha_banco=fecha)
    cambiado = c.MovimientoApp(2, fecha, "compra", 10300, "EJEMPLO", "extracto", "sin_aviso", fecha_banco=fecha)
    ultima = c.EleccionBanco(fecha, -10000, None, 1, cambiado.id)
    p = c.conciliar([f], [activo, cambiado], fecha, elecciones=[ultima])
    assert len(p.preguntas) == 1 and not p.agregar and not p.ya_estaban
    assert p.preguntas[0].candidatos == (activo.id,)
    repetidos = [c.EleccionBanco(fecha, -10000, None, i, activo.id) for i in (1, 2)]
    p = c.conciliar([f, f], [activo], fecha, elecciones=repetidos)
    assert len(p.preguntas) == 2 and not p.agregar and not p.ya_estaban


@pytest.mark.parametrize("sombra_descartada", [False, True])
@pytest.mark.parametrize("segunda_valida", [False, True])
def test_eleccion_obsoleta_nunca_reusa_candidato_reservado_ni_eleccion_valida(segunda_valida, sombra_descartada):
    fecha = date(2026, 8, 10)
    f = c.FilaBanco(fecha, -10000, "EJEMPLO")
    cambiado = c.MovimientoApp(1, fecha, "compra", 10300, "EJEMPLO", "extracto", "sin_aviso", fecha_banco=fecha)
    exacto = c.MovimientoApp(2, fecha, "compra", 10000, "EJEMPLO", "extracto", "sin_aviso", fecha_banco=fecha)
    decisiones = [c.EleccionBanco(fecha, -10000, None, 1, cambiado.id)]
    if segunda_valida:
        decisiones.append(c.EleccionBanco(fecha, -10000, None, 2, exacto.id))
    activos = [cambiado] if sombra_descartada else [cambiado, exacto]
    sombras = [c.ReservaDescarte(exacto, f)] if sombra_descartada else []
    p = c.conciliar([f, f], activos, fecha, elecciones=decisiones, descartes=sombras)
    assert not p.agregar and not p.reduccion_ajuste
    if segunda_valida:
        assert [par.movimiento_id for par in p.ya_estaban + p.descartadas] == [exacto.id]
        assert [(q.ocurrencia_banco, q.candidatos) for q in p.preguntas] == [(1, ())]
    else:
        assert not p.ya_estaban
        assert {(q.ocurrencia_banco, q.candidatos) for q in p.preguntas} == {(1, (exacto.id,)), (2, ())}
    assert {mid for q in p.preguntas for mid in q.candidatos}.isdisjoint(par.movimiento_id for par in p.ya_estaban + p.descartadas)


def test_pregunta_abierta_reserva_backing_antes_de_emparejar_otra_sombra():
    fecha = date(2026, 8, 10)
    f = c.FilaBanco(fecha, -10000, "EJEMPLO")
    reservado = c.MovimientoApp(2, fecha, "compra", 10000, "EJEMPLO", "extracto", "sin_aviso",
                              fecha_banco=fecha, reservado=True)
    sombra = c.MovimientoApp(3, fecha, "compra", 10000, "EJEMPLO", "extracto", "sin_aviso", fecha_banco=fecha)
    pregunta = c.PreguntaPendiente(9, fecha, -10000, ocurrencia_banco=1)
    p = c.conciliar([f, f], [reservado], fecha, preguntas_pendientes=[pregunta],
                    descartes=[c.ReservaDescarte(sombra, f)])
    assert p.ya_preguntadas == [(f, pregunta.id)]
    assert [par.movimiento_id for par in p.descartadas] == [sombra.id]
    assert not p.ya_estaban and not p.preguntas and not p.agregar


@pytest.mark.parametrize("sombra_descartada", [False, True])
@pytest.mark.parametrize("segunda_valida", [False, True])
def test_reimportar_eleccion_obsoleta_y_responder_no_duplica_ni_mueve_saldo_solo(conn, segunda_valida, sombra_descartada):
    ids = banco(conn, [fila(10, -10000)] * 2)
    if sombra_descartada:
        componer_descartes(conn).cambiar(ids[1])
    with db.transaccion(conn):
        for ordinal, ident in [(1, ids[0]), *([(2, ids[1])] if segunda_valida else [])]:
            pregunta = conn.execute(db.preguntas_conciliacion.insert().values(
                tipo="es_el_mismo", fuente="banco", fecha="2026-08-10", monto_centavos=-10000,
                ocurrencia_banco=ordinal, respuesta="si", respondida_en="2026-08-11T10:00:00",
            )).inserted_primary_key[0]
            elecciones_banco.guardar_eleccion_banco(conn, pregunta, ident)
        # Representa un respaldo cuyo importe cambió después de aquella decisión.
        sql(conn, "UPDATE movimientos SET monto_centavos=10300 WHERE id=?", (ids[0],))
    antes = componer_saldo(conn).saldo_actual()
    reporte = [fila(10, -10000)] * 2
    primero = importacion.importar(conn, reporte).conteos
    assert not primero.agregados and componer_saldo(conn).saldo_actual() == antes
    guardado = foto(conn)
    segundo = importacion.importar(conn, reporte).conteos
    assert not segundo.agregados and not segundo.preguntas and foto(conn) == guardado
    preguntas = sql(conn, "SELECT id,ocurrencia_banco FROM preguntas_conciliacion WHERE respuesta IS NULL ORDER BY ocurrencia_banco")
    primera = preguntas[0]["id"]
    if segunda_valida:
        # El ID de la ocurrencia 2 no se puede ofrecer ni elegir para la 1.
        with pytest.raises(importacion.ErrorConciliacion):
            importacion.responder_pregunta(conn, primera, True, ids[1])
        assert componer_saldo(conn).saldo_actual() == antes
        importacion.responder_pregunta(conn, primera, False)  # movimiento nuevo explícito
        assert componer_saldo(conn).saldo_actual() == antes - 10000
    else:
        importacion.responder_pregunta(conn, primera, True, ids[1])
        assert componer_saldo(conn).saldo_actual() == antes
        # La otra fila sigue preguntada: importar no decide que sea una nueva.
        assert len(importacion.preguntas_pendientes(conn)) == 1
    guardado, saldo_antes = foto(conn), componer_saldo(conn).saldo_actual()
    tercero = importacion.importar(conn, reporte).conteos
    assert not tercero.agregados and not tercero.preguntas
    assert foto(conn) == guardado and componer_saldo(conn).saldo_actual() == saldo_antes
    if sombra_descartada:
        assert movimiento(conn, ids[1])["borrado_en"] is not None


def test_sombra_reservada_por_pregunta_abierta_protege_la_fila_pendiente():
    fecha = date(2026, 8, 10)
    f = c.FilaBanco(fecha, -10000, "EJEMPLO")
    sombra = c.MovimientoApp(2, fecha, "compra", 10000, "EJEMPLO", "extracto", "sin_aviso",
                            fecha_banco=fecha, reservado=True)
    pregunta = c.PreguntaPendiente(9, fecha, -10000, ocurrencia_banco=1)
    p = c.conciliar([f, f], [], fecha, preguntas_pendientes=[pregunta],
                    descartes=[c.ReservaDescarte(sombra, f)])
    assert p.ya_preguntadas == [(f, pregunta.id)]
    assert [(q.ocurrencia_banco, q.candidatos) for q in p.preguntas] == [(2, ())]
    assert not p.agregar and not p.descartadas and not p.reduccion_ajuste


def test_deshacer_confirmacion_bancaria_restaura_reserva_sin_reactivar(conn):
    ident = del_correo(conn, 10, "compra", 10000)
    componer_descartes(conn).cambiar(ident)
    antes, historial, guardado = componer_saldo(conn).saldo_actual(), reservas(conn), foto(conn)
    r = gestion.confirmar(conn, gestion.analizar(conn, [fila(10, -10300)]))
    assert movimiento(conn, ident)["monto_centavos"] == 10300
    assert gestion.detalle(conn, r["id"])["se_puede_deshacer"]
    gestion.deshacer_importacion(conn, r["id"])
    assert componer_saldo(conn).saldo_actual() == antes and reservas(conn) == historial and movimiento(conn, ident)["borrado_en"]
    assert foto(conn) == guardado


def test_deshacer_pregunta_y_eleccion_vuelve_a_dejar_reserva_sin_reactivar(conn):
    ids = banco(conn, [fila(10, -10000)] * 2)
    componer_descartes(conn).cambiar(ids[0])
    antes = componer_saldo(conn).saldo_actual()
    r = gestion.confirmar(conn, gestion.analizar(conn, [fila(10, -10000)]))
    [p] = importacion.preguntas_pendientes(conn)
    gestion.responder(conn, [(p["id"], f"si:{ids[0]}")])
    assert elecciones_banco.listar_elecciones_banco(conn)
    gestion.deshacer_importacion(conn, r["id"])
    assert not elecciones_banco.listar_elecciones_banco(conn)
    assert movimiento(conn, ids[0])["borrado_en"] and componer_saldo(conn).saldo_actual() == antes


def test_adaptador_preguntas_ofrece_sombra_same_id_sin_reactivacion(conn):
    """Contrato de integración: no ocultar el candidato descartado."""
    ident = del_correo(conn, 10, "compra", 10000, "COMERCIO EJEMPLO")
    componer_descartes(conn).cambiar(ident)
    importacion.importar(conn, [fila(10, -10300, "PAGO")])
    antes, guardado, historial = componer_saldo(conn).saldo_actual(), foto(conn), reservas(conn)
    [p] = gestion.preguntas(conn)["preguntas"]
    assert [m["id"] for m in p["candidatos"]] == [ident]
    assert p["candidatos"][0]["descartado"] is True
    assert any(opcion["id"] == f"si:{ident}" for opcion in p["opciones"])
    assert foto(conn) == guardado and reservas(conn) == historial and componer_saldo(conn).saldo_actual() == antes


def test_parecido_dudoso_no_cambia_saldo_ni_inserta_y_respuesta_confirma_sombra(conn):
    ident = del_correo(conn, 10, "compra", 10000, "COMERCIO EJEMPLO")
    componer_descartes(conn).cambiar(ident)
    antes = componer_saldo(conn).saldo_actual()
    reporte = [fila(10, -10300, "PAGO")]
    assert importacion.importar(conn, reporte).conteos.preguntas == 1
    [p] = importacion.preguntas_pendientes(conn)
    with pytest.raises(DescarteNoPermitido):
        componer_descartes(conn).cambiar(ident, restaurar=True)
    importacion.responder_pregunta(conn, p["id"], True, ident)
    assert movimiento(conn, ident)["monto_centavos"] == 10300 and componer_saldo(conn).saldo_actual() == antes
    assert len(sql(conn, "SELECT id FROM movimientos")) == 1
    guardado = foto(conn)
    importacion.importar(conn, reporte)
    assert foto(conn) == guardado


def test_aviso_tardio_consume_sombra_sin_duplicar_y_gmail_repetido_no_muta(conn):
    [ident] = banco(conn, [fila(10, -10000)])
    componer_descartes(conn).cambiar(ident)
    antes = componer_saldo(conn).saldo_actual()
    assert recibir(conn) == importacion.AVISO_DESCARTADO
    assert componer_saldo(conn).saldo_actual() == antes and movimiento(conn, ident)["borrado_en"]
    assert movimiento(conn, ident)["gmail_id"] == "aviso-inventado"
    guardado, historial = foto(conn), reservas(conn)
    assert recibir(conn) == importacion.AVISO_YA_ESTABA
    assert foto(conn) == guardado and reservas(conn) == historial
    assert recibir(conn, "segundo-aviso-inventado") == importacion.AVISO_NUEVO
    componer_descartes(conn).cambiar(ident, restaurar=True)
    assert componer_saldo(conn).saldo_actual() == antes - 10000


def test_sync_gmail_descartado_mantiene_identidad_y_no_crea_otra_fila(conn):
    [ident] = banco(conn, [fila(10, -10000)])
    componer_descartes(conn).cambiar(ident)
    correos = {"aviso-inventado": _compra("aviso-inventado", "100,00", "TIENDA EJEMPLO", 10)}
    antes = componer_saldo(conn).saldo_actual()
    sincronizar(conn, ClienteFalso(correos))
    assert componer_saldo(conn).saldo_actual() == antes
    assert movimiento(conn, ident)["gmail_id"] == "aviso-inventado" and movimiento(conn, ident)["borrado_en"]
    guardado, historial = foto(conn), reservas(conn)
    cliente = ClienteFalso(correos)
    sincronizar(conn, cliente)
    assert foto(conn) == guardado and reservas(conn) == historial
    assert len(sql(conn, "SELECT id FROM movimientos")) == 1


def test_aviso_tardio_mezcla_activo_y_sombra_pregunta_y_no_modifica_saldo(conn):
    ids = banco(conn, [fila(10, -10000)] * 2)
    componer_descartes(conn).cambiar(ids[0])
    antes = componer_saldo(conn).saldo_actual()
    assert recibir(conn) == importacion.AVISO_PREGUNTA
    [p] = importacion.preguntas_pendientes(conn)
    importacion.responder_pregunta(conn, p["id"], True, ids[0])
    assert movimiento(conn, ids[0])["gmail_id"] == "aviso-inventado" and movimiento(conn, ids[0])["borrado_en"]
    assert componer_saldo(conn).saldo_actual() == antes and len(sql(conn, "SELECT id FROM movimientos")) == 2


def test_aviso_tardio_de_sombra_reservada_pregunta_antes_de_agregar_candidato(conn):
    ids = banco(conn, [fila(10, -10000)] * 2)
    componer_descartes(conn).cambiar(ids[0])
    importacion.importar(conn, [fila(10, -10000)])  # cobertura parcial: ambos candidatos
    antes = componer_saldo(conn).saldo_actual()
    assert recibir(conn) == importacion.AVISO_PREGUNTA
    assert componer_saldo(conn).saldo_actual() == antes and len(sql(conn, "SELECT id FROM movimientos")) == 2
    assert len(importacion.preguntas_pendientes(conn)) == 2


def test_120_filas_con_sombra_no_marcan_ausencia_el_dia_truncado(conn):
    ident = del_correo(conn, 10, "compra", 10000)
    componer_descartes(conn).cambiar(ident)
    otro = del_correo(conn, 10, "compra", 20000)
    reporte = [fila(10, -10000)] + [fila(11, -30000)] * 119
    r = importacion.importar(conn, reporte).conteos
    assert r.ya_estaban == 1 and r.agregados == 119 and not r.no_en_banco
    assert not movimiento(conn, otro)["no_en_banco"]


def test_cambio_de_contexto_rollback_completo_de_confirmacion(conn):
    ident = del_correo(conn, 10, "compra", 10000)
    componer_descartes(conn).cambiar(ident)
    with db.transaccion(conn):
        sql(conn, "UPDATE movimientos SET descripcion='OTRO EJEMPLO' WHERE id=?", (ident,))
    guardado, historial, antes = foto(conn), reservas(conn), componer_saldo(conn).saldo_actual()
    with pytest.raises(DescarteNoPermitido):
        importacion.importar(conn, [fila(10, -10300, "OTRO EJEMPLO")])
    assert foto(conn) == guardado and reservas(conn) == historial and componer_saldo(conn).saldo_actual() == antes


def test_segunda_importacion_concurrente_no_puede_intercalar_y_al_reintentar_no_duplica(conn, monkeypatch):
    ident = del_correo(conn, 10, "compra", 10000)
    componer_descartes(conn).cambiar(ident)
    otra = db.conectar(db.ruta_de(conn))
    otra.exec_driver_sql("PRAGMA busy_timeout=10")
    from finanzas.modulos.movimientos.descartes_aplicacion import OperarDescartes
    original = OperarDescartes.actualizar_respaldo_banco
    bloqueos = []
    def actualizar(*args, **kwargs):
        with pytest.raises(OperationalError):
            importacion.importar(otra, [fila(10, -10000)])
        bloqueos.append(True)
        original(*args, **kwargs)
    monkeypatch.setattr(OperarDescartes, "actualizar_respaldo_banco", actualizar)
    try:
        importacion.importar(conn, [fila(10, -10000)])
        assert bloqueos == [True]
        guardado = foto(conn)
        assert importacion.importar(otra, [fila(10, -10000)]).conteos.ya_estaban == 1
        assert foto(conn) == guardado
    finally:
        otra.close()


@settings(max_examples=25, deadline=None)
@given(n=st.integers(1, 6), descartados=st.integers(0, 6), nuevos=st.integers(0, 3), monto=st.integers(1, 100000))
def test_propiedad_idempotencia_multiplicidad_saldo_y_referencia(plantilla, n, descartados, nuevos, monto):
    with Base(plantilla) as conexion:
        reporte = [fila(10, -monto, referencia="*0001")] * n
        ids = banco(conexion, reporte)
        cantidad = min(n, descartados)
        for ident in ids[:cantidad]:
            componer_descartes(conexion).cambiar(ident)
        antes = componer_saldo(conexion).saldo_actual()
        reporte += [reporte[0]] * nuevos
        importacion.importar(conexion, reporte)
        guardado, historial = foto(conexion), reservas(conexion)
        assert componer_saldo(conexion).saldo_actual() == antes - nuevos * monto
        importacion.importar(conexion, reporte)
        assert foto(conexion) == guardado and reservas(conexion) == historial
        assert len(sql(conexion, "SELECT id FROM movimientos")) == n + nuevos
        assert all(r[0] == "*0001" for r in sql(conexion, "SELECT referencia FROM movimientos"))


@settings(max_examples=25, deadline=None)
@given(n=st.integers(1, 8), monto=st.integers(1, 100000), dia_ajuste=st.integers(1, 28))
def test_propiedad_reservas_no_tocan_ajuste_ni_generan_ausencias(n, monto, dia_ajuste):
    f = c.FilaBanco(date(2026, 8, 10), -monto, "EJEMPLO", "*0001")
    descartados = [c.ReservaDescarte(c.MovimientoApp(i + 1, f.fecha, "transferencia", monto,
        "*0001", "extracto", "sin_aviso", "*0001", f.fecha), f) for i in range(n)]
    p = c.conciliar([f] * n, [], date(2026, 8, 1), c.AjusteApp(100, date(2026, 8, dia_ajuste), 0), descartes=descartados)
    assert len(p.descartadas) == n
    assert not (p.agregar or p.confirmar or p.corregir or p.marcar or p.preguntas or p.reduccion_ajuste)


def test_no_al_aviso_respeta_la_fila_descartada_que_si_es_el(conn):
    """Ítem 45, caso D (D50): tras "no" a la pregunta de un aviso, si la fila que
    sí es él está descartada, el aviso la consume sin reactivarla."""
    banco(conn, [fila(10, -10300, "PAGO")])
    assert recibir(conn) == importacion.AVISO_PREGUNTA  # $100 parecido a $103, sin apoyo
    [p] = importacion.preguntas_pendientes(conn)
    importacion.importar(conn, [fila(11, -10000, "PAGO")])  # otro reporte: la fila que sí es el aviso
    [sombra] = sql(conn, "SELECT id FROM movimientos WHERE monto_centavos = 10000")
    componer_descartes(conn).cambiar(sombra[0])
    antes = componer_saldo(conn).saldo_actual()
    importacion.responder_pregunta(conn, p["id"], si=False)
    assert movimiento(conn, sombra[0])["gmail_id"] == "aviso-inventado"
    assert movimiento(conn, sombra[0])["borrado_en"]
    assert componer_saldo(conn).saldo_actual() == antes
    assert not sql(conn, "SELECT 1 FROM movimientos WHERE origen = 'gmail'")
