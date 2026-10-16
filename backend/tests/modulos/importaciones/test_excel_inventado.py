"""El Excel inventado generado por código (ítem 40, D43) es la base de las
pruebas de la v3: lo que se escribe con ``generar_excel`` lo lee el lector del
ítem 28 sin cambios. Incluye una primera prueba de propiedades con Hypothesis
(D44), que sirve de ejemplo para las de la conciliación (ítem 29)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import MovimientoExcel, leer_excel_movimientos
from tests.soporte import excel_inventado


def test_generado_tiene_los_63_movimientos_y_el_total():
    movimientos = leer_excel_movimientos(excel_inventado.generar_excel(),
                                         nombre_archivo="Movimientos.xlsx")
    assert len(movimientos) == len(excel_inventado.MOVIMIENTOS_INVENTADOS) == 63
    montos = [m.monto_centavos for m in movimientos]
    assert sum(montos) == excel_inventado.TOTAL_CENTAVOS
    assert sum(m for m in montos if m < 0) == excel_inventado.GASTOS_CENTAVOS
    assert sum(m for m in montos if m > 0) == excel_inventado.ABONOS_CENTAVOS


def test_no_se_escribe_ningun_archivo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert excel_inventado.generar_excel()[:2] == b"PK"
    assert list(tmp_path.iterdir()) == []


# Filas inventadas con la forma del reporte: descripción en mayúsculas de hasta
# 30 caracteres, referencia vacía o de dígitos y valor con signo y centavos.
_descripcion = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 *",
                       min_size=1, max_size=30).map(str.strip).filter(bool)
_referencia = st.one_of(st.none(), st.text(alphabet="0123456789", min_size=4, max_size=12))
_centavos = st.integers(min_value=-500_000_000, max_value=500_000_000).filter(bool)
_fila = st.tuples(st.dates(min_value=date(2024, 1, 1), max_value=date(2027, 12, 31)),
                  _descripcion, _referencia, _centavos)


@settings(max_examples=50, deadline=None)
@given(st.lists(_fila, max_size=20))
def test_lo_generado_se_lee_igual(filas):
    contenido = excel_inventado.generar_excel(
        [(f, d, r, float(Decimal(c) / 100)) for f, d, r, c in filas])
    leidos = leer_excel_movimientos(contenido)
    # De la Referencia solo quedan los últimos 4 dígitos (D37).
    assert leidos == [
        MovimientoExcel(f, c, d, None if r is None else "*" + r[-4:]) for f, d, r, c in filas]
    # Nunca el número completo en los campos de texto (no en el repr: un monto
    # como 50000000 contiene "00000" sin que eso sea una referencia).
    for (_f, _d, r, _c), leido in zip(filas, leidos):
        if r is not None and len(r) > 4:
            assert leido.referencia is not None and r not in leido.referencia
            assert r not in leido.descripcion or r in _d
