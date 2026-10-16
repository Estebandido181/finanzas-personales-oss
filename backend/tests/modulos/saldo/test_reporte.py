"""Pruebas del reporte mensual (ítem 06): flujo y composición de consulta.

Datos inventados.
"""

from __future__ import annotations
from finanzas.bootstrap.saldo import componer_saldo
from finanzas.bootstrap.reporte import componer_reporte
from finanzas.infraestructura.persistencia import lectura_consistente

from datetime import datetime

import pytest

from finanzas import db
from finanzas.compartido import hora
from finanzas.flujos import reporte
from finanzas.flujos.reporte import ErrorReporte, GastoCategoria
from tests.soporte.ayudas_db import sql

_n = iter(range(1, 100_000))


@pytest.fixture
def conn(tmp_path):
    c = db.conectar(str(tmp_path / "reporte.db"))
    db.inicializar(c)
    yield c
    c.close()


def _cat(conn, nombre):
    return sql(conn, "SELECT id FROM categorias WHERE nombre = ?", (nombre,)).fetchone()[0]


def _mov(conn, fecha, monto, tipo="compra", descripcion="TIENDA EJEMPLO", categoria=None):
    manual = tipo in ("ingreso", "ajuste")
    with db.transaccion(conn):
        return sql(
            conn,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, gmail_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                fecha,
                monto,
                tipo,
                descripcion,
                _cat(conn, categoria) if categoria else None,
                "manual" if manual else "gmail",
                None if manual else f"r-{next(_n)}",
            ),
        ).lastrowid


@pytest.fixture
def septiembre(conn):
    """Un mes con varias categorías, gastos sin categoría, ingresos, ajustes y
    movimientos justo fuera del mes. Devuelve lo esperado, sumado a mano."""
    _mov(conn, "2026-09-02T08:15:00", 12_345_67, descripcion="MERCADO EJEMPLO", categoria="Mercado")
    _mov(conn, "2026-09-10T19:00:00", 4_000_00, descripcion="MERCADO EJEMPLO 2", categoria="Mercado")
    _mov(conn, "2026-09-05T13:30:00", 8_500_50, descripcion="RESTAURANTE EJEMPLO", categoria="Restaurantes")
    _mov(conn, "2026-09-07T07:00:00", 2_150_00, "transferencia", "*1234", categoria="Transporte")
    _mov(conn, "2026-09-12T10:00:00", 99_99, descripcion="COMERCIO SIN REGLA")  # sin categoría
    _mov(conn, "2026-09-20T21:45:00", 3_000_01, "transferencia", "*9876")  # sin categoría
    _mov(conn, "2026-09-15T09:00:00", 5_000_000_00, "ingreso", "Salario (ejemplo)")
    _mov(conn, "2026-09-25T18:00:00", -4_300_00, "ajuste", "Ajuste de saldo")
    _mov(conn, "2026-09-26T18:00:00", 1_000_00, "ajuste", "Ajuste de saldo")
    # Fuera del mes: no cuentan.
    _mov(conn, "2026-08-31T23:59:59", 777_77, descripcion="AGOSTO", categoria="Mercado")
    _mov(conn, "2026-10-01T00:00:00", 888_88, descripcion="OCTUBRE", categoria="Mercado")
    return {
        "Mercado": 12_345_67 + 4_000_00,
        "Restaurantes": 8_500_50,
        "Transporte": 2_150_00,
        "Sin categorizar": 99_99 + 3_000_01,
    }


# --- Totales ------------------------------------------------------------------------------

def test_por_categoria_suma_exactamente_el_total(conn, septiembre):
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    a_mano = sum(septiembre.values())
    assert informe.total_gasto_centavos == a_mano == 30_096_17
    assert sum(g.centavos for g in informe.por_categoria) == informe.total_gasto_centavos
    assert all(isinstance(g.centavos, int) for g in informe.por_categoria)
    assert {g.nombre: g.centavos for g in informe.por_categoria} == septiembre


def test_total_es_el_de_gasto_entre(conn, septiembre):
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert informe.total_gasto_centavos == componer_saldo(conn).gasto_entre(datetime(2026, 9, 1), datetime(2026, 10, 1)
    )


def test_ingresos_y_ajustes_no_cuentan_como_gasto(conn):
    _mov(conn, "2026-09-15T09:00:00", 5_000_000_00, "ingreso", "Salario (ejemplo)")
    _mov(conn, "2026-09-25T18:00:00", -4_300_00, "ajuste", "Ajuste de saldo")
    _mov(conn, "2026-09-26T18:00:00", 1_000_00, "ajuste", "Ajuste de saldo")
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert informe.total_gasto_centavos == 0
    assert informe.por_categoria == []
    # Sí aparecen en la lista, marcados como no gasto. El ingreso sin
    # categoría está pendiente (ítem 15); el ajuste no lleva categoría.
    assert len(informe.movimientos) == 3
    assert all(not m.es_gasto for m in informe.movimientos)
    assert {m.tipo: m.categoria for m in informe.movimientos if m.tipo == "ingreso"} == {
        "ingreso": "Sin categorizar"
    }
    assert all(m.categoria == "—" for m in informe.movimientos if m.tipo == "ajuste")


def test_ingreso_con_categoria_no_cuenta_como_gasto(conn):
    # Ítem 15: un ingreso categorizado muestra su categoría, pero nunca es gasto.
    _mov(conn, "2026-09-15T09:00:00", 1_000_00, "ingreso", "Ingreso", categoria="Sueldo")
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert informe.total_gasto_centavos == 0
    assert informe.por_categoria == []
    assert informe.total_ingresos_centavos == 1_000_00
    movimiento = informe.movimientos[0]
    assert (movimiento.categoria, movimiento.categoria_clase, movimiento.es_gasto) == ("Sueldo", "ingreso", False)
    assert not movimiento.pendiente


def test_un_ajuste_nunca_muestra_categoria(conn):
    # Aunque una base vieja trajera una categoría en un ajuste.
    _mov(conn, "2026-09-15T09:00:00", -1_000_00, "ajuste", "Ajuste", categoria="Otros")
    movimiento = componer_reporte(conn).reporte_mensual(2026, 9).movimientos[0]
    assert (movimiento.categoria, movimiento.categoria_id, movimiento.pendiente) == ("—", None, False)


def test_sin_categoria_aparece_como_sin_categorizar(conn, septiembre):
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    sin = [g for g in informe.por_categoria if g.nombre == "Sin categorizar"]
    assert sin == [GastoCategoria("Sin categorizar", 3_100_00, sin[0].porcentaje)]
    assert (sin[0].categoria_id, sin[0].color, sin[0].icono) == (None, None, None)
    etiquetas = {m.descripcion: m.categoria for m in informe.movimientos}
    assert etiquetas["COMERCIO SIN REGLA"] == "Sin categorizar"
    assert etiquetas["*9876"] == "Sin categorizar"
    assert etiquetas["MERCADO EJEMPLO"] == "Mercado"
    assert etiquetas["Salario (ejemplo)"] == "Sin categorizar"  # ingreso pendiente (ítem 15)


def test_no_incluye_categorias_sin_gasto(conn, septiembre):
    nombres = {g.nombre for g in componer_reporte(conn).reporte_mensual(2026, 9).por_categoria}
    assert "Salud" not in nombres and "Otros" not in nombres


def test_por_categoria_ordenada_de_mayor_a_menor(conn, septiembre):
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert [g.nombre for g in informe.por_categoria] == [
        "Mercado", "Restaurantes", "Sin categorizar", "Transporte",
    ]


def test_empate_se_ordena_por_nombre(conn):
    _mov(conn, "2026-09-02T08:00:00", 100, categoria="Salud")
    _mov(conn, "2026-09-02T09:00:00", 100, categoria="Compras")
    nombres = [g.nombre for g in componer_reporte(conn).reporte_mensual(2026, 9).por_categoria]
    assert nombres == ["Compras", "Salud"]


def test_porcentajes_redondeados_a_un_decimal(conn):
    _mov(conn, "2026-09-02T08:00:00", 1, categoria="Mercado")
    _mov(conn, "2026-09-02T09:00:00", 2, categoria="Salud")
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert [g.porcentaje for g in informe.por_categoria] == [66.7, 33.3]


def test_porcentaje_redondea_la_mitad_hacia_arriba(conn):
    # 1/8 = 12,5 % exacto; 1/16 = 6,25 % -> 6,3 %.
    _mov(conn, "2026-09-02T08:00:00", 1, categoria="Mercado")
    _mov(conn, "2026-09-02T09:00:00", 15, categoria="Salud")
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert {g.nombre: g.porcentaje for g in informe.por_categoria} == {"Salud": 93.8, "Mercado": 6.3}


def test_una_sola_categoria_es_el_100(conn):
    _mov(conn, "2026-09-02T08:00:00", 123_45, categoria="Mercado")
    (unica,) = componer_reporte(conn).reporte_mensual(2026, 9).por_categoria
    assert (unica.centavos, unica.porcentaje) == (123_45, 100.0)


def test_mes_sin_datos(conn):
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert informe.total_gasto_centavos == 0
    assert informe.por_categoria == []
    assert informe.movimientos == []
    assert (informe.anio, informe.mes) == (2026, 9)


def test_otro_mes_con_datos_no_se_mezcla(conn, septiembre):
    informe = componer_reporte(conn).reporte_mensual(2026, 8)
    assert informe.total_gasto_centavos == 777_77
    assert [m.descripcion for m in informe.movimientos] == ["AGOSTO"]


def test_no_escribe_nada(conn, septiembre):
    antes = sql(conn, "SELECT * FROM movimientos ORDER BY id").fetchall()
    componer_reporte(conn).reporte_mensual(2026, 9)
    assert sql(conn, "SELECT * FROM movimientos ORDER BY id").fetchall() == antes
    assert not db.en_transaccion(conn)


# --- Lista de movimientos --------------------------------------------------------------

def test_movimientos_del_mes_incluye_todos_los_tipos(conn, septiembre):
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    tipos = sorted(m.tipo for m in informe.movimientos)
    assert tipos == ["ajuste", "ajuste", "compra", "compra", "compra", "compra",
                     "ingreso", "transferencia", "transferencia"]
    assert "AGOSTO" not in {m.descripcion for m in informe.movimientos}
    assert "OCTUBRE" not in {m.descripcion for m in informe.movimientos}
    ajuste = next(m for m in informe.movimientos if m.monto_centavos < 0)
    assert (ajuste.tipo, ajuste.monto_centavos, ajuste.es_gasto) == ("ajuste", -4_300_00, False)
    compras = [m for m in informe.movimientos if m.tipo in ("compra", "transferencia")]
    assert all(m.es_gasto for m in compras)


def test_movimientos_de_la_mas_reciente_a_la_mas_antigua(conn, septiembre):
    fechas = [m.fecha_hora for m in componer_reporte(conn).reporte_mensual(2026, 9).movimientos]
    assert fechas == sorted(fechas, reverse=True)
    assert fechas[0] == "2026-09-26T18:00:00"
    assert fechas[-1] == "2026-09-02T08:15:00"


def test_misma_fecha_el_ultimo_registrado_primero(conn):
    primero = _mov(conn, "2026-09-02T08:00:00", 100, descripcion="A")
    segundo = _mov(conn, "2026-09-02T08:00:00", 200, descripcion="B")
    ids = [m.id for m in componer_reporte(conn).reporte_mensual(2026, 9).movimientos]
    assert ids == [segundo, primero]


# --- Límites del mes ---------------------------------------------------------------------

@pytest.mark.parametrize(
    ("anio", "mes", "desde", "hasta"),
    [
        (2026, 9, datetime(2026, 9, 1), datetime(2026, 10, 1)),
        (2026, 12, datetime(2026, 12, 1), datetime(2027, 1, 1)),
        (2028, 2, datetime(2028, 2, 1), datetime(2028, 3, 1)),
        (2000, 1, datetime(2000, 1, 1), datetime(2000, 2, 1)),
        (2099, 12, datetime(2099, 12, 1), datetime(2100, 1, 1)),
    ],
)
def test_limites_del_mes(anio, mes, desde, hasta):
    assert reporte.limites_del_mes(anio, mes) == (desde, hasta)


@pytest.mark.parametrize(("anio", "mes"), [(2026, 0), (2026, 13), (1999, 12), (2100, 1), ("2026", 9), (2026, True)])
def test_limites_de_un_mes_invalido(anio, mes):
    with pytest.raises(ErrorReporte):
        reporte.limites_del_mes(anio, mes)


@pytest.mark.parametrize(
    ("anio", "mes", "primero", "ultimo", "siguiente"),
    [
        (2026, 9, "2026-09-01T00:00:00", "2026-09-30T23:59:59", "2026-10-01T00:00:00"),
        # Febrero de año bisiesto: el 29 cuenta.
        (2028, 2, "2028-02-01T00:00:00", "2028-02-29T23:59:59", "2028-03-01T00:00:00"),
        # Febrero de año no bisiesto.
        (2026, 2, "2026-02-01T00:00:00", "2026-02-28T23:59:59", "2026-03-01T00:00:00"),
        # Diciembre pasa a enero del año siguiente.
        (2026, 12, "2026-12-01T00:00:00", "2026-12-31T23:59:59", "2027-01-01T00:00:00"),
    ],
)
def test_bordes_del_mes(conn, anio, mes, primero, ultimo, siguiente):
    a = _mov(conn, primero, 1_00, categoria="Mercado")
    b = _mov(conn, ultimo, 10_00)
    c = _mov(conn, siguiente, 100_00, categoria="Mercado")
    informe = componer_reporte(conn).reporte_mensual(anio, mes)
    assert informe.total_gasto_centavos == 11_00
    assert sum(g.centavos for g in informe.por_categoria) == 11_00
    assert {m.id for m in informe.movimientos} == {a, b}
    # El de las 00:00:00 del mes siguiente cuenta en ese mes.
    anio_sig, mes_sig = reporte.mes_siguiente(anio, mes)
    assert [m.id for m in componer_reporte(conn).reporte_mensual(anio_sig, mes_sig).movimientos] == [c]


def test_un_segundo_antes_del_mes_no_cuenta(conn):
    _mov(conn, "2026-08-31T23:59:59", 5_00)
    assert componer_reporte(conn).reporte_mensual(2026, 9).total_gasto_centavos == 0


def test_29_de_febrero_en_bisiesto(conn):
    _mov(conn, "2028-02-29T12:00:00", 5_00, categoria="Salud")
    informe = componer_reporte(conn).reporte_mensual(2028, 2)
    assert informe.total_gasto_centavos == 5_00
    assert componer_reporte(conn).reporte_mensual(2028, 3).total_gasto_centavos == 0


# --- Navegación y nombres ----------------------------------------------------------------

def test_mes_siguiente_y_anterior():
    assert reporte.mes_siguiente(2026, 12) == (2027, 1)
    assert reporte.mes_siguiente(2026, 9) == (2026, 10)
    assert reporte.mes_anterior(2027, 1) == (2026, 12)
    assert reporte.mes_anterior(2026, 9) == (2026, 8)


def test_nombre_del_mes_en_espanol():
    assert reporte.nombre_mes(2026, 9) == "septiembre de 2026"
    assert reporte.nombre_mes(2027, 1) == "enero de 2027"
    assert reporte.nombre_mes(2026, 12) == "diciembre de 2026"


def test_texto_mes():
    assert reporte.texto_mes(2026, 9) == "2026-09"


def test_en_rango():
    assert reporte.en_rango(2000, 1) and reporte.en_rango(2099, 12)
    assert not reporte.en_rango(1999, 12) and not reporte.en_rango(2100, 1)


def test_mes_actual_usa_la_hora_de_colombia(monkeypatch):
    # 1 de octubre a las 03:00 UTC es todavía 30 de septiembre en Colombia.
    monkeypatch.setattr(hora, "ahora_colombia", lambda: datetime(2026, 9, 30, 22, 0))
    assert reporte.mes_actual() == (2026, 9)
    monkeypatch.setattr(hora, "ahora_colombia", lambda: datetime(2027, 1, 1, 0, 0))
    assert reporte.mes_actual() == (2027, 1)


# --- leer_mes ------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("2026-09", (2026, 9)),
        ("2026-12", (2026, 12)),
        ("2027-01", (2027, 1)),
        ("2000-01", (2000, 1)),
        ("2099-12", (2099, 12)),
    ],
)
def test_leer_mes_valido(texto, esperado):
    assert reporte.leer_mes(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "2026",
        "2026-9",
        "2026-00",
        "2026-13",
        "1999-12",
        "2100-01",
        "26-09",
        "2026/09",
        "2026-09-01",
        " 2026-09",
        "2026-09 ",
        "2026-09\n",
        "+2026-09",
        "2026--9",
        "abcd-ef",
        "２０２６-０９",  # cifras de ancho completo (no ASCII)
        "٢٠٢٦-٠٩",  # cifras arábigo-índicas
        None,
        202609,
    ],
)
def test_leer_mes_invalido(texto):
    with pytest.raises(ErrorReporte, match="Mes no válido"):
        reporte.leer_mes(texto)


# --- Transacción de lectura --------------------------------------------------------------

def test_lectura_consistente_abre_y_cierra_su_transaccion(conn):
    assert not db.en_transaccion(conn)
    with lectura_consistente(conn):
        assert db.en_transaccion(conn)
    assert not db.en_transaccion(conn)


def test_lectura_consistente_reutiliza_la_transaccion_de_quien_llama(conn):
    # Quien llama ya tiene una transacción abierta con un cambio sin confirmar:
    # el reporte lo ve (misma transacción) y no la cierra ni la confirma.
    # (No se usa ``_mov``: su ``with conn`` confirmaría la transacción.)
    sql(conn, "BEGIN")
    sql(
        conn,
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen, gmail_id) "
        "VALUES ('2026-09-03T10:00:00', 500, 'compra', 'SIN CONFIRMAR', 'gmail', 'tx-1')"
    )
    with lectura_consistente(conn):
        assert db.en_transaccion(conn)
    assert db.en_transaccion(conn)  # sigue abierta: no la cerró
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert informe.total_gasto_centavos == 5_00
    assert db.en_transaccion(conn)
    conn.rollback()  # quien llama decide: al deshacer, el movimiento no quedó guardado
    assert componer_reporte(conn).reporte_mensual(2026, 9).total_gasto_centavos == 0


# --- Ingresos del mes (ítem 13) --------------------------------------------------------------

def test_ingresos_del_mes_solo_tipo_ingreso(conn, septiembre):
    # Ingresos de Gmail y manuales en el mes; en los bordes de otros meses no cuentan.
    _mov(conn, "2026-09-01T00:00:00", 160_000_00, "ingreso", "PERSONA EJEMPLO")
    with db.transaccion(conn):
        sql(conn, "UPDATE movimientos SET origen = 'gmail', gmail_id = 'r-ing-1' WHERE descripcion = 'PERSONA EJEMPLO'")
    _mov(conn, "2026-09-30T23:59:59", 25_000_01, "ingreso", "Efectivo (ejemplo)")
    _mov(conn, "2026-08-31T23:59:59", 1_111_11, "ingreso", "Agosto (ejemplo)")
    _mov(conn, "2026-10-01T00:00:00", 2_222_22, "ingreso", "Octubre (ejemplo)")
    gasto_antes = 30_096_17

    informe = componer_reporte(conn).reporte_mensual(2026, 9)

    # Los ajustes (uno negativo y uno positivo) no son ingreso ni gasto.
    assert informe.total_ingresos_centavos == 5_000_000_00 + 160_000_00 + 25_000_01
    assert informe.total_gasto_centavos == gasto_antes
    desde, hasta = reporte.limites_del_mes(2026, 9)
    assert informe.total_ingresos_centavos == componer_saldo(conn).ingresos_entre(desde, hasta)
    assert isinstance(informe.total_ingresos_centavos, int)


def test_mes_sin_ingresos_da_cero(conn, septiembre):
    assert componer_reporte(conn).reporte_mensual(2026, 8).total_ingresos_centavos == 0
    assert componer_reporte(conn).reporte_mensual(2026, 11).total_ingresos_centavos == 0


def test_ingresos_del_mes_cuadran_con_el_saldo(conn, septiembre):
    # La misma regla que saldo_actual: saldo = inicial + ingresos − gasto + ajustes.
    with db.transaccion(conn):
        sql(conn, "INSERT INTO configuracion_saldo VALUES (1, 1000000, '2026-09-01')")
        # Solo septiembre (la fecha de inicio ya deja fuera agosto).
        sql(conn, "DELETE FROM movimientos WHERE fecha_hora >= '2026-10-01'")
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    ajustes = -4_300_00 + 1_000_00
    assert componer_saldo(conn).saldo_actual() == (
        1000000 + informe.total_ingresos_centavos - informe.total_gasto_centavos + ajustes
    )
