"""Casos borde del reporte mensual (ítem 06).

Complementa ``test_reporte.py``: redondeo de porcentajes, meses con solo
ingresos/ajustes o solo "Sin categorizar", transferencias categorizadas,
límites de meses (bisiestos y cambio de año), rendimiento con 500
movimientos y consistencia frente a una escritura concurrente. Los valores
raros de ``?mes=`` y la CSP se prueban en ``test_web.py`` y en las pruebas
de la API.

Todos los datos son inventados.
"""

from __future__ import annotations
from finanzas.bootstrap.reporte import componer_reporte
from finanzas.modulos.saldo.aplicacion import OperarSaldo

import random
import sqlite3
import threading
import time
from decimal import ROUND_HALF_UP, Decimal

import pytest

from finanzas import db
from finanzas.flujos import reporte
from tests.soporte.ayudas_db import sql


_n = iter(range(1, 1_000_000))


# --- Ayudas --------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    c = db.conectar(str(tmp_path / "bordes.db"))
    db.inicializar(c)
    yield c
    c.close()


def _cat_id(conn, nombre):
    return sql(conn, "SELECT id FROM categorias WHERE nombre = ?", (nombre,)).fetchone()[0]


def _insertar(conn, fecha, monto, tipo="compra", descripcion="COMERCIO INVENTADO", categoria=None):
    manual = tipo in ("ingreso", "ajuste")
    return sql(
        conn,
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, gmail_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            fecha,
            monto,
            tipo,
            descripcion,
            _cat_id(conn, categoria) if categoria else None,
            "manual" if manual else "gmail",
            None if manual else f"borde-{next(_n)}",
        ),
    ).lastrowid


def _mov(conn, *args, **kwargs):
    with db.transaccion(conn):
        return _insertar(conn, *args, **kwargs)


def _redondeo_exacto(centavos, total):
    return float((Decimal(centavos) * 100 / Decimal(total)).quantize(Decimal("0.1"), ROUND_HALF_UP))


# --- Porcentajes -----------------------------------------------------------------------

def test_tres_partes_iguales_no_suman_100_pero_el_total_es_exacto(conn):
    for categoria in ("Mercado", "Salud", "Transporte"):
        _mov(conn, "2026-09-10T10:00:00", 1_000_00, categoria=categoria)
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert [g.porcentaje for g in informe.por_categoria] == [33.3, 33.3, 33.3]
    assert round(sum(g.porcentaje for g in informe.por_categoria), 1) == 99.9
    assert sum(g.centavos for g in informe.por_categoria) == informe.total_gasto_centavos == 3_000_00


def test_seis_partes_iguales_suman_mas_de_100(conn):
    for categoria in ("Mercado", "Salud", "Transporte", "Compras", "Otros", "Restaurantes"):
        _mov(conn, "2026-09-10T10:00:00", 1, categoria=categoria)
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert all(g.porcentaje == 16.7 for g in informe.por_categoria)
    assert round(sum(g.porcentaje for g in informe.por_categoria), 1) == 100.2
    assert sum(g.centavos for g in informe.por_categoria) == informe.total_gasto_centavos == 6


def test_muchos_movimientos_aleatorios_total_exacto_y_porcentajes_bien_redondeados(conn):
    azar = random.Random(20260929)
    categorias = list(db.CATEGORIAS_FIJAS) + [None]
    with db.transaccion(conn):
        for i in range(300):
            _insertar(
                conn,
                f"2026-09-{azar.randint(1, 30):02d}T{azar.randint(0, 23):02d}:{azar.randint(0, 59):02d}:00",
                azar.randint(1, 3_000_000_00),
                azar.choice(["compra", "transferencia"]),
                f"COMERCIO {i}",
                azar.choice(categorias),
            )
            if i % 10 == 0:
                _insertar(conn, "2026-09-15T12:00:00", azar.randint(1, 10**9), "ingreso", "INGRESO X")
                _insertar(conn, "2026-09-16T12:00:00", -azar.randint(1, 10**7), "ajuste", "AJUSTE X")
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    a_mano = sql(
        conn,
        "SELECT SUM(monto_centavos) FROM movimientos WHERE tipo IN ('compra','transferencia')"
    ).fetchone()[0]
    assert informe.total_gasto_centavos == a_mano
    assert sum(g.centavos for g in informe.por_categoria) == a_mano
    for g in informe.por_categoria:
        assert g.porcentaje == _redondeo_exacto(g.centavos, a_mano), g
    assert abs(sum(g.porcentaje for g in informe.por_categoria) - 100) <= 0.05 * len(informe.por_categoria)


def test_categoria_diminuta_aparece_con_0_0(conn):
    _mov(conn, "2026-09-10T10:00:00", 1, categoria="Salud")
    _mov(conn, "2026-09-10T11:00:00", 999_999_99, categoria="Mercado")
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert {g.nombre: g.porcentaje for g in informe.por_categoria} == {"Mercado": 100.0, "Salud": 0.0}
    assert sum(g.centavos for g in informe.por_categoria) == informe.total_gasto_centavos


@pytest.mark.parametrize("semilla", range(5))
def test_porcentaje_coincide_con_decimal_half_up(semilla):
    azar = random.Random(semilla)
    for _ in range(2000):
        total = azar.randint(1, 10**12)
        parte = azar.randint(1, total)
        assert reporte._porcentaje(parte, total) == _redondeo_exacto(parte, total)


# --- Composición del mes -------------------------------------------------------------

def test_mes_con_solo_sin_categorizar(conn):
    _mov(conn, "2026-09-03T10:00:00", 1_500_00, descripcion="SIN REGLA A")
    _mov(conn, "2026-09-04T10:00:00", 2_500_00, "transferencia", "*0001")
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert informe.total_gasto_centavos == 4_000_00
    assert [(g.nombre, g.centavos, g.porcentaje) for g in informe.por_categoria] == [
        ("Sin categorizar", 4_000_00, 100.0)
    ]
    assert {m.categoria for m in informe.movimientos} == {"Sin categorizar"}


def test_transferencia_con_categoria_cuenta_en_su_categoria(conn):
    _mov(conn, "2026-09-05T10:00:00", 800_000_00, "transferencia", "*4321", categoria="Vivienda y servicios")
    _mov(conn, "2026-09-06T10:00:00", 50_000_00, descripcion="TIENDA", categoria="Vivienda y servicios")
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert [(g.nombre, g.centavos) for g in informe.por_categoria] == [("Vivienda y servicios", 850_000_00)]
    transferencia = next(m for m in informe.movimientos if m.tipo == "transferencia")
    assert (transferencia.categoria, transferencia.es_gasto) == ("Vivienda y servicios", True)


def test_ajuste_con_categoria_en_la_base_no_cuenta(conn):
    _mov(conn, "2026-09-05T10:00:00", -1_000_00, "ajuste", "Ajuste", categoria="Otros")
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert (informe.total_gasto_centavos, informe.por_categoria) == (0, [])
    assert informe.movimientos[0].categoria == "—"


# --- Límites del mes -------------------------------------------------------------------

@pytest.mark.parametrize(
    ("anio", "mes", "dentro", "fuera_antes", "fuera_despues"),
    [
        (2024, 2, ["2024-02-01T00:00:00", "2024-02-29T23:59:59"], "2024-01-31T23:59:59", "2024-03-01T00:00:00"),
        (2000, 2, ["2000-02-01T00:00:00", "2000-02-29T23:59:59"], "2000-01-31T23:59:59", "2000-03-01T00:00:00"),
        (2027, 2, ["2027-02-01T00:00:00", "2027-02-28T23:59:59"], "2027-01-31T23:59:59", "2027-03-01T00:00:00"),
        (2026, 12, ["2026-12-01T00:00:00", "2026-12-31T23:59:59"], "2026-11-30T23:59:59", "2027-01-01T00:00:00"),
        (2027, 1, ["2027-01-01T00:00:00", "2027-01-31T23:59:59"], "2026-12-31T23:59:59", "2027-02-01T00:00:00"),
        (2099, 12, ["2099-12-01T00:00:00", "2099-12-31T23:59:59"], "2099-11-30T23:59:59", "2100-01-01T00:00:00"),
        (2000, 1, ["2000-01-01T00:00:00", "2000-01-31T23:59:59"], "1999-12-31T23:59:59", "2000-02-01T00:00:00"),
    ],
)
def test_limites_bisiestos_y_cambio_de_anio(conn, anio, mes, dentro, fuera_antes, fuera_despues):
    ids = {_mov(conn, f, 1_00, categoria="Mercado") for f in dentro}
    _mov(conn, fuera_antes, 10_00, categoria="Mercado")
    _mov(conn, fuera_despues, 100_00, categoria="Mercado")
    informe = componer_reporte(conn).reporte_mensual(anio, mes)
    assert {m.id for m in informe.movimientos} == ids
    assert informe.total_gasto_centavos == 2_00
    assert sum(g.centavos for g in informe.por_categoria) == 2_00


def test_29_de_febrero_2028_no_aparece_en_marzo_ni_enero(conn):
    _mov(conn, "2028-02-29T23:59:59", 7_00, categoria="Salud")
    assert componer_reporte(conn).reporte_mensual(2028, 2).total_gasto_centavos == 7_00
    assert componer_reporte(conn).reporte_mensual(2028, 1).total_gasto_centavos == 0
    assert componer_reporte(conn).reporte_mensual(2028, 3).total_gasto_centavos == 0


# --- Consistencia con escrituras concurrentes -------------------------------------------

def test_escritura_concurrente_entre_consultas_no_descuadra(conn, tmp_path, monkeypatch):
    """Una "sincronización" (otra conexión) intenta guardar un gasto justo entre
    la consulta del total y la del gasto por categoría. El reporte debe ser
    coherente: la suma por categoría es el total y la lista cuadra con ambos."""
    _mov(conn, "2026-09-02T10:00:00", 1_000_00, categoria="Mercado")
    ruta = str(tmp_path / "bordes.db")
    original = OperarSaldo.gasto_entre
    resultado = {}

    def sincronizar_en_paralelo():
        otra = sqlite3.connect(ruta, timeout=10)
        try:
            with otra:
                otra.execute(
                    "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen, gmail_id) "
                    "VALUES ('2026-09-03T10:00:00', 55500, 'compra', 'SINCRONIZADO', 'gmail', 'concurrente-1')"
                )
            resultado["ok"] = True
        except Exception as error:  # pragma: no cover - se reporta en el assert
            resultado["error"] = repr(error)
        finally:
            otra.close()

    hilo = threading.Thread(target=sincronizar_en_paralelo)

    def gasto_entre_y_luego_sincroniza(*args, **kwargs):
        total = original(*args, **kwargs)
        hilo.start()
        time.sleep(0.3)  # deja que la otra conexión intente escribir
        return total

    monkeypatch.setattr(OperarSaldo, "gasto_entre", gasto_entre_y_luego_sincroniza)
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    hilo.join(timeout=15)
    monkeypatch.setattr(OperarSaldo, "gasto_entre", original)

    assert sum(g.centavos for g in informe.por_categoria) == informe.total_gasto_centavos
    gastos_listados = sum(m.monto_centavos for m in informe.movimientos if m.es_gasto)
    assert gastos_listados == informe.total_gasto_centavos
    # La sincronización no se pierde: termina en cuanto el reporte suelta la lectura.
    assert resultado == {"ok": True}
    despues = componer_reporte(conn).reporte_mensual(2026, 9)
    assert despues.total_gasto_centavos == 1_555_00
    assert not db.en_transaccion(conn)


def test_respeta_una_transaccion_abierta_de_quien_llama(conn):
    _mov(conn, "2026-09-02T10:00:00", 1_00, categoria="Mercado")
    sql(conn, "BEGIN")
    _insertar(conn, "2026-09-03T10:00:00", 2_00, categoria="Mercado")
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert informe.total_gasto_centavos == 3_00  # ve lo no confirmado de su propia transacción
    assert db.en_transaccion(conn)  # y no la cierra
    conn.rollback()
    assert componer_reporte(conn).reporte_mensual(2026, 9).total_gasto_centavos == 1_00


def test_reporte_grande_es_rapido(conn):
    with db.transaccion(conn):
        for i in range(500):
            _insertar(conn, f"2026-09-{i % 30 + 1:02d}T{i % 24:02d}:00:00", 1_000 + i,
                      "compra" if i % 2 else "transferencia", f"COMERCIO {i}",
                      db.CATEGORIAS_FIJAS[i % len(db.CATEGORIAS_FIJAS)] if i % 5 else None)
    inicio = time.perf_counter()
    informe = componer_reporte(conn).reporte_mensual(2026, 9)
    assert time.perf_counter() - inicio < 1.0
    assert len(informe.movimientos) == 500
    assert informe.total_gasto_centavos == sum(1_000 + i for i in range(500))
