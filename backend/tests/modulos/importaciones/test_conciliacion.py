"""Motor de conciliación puro (ítem 29, D38 a D40, D45). Datos inventados."""

from __future__ import annotations

from datetime import date

import pytest

from finanzas.modulos.importaciones import motor as c
from finanzas.modulos.importaciones.motor import AjusteApp, FilaBanco, MovimientoApp, PreguntaPendiente

INICIO = date(2026, 8, 1)


def dia(n: int) -> date:
    return date(2026, 8, n)


_ids = iter(range(1, 10_000))


def correo(n, tipo, monto, descripcion="TIENDA EJEMPLO", **kw) -> MovimientoApp:
    return MovimientoApp(next(_ids), dia(n), tipo, monto, descripcion, c.ORIGEN_GMAIL, **kw)


def manual(n, monto, descripcion="Ingreso", **kw) -> MovimientoApp:
    return MovimientoApp(next(_ids), dia(n), c.TIPO_INGRESO, monto, descripcion, c.ORIGEN_MANUAL,
                         estado=kw.pop("estado", c.ESTADO_PROVISIONAL), **kw)


def fila(n, monto, descripcion="COMPRA EN  TIENDA EJEMPLO", referencia=None) -> FilaBanco:
    return FilaBanco(dia(n), monto, descripcion, referencia)


def primer_dia() -> FilaBanco:
    """Una fila del día 1: el día más antiguo de un reporte nunca marca
    "no está en el banco" (D51), así los días que se prueban no son el primero."""
    return FilaBanco(dia(1), -1, "COMISION INVENTADA", None)


def pares(lista):
    return sorted((p.fila.fecha.day, p.fila.monto_centavos, p.movimiento_id) for p in lista)


# --- Monto exacto y día ±1 -----------------------------------------------------------

def test_monto_exacto_mismo_dia_se_confirma():
    m = correo(5, "compra", 2590000)
    plan = c.conciliar([fila(5, -2590000)], [m], INICIO)
    assert pares(plan.confirmar) == [(5, -2590000, m.id)]
    assert not (plan.agregar or plan.preguntas or plan.marcar or plan.corregir)


@pytest.mark.parametrize("desfase", [-1, 1])
def test_desfase_de_un_dia_se_confirma(desfase):
    m = correo(10, "compra", 980000)
    plan = c.conciliar([fila(10 + desfase, -980000)], [m], INICIO)
    assert [p.movimiento_id for p in plan.confirmar] == [m.id]


def test_dos_dias_de_desfase_no_es_el_mismo():
    m = correo(10, "compra", 980000)
    plan = c.conciliar([fila(1, -5), fila(12, -980000)], [m], INICIO)
    assert plan.confirmar == [] and len(plan.agregar) == 2
    assert plan.marcar == [m.id]


def test_nunca_por_descripcion_ni_sentido_contrario():
    gasto = correo(5, "compra", 100000, "ALGO DISTINTO")
    plan = c.conciliar([fila(5, 100000, "ABONO EJEMPLO")], [gasto], INICIO)
    assert plan.confirmar == []  # un abono no confirma un gasto
    plan = c.conciliar([fila(5, -100000, "OTRO NOMBRE")], [gasto], INICIO)
    assert [p.movimiento_id for p in plan.confirmar] == [gasto.id]  # la descripción no importa


def test_prefiere_el_mismo_dia_cuando_hay_dos_candidatos():
    ayer, hoy = correo(9, "compra", 50000), correo(10, "compra", 50000)
    plan = c.conciliar([fila(10, -50000), fila(9, -50000)], [ayer, hoy], INICIO)
    assert pares(plan.confirmar) == [(9, -50000, ayer.id), (10, -50000, hoy.id)]


def test_emparejamiento_maximo_y_no_el_primero_que_aparece():
    # La fila del 10 podría tomar el del 9 o el del 11; la del 12 solo el del 11.
    m9, m11 = correo(9, "compra", 70000), correo(11, "compra", 70000)
    plan = c.conciliar([fila(10, -70000), fila(12, -70000)], [m9, m11], INICIO)
    assert pares(plan.confirmar) == [(10, -70000, m9.id), (12, -70000, m11.id)]
    assert plan.agregar == []


# --- Repeticiones -------------------------------------------------------------------------

def test_montos_repetidos_el_mismo_dia_se_cuentan_uno_a_uno():
    correos = [correo(4, "transferencia", 620000, "PERSONA EJEMPLO") for _ in range(2)]
    filas = [fila(4, -620000, "TRANSFERENCIAS A NEQUI") for _ in range(3)]
    plan = c.conciliar(filas, correos, INICIO)
    assert sorted(p.movimiento_id for p in plan.confirmar) == sorted(m.id for m in correos)
    assert len(plan.agregar) == 1  # el banco trae tres y el correo dos: falta una


def test_tres_iguales_en_el_correo_y_dos_en_el_banco():
    correos = [correo(4, "compra", 355000) for _ in range(3)]
    plan = c.conciliar([primer_dia(), fila(4, -355000), fila(4, -355000)], correos, INICIO)
    assert len(plan.confirmar) == 2 and len(plan.marcar) == 1


# --- Destino ------------------------------------------------------------------------------

def test_mismo_dia_y_monto_a_destinos_distintos_cada_uno_con_el_suyo():
    a = correo(4, "transferencia", 620000, "*3000000001")
    b = correo(4, "transferencia", 620000, "*3000000002")
    filas = [fila(4, -620000, "TRANSFERENCIAS A NEQUI", "*0002"),
             fila(4, -620000, "TRANSFERENCIAS A NEQUI", "*0001")]
    plan = c.conciliar(filas, [a, b], INICIO)
    assert {(p.fila.referencia, p.movimiento_id) for p in plan.confirmar} == {("*0001", a.id), ("*0002", b.id)}


def test_destinos_que_no_coinciden_no_son_el_mismo():
    a = correo(4, "transferencia", 620000, "*3000000001")
    plan = c.conciliar([primer_dia(), fila(4, -620000, "TRANSFERENCIAS A NEQUI", "*0009")], [a], INICIO)
    assert plan.confirmar == [] and plan.preguntas == []
    assert len(plan.agregar) == 2 and plan.marcar == [a.id]


def test_destino_desconocido_en_un_lado_empareja_por_dia_y_monto():
    bre_b = correo(4, "transferencia", 620000, "PERSONA EJEMPLO")  # sin dígitos
    plan = c.conciliar([fila(4, -620000, "TRANSFERENCIAS A NEQUI", "*0004")], [bre_b], INICIO)
    assert [p.movimiento_id for p in plan.confirmar] == [bre_b.id]


def test_el_destino_igual_gana_sobre_el_desconocido():
    desconocido = correo(4, "transferencia", 620000, "PERSONA EJEMPLO")
    igual = correo(4, "transferencia", 620000, "*3000000004")
    plan = c.conciliar([primer_dia(), fila(4, -620000, "TRANSF", "*0004")], [desconocido, igual], INICIO)
    assert [p.movimiento_id for p in plan.confirmar] == [igual.id]
    assert plan.marcar == [desconocido.id]


def test_destino_de_la_descripcion_del_correo():
    m = correo(4, "transferencia", 1, "*3000000004")
    assert c.destino(m) == "*0004"
    assert c.destino(correo(4, "transferencia", 1, "Pago QR")) is None
    assert c.destino(correo(4, "compra", 1, "*3000000004")) is None  # solo transferencias


# --- Montos parecidos ---------------------------------------------------------------------

def test_parecido_con_palabra_propia_se_corrige_al_monto_del_banco():
    m = correo(18, "compra", 950000, "WOMPI EJEMPLO")
    plan = c.conciliar([fila(18, -980000, "COMPRA EN  WOMPI EJEMPLO")], [m], INICIO)
    assert pares(plan.corregir) == [(18, -980000, m.id)]
    assert plan.preguntas == [] and plan.agregar == []


def test_parecido_con_destino_igual_se_corrige():
    m = correo(18, "transferencia", 600000, "*3000000005")
    plan = c.conciliar([fila(18, -610000, "TRANSFERENCIAS A NEQUI", "*0005")], [m], INICIO)
    assert pares(plan.corregir) == [(18, -610000, m.id)]


def test_parecido_sin_destino_ni_nombre_en_comun_se_pregunta():
    m = correo(18, "compra", 950000, "SUPERMERCADO INVENTADO")
    plan = c.conciliar([fila(18, -980000, "COMPRA EN  WOMPI EJEMPLO")], [m], INICIO)
    assert plan.corregir == [] and plan.agregar == [] and plan.marcar == []
    [pregunta] = plan.preguntas
    assert pregunta.tipo == c.PREGUNTA_ES_EL_MISMO and pregunta.candidatos == (m.id,)


def test_palabras_genericas_no_cuentan():
    m = correo(18, "compra", 950000, "COMPRA PAGO TRANSFERENCIA")
    plan = c.conciliar([fila(18, -980000, "COMPRA EN PAGO TRANSFERENCIA")], [m], INICIO)
    assert len(plan.preguntas) == 1


def test_parecido_con_varios_candidatos_se_pregunta():
    a, b = correo(18, "compra", 950000, "WOMPI EJEMPLO"), correo(18, "compra", 960000, "WOMPI EJEMPLO")
    plan = c.conciliar([fila(18, -980000, "COMPRA EN  WOMPI EJEMPLO")], [a, b], INICIO)
    [pregunta] = plan.preguntas
    assert pregunta.candidatos == tuple(sorted((a.id, b.id)))


def test_parecido_solo_el_mismo_dia_y_hasta_5_por_ciento_del_banco():
    m = correo(18, "compra", 950000, "WOMPI EJEMPLO")
    assert c.conciliar([fila(19, -980000, "WOMPI EJEMPLO")], [m], INICIO).corregir == []
    assert c.es_parecido(-1000000, 950000) and not c.es_parecido(-1000000, 949999)
    assert c.es_parecido(1000000, 1050000) and not c.es_parecido(1000000, 1050001)
    assert not c.es_parecido(1000000, 1000000)


def test_parecido_con_destinos_distintos_no_es_el_mismo():
    m = correo(18, "transferencia", 600000, "*3000000005")
    plan = c.conciliar([fila(18, -610000, "TRANSF", "*0006")], [m], INICIO)
    assert plan.preguntas == [] and len(plan.agregar) == 1


# --- Lo que el banco no trae ----------------------------------------------------------------

def test_lo_del_correo_dentro_de_las_fechas_que_el_banco_no_trae_queda_marcado():
    dentro, fuera = correo(10, "compra", 123400), correo(25, "compra", 123400)
    plan = c.conciliar([fila(5, -100), fila(20, -200)], [dentro, fuera], INICIO)
    assert plan.marcar == [dentro.id]


def test_un_marcado_que_luego_aparece_se_confirma_y_uno_ya_marcado_no_se_repite():
    ya = correo(10, "compra", 123400, no_en_banco=True)
    assert c.conciliar([fila(5, -100), fila(20, -200)], [ya], INICIO).marcar == []
    plan = c.conciliar([fila(10, -123400)], [ya], INICIO)
    assert [p.movimiento_id for p in plan.confirmar] == [ya.id]


@pytest.mark.parametrize("cantidad", [1, 2, 50, 119, 120, 121, 146, 300])
def test_el_dia_mas_antiguo_de_cualquier_reporte_no_marca(cantidad):
    """D51: el tope de filas del banco no se conoce; el primer día nunca marca."""
    del_primer_dia, del_segundo, del_ultimo = (correo(3, "compra", 777700), correo(4, "compra", 777700),
                                               correo(24, "compra", 777700))
    filas = [fila(3, -1)] + [fila(4 + i % 21, -(i + 10)) for i in range(cantidad - 1)]
    plan = c.conciliar(filas, [del_primer_dia, del_segundo, del_ultimo], INICIO)
    hasta = max(f.fecha for f in filas)
    esperado = [m.id for m in (del_segundo, del_ultimo) if m.fecha <= hasta]
    assert sorted(plan.marcar) == sorted(esperado)
    assert del_primer_dia.id not in plan.marcar


def test_el_primer_dia_del_reporte_no_marca_aunque_sea_anterior_al_inicio():
    """Si el reporte empieza antes de la fecha de inicio, su primer día ya no
    cuenta y el día de inicio sí marca."""
    del_inicio = correo(1, "compra", 777700)
    plan = c.conciliar([FilaBanco(date(2026, 7, 31), -1, "COMISION INVENTADA", None), fila(1, -3), fila(2, -5)],
                       [del_inicio], INICIO)
    assert plan.marcar == [del_inicio.id] and plan.anteriores == 1


def test_ingreso_provisional_que_no_aparece_queda_como_esta():
    m = manual(10, 5000000)
    plan = c.conciliar([fila(5, -100), fila(20, -200)], [m], INICIO)
    assert plan.marcar == [] and plan.confirmar == []


# --- Ingresos manuales (D39) --------------------------------------------------------------

def test_ingreso_manual_se_confirma_con_el_deposito_del_banco():
    m = manual(22, 16000000)
    plan = c.conciliar([fila(23, 16000000, "TRANSFERENCIA CTA SUC VIRTUAL", "*0002")], [m], INICIO)
    assert [p.movimiento_id for p in plan.confirmar] == [m.id] and plan.agregar == []


def test_ingreso_provisional_con_monto_parecido_se_corrige_o_se_pregunta():
    m = manual(22, 16000000, "Sueldo EMPRESA EJEMPLO")
    plan = c.conciliar([fila(22, 16200000, "TRANSF DE EMPRESA EJEMPLO")], [m], INICIO)
    assert pares(plan.corregir) == [(22, 16200000, m.id)]
    plan = c.conciliar([fila(22, 16200000, "TRANSFERENCIA CTA SUC VIRTUAL")], [m], INICIO)
    assert [p.candidatos for p in plan.preguntas] == [(m.id,)]


def test_lo_del_correo_se_prefiere_al_provisional():
    del_correo, provisional = correo(22, "ingreso", 16000000, "PERSONA EJEMPLO"), manual(22, 16000000)
    plan = c.conciliar([fila(22, 16000000)], [provisional, del_correo], INICIO)
    assert [p.movimiento_id for p in plan.confirmar] == [del_correo.id]


# --- Cobros acumulados por día (Transmilenio) -----------------------------------------------

def test_cobro_acumulado_por_dia_entra_como_una_sola_fila_por_dia():
    filas = [fila(n, -1065000, "COBRO VIAJE TRANSPORTE MASIVO") for n in (5, 6, 7)]
    plan = c.conciliar(filas, [], INICIO)
    assert [(f.fecha.day, f.monto_centavos) for f in plan.agregar] == [(5, -1065000), (6, -1065000), (7, -1065000)]
    assert all(c.tipo_de_fila(f) == c.TIPO_COMPRA for f in plan.agregar)


def test_cobro_acumulado_no_se_parte_contra_pasajes_sueltos():
    pasaje = correo(5, "compra", 355000, "COBRO VIAJE")
    plan = c.conciliar([fila(5, -1065000, "COBRO VIAJE TRANSPORTE MASIVO")], [pasaje], INICIO)
    assert plan.confirmar == [] and plan.corregir == [] and len(plan.agregar) == 1


# --- Lo que ya vino del banco: importar dos veces ----------------------------------------------

def test_fila_ya_importada_no_cambia_nada():
    respaldado = MovimientoApp(1, dia(5), "compra", 1065000, "COBRO", c.ORIGEN_EXTRACTO,
                               estado=c.ESTADO_SIN_AVISO, fecha_banco=dia(5))
    confirmado = correo(6, "compra", 2590000, estado=c.ESTADO_CONFIRMADO, fecha_banco=dia(7))
    plan = c.conciliar([fila(5, -1065000), fila(7, -2590000)], [respaldado, confirmado], INICIO)
    assert pares(plan.ya_estaban) == [(5, -1065000, 1), (7, -2590000, confirmado.id)]
    assert not plan.cambia_algo


def test_fila_que_espera_respuesta_no_se_vuelve_a_preguntar():
    plan = c.conciliar([fila(18, -980000)], [], INICIO, preguntas_pendientes=[PreguntaPendiente(7, dia(18), -980000)])
    assert plan.ya_preguntadas == [(fila(18, -980000), 7)] and not plan.cambia_algo


def test_candidato_reservado_por_una_pregunta_no_se_empareja_ni_se_marca():
    m = correo(18, "compra", 950000, reservado=True)
    plan = c.conciliar([fila(18, -950000), fila(19, -1)], [m], INICIO)
    assert plan.confirmar == [] and plan.marcar == []


# --- Fecha de inicio (D40) ----------------------------------------------------------------------

def test_filas_anteriores_a_la_fecha_de_inicio_se_cuentan_y_no_se_importan():
    plan = c.conciliar([fila(1, -100), fila(2, -200), fila(3, -300)], [], dia(3))
    assert plan.anteriores == 2 and [f.monto_centavos for f in plan.agregar] == [-300]


def test_movimientos_anteriores_a_la_fecha_de_inicio_no_se_usan():
    viejo = correo(2, "compra", 300)
    plan = c.conciliar([fila(3, -300)], [viejo], dia(3))
    assert plan.confirmar == [] and len(plan.agregar) == 1


# --- Último ajuste (D45) ------------------------------------------------------------------------

AJUSTE = AjusteApp(99, dia(20), -500000)


def test_lo_anterior_al_dia_del_ajuste_lo_reduce():
    plan = c.conciliar([fila(10, -300000), fila(11, 5000)], [], INICIO, AJUSTE)
    assert plan.ajuste_id == 99 and plan.reduccion_ajuste == -295000
    assert len(plan.agregar) == 2


def test_lo_del_mismo_dia_del_ajuste_se_pregunta_y_no_entra():
    plan = c.conciliar([fila(20, -300000)], [], INICIO, AJUSTE)
    assert plan.agregar == [] and plan.reduccion_ajuste == 0
    assert [(p.tipo, p.candidatos) for p in plan.preguntas] == [(c.PREGUNTA_YA_ESTABA, ())]


def test_lo_posterior_al_ajuste_no_lo_toca():
    plan = c.conciliar([fila(21, -300000)], [], INICIO, AJUSTE)
    assert plan.reduccion_ajuste == 0 and len(plan.agregar) == 1


def test_la_correccion_de_un_parecido_anterior_al_ajuste_lo_reduce():
    m = correo(18, "compra", 950000, "WOMPI EJEMPLO")
    plan = c.conciliar([fila(18, -980000, "WOMPI EJEMPLO")], [m], INICIO, AJUSTE)
    assert plan.reduccion_ajuste == -30000 and len(plan.corregir) == 1


def test_la_correccion_del_mismo_dia_del_ajuste_se_pregunta():
    m = correo(20, "compra", 950000, "WOMPI EJEMPLO")
    plan = c.conciliar([fila(20, -980000, "WOMPI EJEMPLO")], [m], INICIO, AJUSTE)
    assert plan.corregir == [] and [(p.tipo, p.candidatos) for p in plan.preguntas] == [(c.PREGUNTA_YA_ESTABA, (m.id,))]


def test_confirmar_un_monto_exacto_no_toca_el_ajuste():
    m = correo(20, "compra", 950000)
    plan = c.conciliar([fila(20, -950000)], [m], INICIO, AJUSTE)
    assert len(plan.confirmar) == 1 and plan.preguntas == [] and plan.reduccion_ajuste == 0


# --- Cada fila en un solo lugar --------------------------------------------------------------------

def test_tipo_de_las_filas_sin_aviso():
    assert c.tipo_de_fila(fila(1, 100)) == c.TIPO_INGRESO
    assert c.tipo_de_fila(fila(1, -100, referencia="*0001")) == c.TIPO_TRANSFERENCIA
    assert c.tipo_de_fila(fila(1, -100)) == c.TIPO_COMPRA


def test_palabras_propias_sin_tildes_ni_genericas():
    assert c.palabras_propias("COMPRA EN  Panadería EJEMPLO 123") == {"PANADERIA", "EJEMPLO"}


# --- Aviso que llega después de importar (D45) -----------------------------------------------------

def sin_aviso(n, tipo, monto, descripcion="COMPRA EN  TIENDA EJEMPLO", referencia=None, **kw):
    return MovimientoApp(next(_ids), dia(n), tipo, monto, descripcion, c.ORIGEN_EXTRACTO,
                         estado=c.ESTADO_SIN_AVISO, referencia=referencia, fecha_banco=dia(n), **kw)


def test_aviso_tardio_confirma_lo_que_entro_del_banco():
    b = sin_aviso(5, "compra", 2590000)
    d = c.emparejar_aviso(c.AvisoNuevo(dia(4), "compra", 2590000, "TIENDA EJEMPLO"), [b])
    assert (d.accion, d.movimiento_id) == ("confirmar", b.id)


def test_aviso_tardio_respeta_destino_y_repeticiones():
    a = sin_aviso(4, "transferencia", 620000, "TRANSFERENCIAS A NEQUI", "*0001")
    b = sin_aviso(4, "transferencia", 620000, "TRANSFERENCIAS A NEQUI", "*0002")
    d = c.emparejar_aviso(c.AvisoNuevo(dia(4), "transferencia", 620000, "*3000000002"), [a, b])
    assert d.movimiento_id == b.id
    d = c.emparejar_aviso(c.AvisoNuevo(dia(4), "transferencia", 620000, "*3000000009"), [a, b])
    assert d.accion == "nuevo"


def test_aviso_tardio_parecido_sin_apoyo_se_pregunta_y_sin_candidatos_es_nuevo():
    b = sin_aviso(18, "compra", 980000, "COMPRA EN  WOMPI EJEMPLO")
    d = c.emparejar_aviso(c.AvisoNuevo(dia(18), "compra", 950000, "SUPERMERCADO INVENTADO"), [b])
    assert (d.accion, d.candidatos) == ("preguntar", (b.id,))
    d = c.emparejar_aviso(c.AvisoNuevo(dia(18), "compra", 950000, "WOMPI EJEMPLO"), [b])
    assert (d.accion, d.movimiento_id) == ("confirmar", b.id)
    assert c.emparejar_aviso(c.AvisoNuevo(dia(18), "compra", 500000, "X"), [b]).accion == "nuevo"


def test_aviso_tardio_exacto_y_parecido_del_mismo_dia_se_pregunta():
    parecido = sin_aviso(18, "compra", 100000)
    exacto = sin_aviso(18, "compra", 98000)
    aviso = c.AvisoNuevo(dia(18), "compra", 98000, "AVISO INVENTADO")
    decision = c.emparejar_aviso(aviso, [parecido, exacto])
    assert (decision.accion, decision.candidatos) == ("preguntar", (parecido.id, exacto.id))


def test_aviso_tardio_incluye_parecido_si_hay_sombra_exacta():
    exacto = sin_aviso(18, "compra", 98000)
    parecido = sin_aviso(18, "compra", 100000)
    sombra = sin_aviso(18, "compra", 98000)
    aviso = c.AvisoNuevo(dia(18), "compra", 98000, "AVISO INVENTADO")
    reserva = c.ReservaDescarte(sombra, fila(18, -98000))
    decision = c.emparejar_aviso(aviso, [exacto, parecido], [reserva])
    assert (decision.accion, decision.candidatos) == (
        "preguntar", (exacto.id, parecido.id, sombra.id),
    )


def test_aviso_tardio_no_toca_lo_ya_confirmado_ni_lo_reservado():
    confirmado = MovimientoApp(1, dia(5), "compra", 100, "X", c.ORIGEN_EXTRACTO,
                               estado=c.ESTADO_CONFIRMADO, fecha_banco=dia(5))
    reservado = sin_aviso(5, "compra", 100, reservado=True)
    assert c.emparejar_aviso(c.AvisoNuevo(dia(5), "compra", 100, "X"), [confirmado, reservado]).accion == "nuevo"
