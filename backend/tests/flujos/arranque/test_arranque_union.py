"""Oráculos de multiconjuntos, repetición y centavos del ítem31."""
from collections import Counter
from datetime import date
import pytest
from hypothesis import given, settings, strategies as st
from finanzas.flujos.historial import unir_archivos, calcular_saldo_inicial, identidad, ErrorArranque
from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import MovimientoExcel


def fila(dia=1, monto=-100, descripcion="TIENDA INVENTADA", ref=None):
    return MovimientoExcel(date(2026, 7, dia), monto, descripcion, ref)


def test_no_confunde_repeticiones_reales_con_solapamiento():
    a = fila()
    r = unir_archivos([[a, a], [fila(descripcion="TIENDA RECORTADA"), a]])
    assert len(r.filas) == 2
    assert r.solapadas == 2


def test_identidad_conserva_destinos_distintos_y_signos():
    r = unir_archivos([[fila(ref="*1234"), fila(ref="*5678"), fila(monto=100)]])
    assert len(r.filas) == 3


def test_frontera_truncada_se_conserva_por_archivo():
    r = unir_archivos([[fila(1)] * 119 + [fila(2)], [fila(20)] * 119 + [fila(21)]])
    assert r.cobertura == ((date(2026, 7, 2), date(2026, 7, 2)), (date(2026, 7, 21), date(2026, 7, 21)))
    assert r.huecos == ((date(2026, 7, 3), date(2026, 7, 19)),)
    assert r.truncados == 2


def test_el_primer_dia_de_cada_archivo_no_acredita_pero_otro_archivo_si():
    """D51: ningún archivo acredita su día más antiguo, tenga las filas que tenga;
    otro archivo que traiga ese día después de su propio primer día sí lo acredita."""
    for cantidad in (2, 50, 120, 146):
        assert unir_archivos([[fila(1)] + [fila(2)] * (cantidad - 1)]).cobertura == (
            (date(2026, 7, 2), date(2026, 7, 2)),)
    r = unir_archivos([[fila(2)] * 120, [fila(1), fila(2)]])
    assert r.cobertura == ((date(2026, 7, 2), date(2026, 7, 2)),)
    assert unir_archivos([[fila(1)] * 146]).cobertura == ()


def test_reportes_truncados_mismo_dia_no_inventan_ocurrencias_indistinguibles():
    historia = unir_archivos([[fila()] * 120, [fila(descripcion="RECORTADO INVENTADO")] * 120])
    assert len(historia.filas) == 120 and historia.truncados == 2
    assert historia.cobertura == ()
    assert calcular_saldo_inicial(historia, 100000)["cobertura_verificada"] is False


def test_calculo_no_promete_cobertura_total_y_muestra_huecos_posibles():
    r = calcular_saldo_inicial(unir_archivos([[fila(1, -501)], [fila(20, 1234)]]), 10000)
    assert r["saldo_inicial_centavos"] == 9267
    assert r["huecos"] == [{"desde": "2026-07-02", "hasta": "2026-07-19"}]
    assert r["cobertura_verificada"] is False


@pytest.mark.parametrize("saldo", [True, 1.0, -1, "100"])
def test_no_acepta_float_bool_o_saldo_negativo(saldo):
    with pytest.raises(ErrorArranque):
        calcular_saldo_inicial(unir_archivos([[fila()]]), saldo)


def test_no_acepta_calculo_negativo_ni_sin_movimientos():
    with pytest.raises(ErrorArranque):
        calcular_saldo_inicial(unir_archivos([[fila(monto=200)]]), 100)
    with pytest.raises(ErrorArranque):
        calcular_saldo_inicial(unir_archivos([[]]), 100)


filas = st.tuples(st.integers(1, 28), st.integers(-20, 20).filter(bool),
    st.sampled_from([None, "*1234", "*5678"])).map(lambda x: fila(x[0], x[1], ref=x[2]))


@settings(max_examples=300)
@given(st.lists(st.lists(filas, max_size=30), min_size=1, max_size=5))
def test_union_contra_oraculo_maximo_y_permutacion(archivos):
    r = unir_archivos(archivos)
    claves = {identidad(f) for a in archivos for f in a}
    esperado = {k: max(sum(identidad(f) == k for f in a) for a in archivos) for k in claves}
    assert Counter(map(identidad, r.filas)) == esperado
    assert unir_archivos([list(reversed(a)) for a in reversed(archivos)]) == r
    assert unir_archivos([*archivos, archivos[0]]).filas == r.filas


@settings(max_examples=300)
@given(st.lists(filas, min_size=1, max_size=50), st.integers(1000, 100000000))
def test_saldo_inicial_mas_historia_da_objetivo(archivo, objetivo):
    historia = unir_archivos([archivo])
    vista = calcular_saldo_inicial(historia, objetivo)
    assert vista["saldo_inicial_centavos"] + sum(f.monto_centavos for f in historia.filas) == objetivo
