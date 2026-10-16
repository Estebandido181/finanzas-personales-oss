"""Pruebas del cálculo del saldo, ingresos manuales y ajustes (ítem 05).

Todos los montos y fechas son inventados.
"""

from __future__ import annotations
from finanzas.bootstrap.saldo import componer_saldo
from finanzas.modulos.saldo import politica as saldo_politica
from finanzas.modulos.saldo import contratos as saldo_contratos

from finanzas.modulos.saldo.aplicacion import OperarSaldo

import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone

import pytest

from finanzas import db
from finanzas.compartido import hora
from finanzas.modulos.saldo.contratos import ErrorSaldo, SaldoNoConfigurado
from tests.soporte.ayudas_db import sql

INICIO = date(2026, 8, 1)
AHORA = datetime(2026, 9, 15, 12, 0, 0)  # hora de Colombia fija para las pruebas


@pytest.fixture
def ruta(tmp_path):
    return str(tmp_path / "saldo.db")


@pytest.fixture
def conn(ruta):
    c = db.conectar(ruta)
    db.inicializar(c)
    yield c
    c.close()


@pytest.fixture
def reloj(monkeypatch):
    """Fija la hora de Colombia en ``AHORA`` (se puede mover con ``reloj.poner``)."""

    class Reloj:
        actual = AHORA

        def poner(self, momento):
            self.actual = momento

    r = Reloj()
    monkeypatch.setattr(hora, "ahora_colombia", lambda: r.actual)
    return r


@pytest.fixture
def configurada(conn, reloj):
    componer_saldo(conn).configurar(100_000_00, INICIO)  # $100.000,00
    return conn


_contador_gmail = iter(range(1, 10**6))


def insertar(conn, tipo, monto, fecha_hora, descripcion="MOVIMIENTO DE PRUEBA"):
    """Inserta un movimiento directo en la base (como lo haría la sincronización)."""
    origen = "gmail" if tipo in ("compra", "transferencia") else "manual"
    gmail_id = f"msg-prueba-{next(_contador_gmail)}" if origen == "gmail" else None
    with db.transaccion(conn):
        sql(
            conn,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen, gmail_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fecha_hora, monto, tipo, descripcion, origen, gmail_id),
        )


def contar(conn, tipo=None):
    if tipo is None:
        return sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0]
    return sql(conn, "SELECT COUNT(*) FROM movimientos WHERE tipo = ?", (tipo,)).fetchone()[0]


# --- Fórmula --------------------------------------------------------------------

def test_sin_movimientos_el_saldo_es_el_inicial(configurada):
    assert componer_saldo(configurada).saldo_actual() == 100_000_00


def test_formula_exacta(configurada):
    c = configurada
    insertar(c, "compra", 12_345_67, "2026-08-02T10:00:00")
    insertar(c, "compra", 1, "2026-08-03T10:00:00")
    insertar(c, "transferencia", 20_000_00, "2026-08-04T10:00:00")
    insertar(c, "ingreso", 50_000_50, "2026-08-05T10:00:00")
    insertar(c, "ajuste", -3_000_00, "2026-08-06T10:00:00")
    insertar(c, "ajuste", 1_500_25, "2026-08-07T10:00:00")
    esperado = 100_000_00 + 50_000_50 - 12_345_67 - 1 - 20_000_00 - 3_000_00 + 1_500_25
    assert componer_saldo(c).saldo_actual() == esperado == 116_155_07


def test_el_saldo_puede_quedar_negativo(configurada):
    insertar(configurada, "compra", 150_000_00, "2026-08-02T10:00:00")
    assert componer_saldo(configurada).saldo_actual() == -50_000_00


def test_movimientos_anteriores_a_la_fecha_de_inicio_no_cuentan(conn, reloj):
    # Se insertan antes de configurar (configurar exige que no haya
    # movimientos), así que se configura primero y se insertan después.
    componer_saldo(conn).configurar(100_000_00, INICIO)
    insertar(conn, "compra", 9_999_00, "2026-07-31T23:59:59")
    insertar(conn, "ingreso", 5_000_00, "2026-07-15T08:00:00")
    insertar(conn, "ajuste", -700_00, "2025-12-31T12:00:00")
    assert componer_saldo(conn).saldo_actual() == 100_000_00
    # El mismo día de inicio desde las 00:00 sí cuenta.
    insertar(conn, "compra", 1_000_00, "2026-08-01T00:00:00")
    assert componer_saldo(conn).saldo_actual() == 99_000_00


def test_sin_configuracion_lanza(conn):
    with pytest.raises(SaldoNoConfigurado):
        componer_saldo(conn).saldo_actual()
    assert componer_saldo(conn).leer_configuracion() is None


def test_leer_configuracion(configurada):
    config = componer_saldo(configurada).leer_configuracion()
    assert config == saldo_contratos.Configuracion(100_000_00, INICIO)


# --- Ajustes ---------------------------------------------------------------------

@pytest.fixture
def con_movimientos(configurada):
    insertar(configurada, "compra", 30_000_00, "2026-08-02T10:00:00")
    insertar(configurada, "ingreso", 10_000_00, "2026-08-03T10:00:00")
    assert componer_saldo(configurada).saldo_actual() == 80_000_00
    return configurada


@pytest.mark.parametrize(
    ("real", "diferencia"),
    [
        (79_991_60, -8_40),  # falta dinero: cuota de manejo, 4x1000...
        (0, -80_000_00),
        (85_000_01, 5_000_01),  # sobra dinero
    ],
)
def test_despues_del_ajuste_el_saldo_coincide(con_movimientos, real, diferencia):
    c = con_movimientos
    assert componer_saldo(c).ajustar_saldo(real) == diferencia
    assert componer_saldo(c).saldo_actual() == real
    fila = sql(
        c,
        "SELECT monto_centavos, fecha_hora, descripcion, origen, gmail_id, categoria_id "
        "FROM movimientos WHERE tipo = 'ajuste'"
    ).fetchone()
    assert tuple(fila) == (diferencia, "2026-09-15T12:00:00", "Ajuste de saldo", "manual", None, None)


def test_ajuste_igual_al_calculado_no_inserta_nada(con_movimientos):
    antes = contar(con_movimientos)
    assert componer_saldo(con_movimientos).ajustar_saldo(80_000_00) == 0
    assert contar(con_movimientos) == antes
    assert contar(con_movimientos, "ajuste") == 0
    assert componer_saldo(con_movimientos).saldo_actual() == 80_000_00


def test_ajustes_sucesivos(con_movimientos):
    componer_saldo(con_movimientos).ajustar_saldo(70_000_00)
    componer_saldo(con_movimientos).ajustar_saldo(75_000_00)
    assert componer_saldo(con_movimientos).saldo_actual() == 75_000_00
    montos = [f[0] for f in sql(con_movimientos,
        "SELECT monto_centavos FROM movimientos WHERE tipo = 'ajuste' ORDER BY id")]
    assert montos == [-10_000_00, 5_000_00]


@pytest.mark.parametrize("real", [-1, 1.5, "100", True, None, saldo_politica.MAXIMO_CENTAVOS + 1])
def test_ajuste_rechaza_saldo_real_invalido(con_movimientos, real):
    with pytest.raises(ErrorSaldo):
        componer_saldo(con_movimientos).ajustar_saldo(real)
    assert contar(con_movimientos, "ajuste") == 0


def test_ajuste_sin_configuracion(conn):
    with pytest.raises(SaldoNoConfigurado):
        componer_saldo(conn).ajustar_saldo(1_000_00)
    assert contar(conn) == 0


# --- Gasto --------------------------------------------------------------------------

def test_gasto_entre_excluye_ingresos_y_ajustes(configurada):
    c = configurada
    insertar(c, "compra", 10_000_00, "2026-08-10T10:00:00")
    insertar(c, "transferencia", 2_500_50, "2026-08-11T10:00:00")
    insertar(c, "ingreso", 999_000_00, "2026-08-12T10:00:00")
    insertar(c, "ajuste", -4_000_00, "2026-08-13T10:00:00")
    insertar(c, "ajuste", 7_000_00, "2026-08-14T10:00:00")
    assert componer_saldo(c).gasto_entre(datetime(2026, 8, 1), datetime(2026, 9, 1)) == 12_500_50


def test_gasto_entre_respeta_los_limites(configurada):
    c = configurada
    insertar(c, "compra", 1_00, "2026-07-31T23:59:59")  # antes de desde
    insertar(c, "compra", 10_00, "2026-08-01T00:00:00")  # justo en desde: cuenta
    insertar(c, "compra", 100_00, "2026-08-31T23:59:59")  # último segundo: cuenta
    insertar(c, "transferencia", 1_000_00, "2026-09-01T00:00:00")  # justo en hasta: no
    assert componer_saldo(c).gasto_entre(datetime(2026, 8, 1), datetime(2026, 9, 1)) == 110_00
    assert componer_saldo(c).gasto_entre(datetime(2026, 9, 1), datetime(2026, 10, 1)) == 1_000_00
    assert componer_saldo(c).gasto_entre(datetime(2026, 8, 1), datetime(2026, 8, 1)) == 0


def test_gasto_entre_convierte_fechas_con_zona(configurada):
    insertar(configurada, "compra", 10_00, "2026-08-01T00:00:00")
    # 05:00 UTC es la medianoche en Colombia.
    desde = datetime(2026, 8, 1, 5, 0, tzinfo=timezone.utc)
    assert componer_saldo(configurada).gasto_entre(desde, desde + timedelta(days=1)) == 10_00
    assert componer_saldo(configurada).gasto_entre(desde + timedelta(seconds=1), desde + timedelta(days=1)) == 0


def test_gasto_entre_con_microsegundos_respeta_desde_y_hasta(configurada):
    """Contrato: desde <= fecha_hora < hasta, también si los límites traen microsegundos."""
    insertar(configurada, "compra", 1_00, "2026-08-01T00:00:00")
    insertar(configurada, "compra", 10_00, "2026-09-01T00:00:00")
    desde = datetime(2026, 8, 1, 0, 0, 0, 500_000)  # 00:00:00 queda antes de desde
    hasta = datetime(2026, 9, 1, 0, 0, 0, 500_000)  # 00:00:00 queda antes de hasta
    assert componer_saldo(configurada).gasto_entre(desde, hasta) == 10_00

def test_gasto_entre_redondea_hacia_arriba_los_microsegundos(configurada):
    insertar(configurada, "compra", 1_00, "2026-08-01T00:00:01")
    insertar(configurada, "compra", 10_00, "2026-08-31T23:59:59")
    desde = datetime(2026, 8, 1, 0, 0, 0, 1)  # 00:00:01 sí cuenta
    hasta = datetime(2026, 8, 31, 23, 59, 59, 999_999)  # 23:59:59 sí cuenta
    assert componer_saldo(configurada).gasto_entre(desde, hasta) == 11_00
    # Sin microsegundos no se redondea: 00:00:01 no es < 00:00:01.
    assert componer_saldo(configurada).gasto_entre(datetime(2026, 8, 1), datetime(2026, 8, 1, 0, 0, 1)) == 0


def test_gasto_entre_sin_movimientos_es_cero(conn):
    assert componer_saldo(conn).gasto_entre(datetime(2026, 8, 1), datetime(2026, 9, 1)) == 0


# --- Configurar ------------------------------------------------------------------------

def test_configurar_guarda_y_se_puede_repetir_sin_movimientos(conn, reloj):
    componer_saldo(conn).configurar(5_00, date(2026, 9, 1))
    componer_saldo(conn).configurar(0, INICIO)
    assert componer_saldo(conn).leer_configuracion() == saldo_contratos.Configuracion(0, INICIO)
    assert sql(conn, "SELECT fecha_inicio FROM configuracion_saldo").fetchone()[0] == "2026-08-01"


def test_configurar_rechaza_si_ya_hay_movimientos(configurada):
    insertar(configurada, "compra", 1_000_00, "2026-08-02T10:00:00")
    with pytest.raises(ErrorSaldo, match="ajuste"):
        componer_saldo(configurada).configurar(1, INICIO)
    assert componer_saldo(configurada).leer_configuracion() == saldo_contratos.Configuracion(100_000_00, INICIO)


def test_configurar_rechaza_si_hay_un_ingreso_o_ajuste(configurada):
    componer_saldo(configurada).ajustar_saldo(1)
    with pytest.raises(ErrorSaldo):
        componer_saldo(configurada).configurar(1, INICIO)


def test_configurar_rechaza_fecha_futura(conn, reloj):
    with pytest.raises(ErrorSaldo, match="futura"):
        componer_saldo(conn).configurar(1_000_00, AHORA.date() + timedelta(days=1))
    componer_saldo(conn).configurar(1_000_00, AHORA.date())  # hoy sí
    assert componer_saldo(conn).leer_configuracion().fecha_inicio == AHORA.date()


def test_configurar_usa_la_fecha_de_colombia(conn, reloj):
    # 23:30 del 15 en Colombia (ya es 16 en UTC): el 16 todavía es futuro.
    reloj.poner(datetime(2026, 9, 15, 23, 30))
    with pytest.raises(ErrorSaldo):
        componer_saldo(conn).configurar(1, date(2026, 9, 16))


@pytest.mark.parametrize("valor", [-1, -100_00, 1.0, "100", None, True, saldo_politica.MAXIMO_CENTAVOS + 1])
def test_configurar_rechaza_saldo_invalido(conn, reloj, valor):
    with pytest.raises(ErrorSaldo):
        componer_saldo(conn).configurar(valor, INICIO)
    assert componer_saldo(conn).leer_configuracion() is None


@pytest.mark.parametrize("fecha", ["2026-08-01", datetime(2026, 8, 1, 10, 0), None])
def test_configurar_rechaza_fecha_que_no_es_date(conn, reloj, fecha):
    with pytest.raises(ErrorSaldo):
        componer_saldo(conn).configurar(1, fecha)


def test_ahora_colombia_real_es_utc_menos_5():
    antes = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0) - timedelta(hours=5)
    ahora = hora.ahora_colombia()
    assert ahora.tzinfo is None and ahora.microsecond == 0
    assert timedelta(0) <= ahora - antes <= timedelta(seconds=5)


# --- Ingresos --------------------------------------------------------------------------

def test_registrar_ingreso(configurada):
    id_ = componer_saldo(configurada).registrar_ingreso(2_500_000_00, datetime(2026, 8, 30, 8, 15), "  Sueldo  ")
    fila = sql(configurada, "SELECT * FROM movimientos WHERE id = ?", (id_,)).fetchone()
    assert fila["tipo"] == "ingreso"
    assert fila["monto_centavos"] == 2_500_000_00
    assert fila["fecha_hora"] == "2026-08-30T08:15:00"
    assert fila["descripcion"] == "Sueldo"
    assert (fila["origen"], fila["gmail_id"], fila["categoria_id"]) == ("manual", None, None)
    assert componer_saldo(configurada).saldo_actual() == 100_000_00 + 2_500_000_00
    # No es gasto.
    assert componer_saldo(configurada).gasto_entre(datetime(2026, 8, 1), datetime(2026, 10, 1)) == 0


@pytest.mark.parametrize("monto", [0, -1, -5_000_00, 1.5, "100", True, None, saldo_politica.MAXIMO_CENTAVOS + 1])
def test_ingreso_rechaza_monto_invalido(configurada, monto):
    with pytest.raises(ErrorSaldo):
        componer_saldo(configurada).registrar_ingreso(monto, datetime(2026, 8, 30), "Sueldo")
    assert contar(configurada) == 0


def test_ingreso_fecha_limites(configurada):
    # Justo en la fecha de inicio a las 00:00 y hasta ahora + 5 minutos: sí.
    componer_saldo(configurada).registrar_ingreso(1, datetime(2026, 8, 1, 0, 0), "")
    componer_saldo(configurada).registrar_ingreso(1, AHORA + timedelta(minutes=5), "")
    # Un segundo antes del inicio o más allá de la tolerancia: no.
    with pytest.raises(ErrorSaldo, match="anterior"):
        componer_saldo(configurada).registrar_ingreso(1, datetime(2026, 7, 31, 23, 59, 59), "")
    with pytest.raises(ErrorSaldo, match="futura"):
        componer_saldo(configurada).registrar_ingreso(1, AHORA + timedelta(minutes=5, seconds=1), "")
    assert contar(configurada) == 2


def test_ingreso_con_zona_se_convierte_a_colombia(configurada):
    id_ = componer_saldo(configurada).registrar_ingreso(1_00, datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc), "x"
    )
    fila = sql(configurada, "SELECT fecha_hora FROM movimientos WHERE id = ?", (id_,)).fetchone()
    assert fila[0] == "2026-08-10T10:00:00"


@pytest.mark.parametrize("descripcion", ["", "   ", "\t\n", None])
def test_ingreso_descripcion_vacia_queda_ingreso(configurada, descripcion):
    id_ = componer_saldo(configurada).registrar_ingreso(1_00, datetime(2026, 8, 10), descripcion)
    fila = sql(configurada, "SELECT descripcion FROM movimientos WHERE id = ?", (id_,)).fetchone()
    assert fila[0] == "Ingreso"


def test_ingreso_descripcion_larga(configurada):
    componer_saldo(configurada).registrar_ingreso(1_00, datetime(2026, 8, 10), "á" * 200)
    with pytest.raises(ErrorSaldo, match="200"):
        componer_saldo(configurada).registrar_ingreso(1_00, datetime(2026, 8, 10), "á" * 201)
    # Se recorta antes de medir.
    componer_saldo(configurada).registrar_ingreso(1_00, datetime(2026, 8, 10), "  " + "b" * 200 + "  ")
    assert contar(configurada) == 2


def test_ingreso_sin_configuracion(conn, reloj):
    with pytest.raises(SaldoNoConfigurado):
        componer_saldo(conn).registrar_ingreso(1_00, datetime(2026, 8, 10), "x")
    assert contar(conn) == 0


def test_ingreso_rechaza_fecha_que_no_es_datetime(configurada):
    with pytest.raises(ErrorSaldo):
        componer_saldo(configurada).registrar_ingreso(1_00, date(2026, 8, 10), "x")


def test_ultimos_ingresos_y_ajustes(configurada):
    insertar(configurada, "compra", 1_00, "2026-08-20T10:00:00")
    for dia in range(1, 25):
        componer_saldo(configurada).registrar_ingreso(dia, datetime(2026, 8, dia, 9, 0), f"ingreso {dia}")
    componer_saldo(configurada).ajustar_saldo(0)
    ultimos = componer_saldo(configurada).ultimos_ingresos_y_ajustes()
    assert len(ultimos) == 20
    assert ultimos[0]["tipo"] == "ajuste"  # el más reciente (15/09)
    assert [f["descripcion"] for f in ultimos[1:3]] == ["ingreso 24", "ingreso 23"]
    assert all(f["tipo"] in ("ingreso", "ajuste") for f in ultimos)


# --- leer_pesos ------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("texto", "centavos"),
    [
        ("1234567", 123456700),
        ("1.234.567", 123456700),
        ("1.234.567,89", 123456789),
        ("1234567,89", 123456789),
        ("0,50", 50),
        ("0,5", 50),
        ("0", 0),
        ("1.000", 100000),
        ("999", 99900),
        ("$1.234.567,89", 123456789),
        ("$ 1.234", 123400),
        ("  $ 68.630,00  ", 6863000),
        ("12,3", 1230),
        (" $ 1.000 ", 100000),  # espacios duros al copiar y pegar
        ("10.000.000.000", 10**12),  # el máximo exacto
    ],
)
def test_leer_pesos_validos(texto, centavos):
    assert saldo_politica.leer_pesos(texto) == centavos


@pytest.mark.parametrize(
    ("texto", "mensaje"),
    [
        ("", "Escribe un monto"),
        ("   ", "Escribe un monto"),
        ("$", "Escribe un monto"),
        ("-5", "negativo"),
        ("$-5", "negativo"),
        ("-$5", "negativo"),
        ("−5", "negativo"),
        ("12.34.567", "Monto no válido"),  # miles mal agrupados
        ("1.2345", "Monto no válido"),
        ("1234.567", "Monto no válido"),
        (".123", "Monto no válido"),
        ("1.", "Monto no válido"),
        ("1,", "Monto no válido"),
        (",50", "Monto no válido"),
        ("1,234", "2 decimales"),
        ("1.234,567", "2 decimales"),
        ("0,001", "2 decimales"),
        ("1234.56", "coma para los decimales"),  # punto como decimal: ambiguo
        ("1.234.56", "coma para los decimales"),
        ("12.5", "coma para los decimales"),
        ("1,234.56", "Monto no válido"),
        ("١٢٣", "Monto no válido"),  # cifras arábigo-índicas
        ("１２３", "Monto no válido"),  # cifras de ancho completo
        ("1 234", "Monto no válido"),
        ("abc", "Monto no válido"),
        ("1e5", "Monto no válido"),
        ("+5", "Monto no válido"),
        ("$$5", "Monto no válido"),
        ("10.000.000.001", "demasiado grande"),
        ("10000000000,01", "demasiado grande"),
        ("9" * 60, "demasiado grande"),
    ],
)
def test_leer_pesos_invalidos(texto, mensaje):
    with pytest.raises(ErrorSaldo, match=mensaje):
        saldo_politica.leer_pesos(texto)


def test_leer_pesos_rechaza_lo_que_no_es_texto():
    with pytest.raises(ErrorSaldo):
        saldo_politica.leer_pesos(None)


def test_leer_fecha_y_fecha_hora():
    assert saldo_politica.leer_fecha("2026-08-01") == INICIO
    assert saldo_politica.leer_fecha_hora("2026-08-01T09:30") == datetime(2026, 8, 1, 9, 30)
    assert saldo_politica.leer_fecha_hora("2026-08-01T09:30:15") == datetime(2026, 8, 1, 9, 30, 15)
    for malo in ("", "20260801", "2026-02-30", "01/08/2026", "2026-08-01T09:30+00:00", "２026-08-01"):
        with pytest.raises(ErrorSaldo):
            saldo_politica.leer_fecha(malo)
        with pytest.raises(ErrorSaldo):
            saldo_politica.leer_fecha_hora(malo)
    with pytest.raises(ErrorSaldo):
        saldo_politica.leer_fecha_hora("2026-08-01T25:00")


# --- Concurrencia -------------------------------------------------------------------------

def _insertar_compra_en_otra_conexion(ruta, monto, fecha_hora, hecho):
    otra = db.conectar(ruta)
    try:
        insertar(otra, "compra", monto, fecha_hora)
    finally:
        otra.close()
        hecho.set()


def test_ajuste_bloquea_la_compra_hasta_terminar(configurada, ruta, monkeypatch):
    """La compra llega mientras el ajuste está entre el cálculo y el INSERT:
    debe esperar a que el ajuste termine (entra después, nunca en medio)."""
    calculado = threading.Event()
    seguir = threading.Event()
    original = OperarSaldo.saldo_actual

    def saldo_actual_lento(conn):
        valor = original(conn)
        calculado.set()
        assert seguir.wait(5)
        return valor

    monkeypatch.setattr(OperarSaldo, "saldo_actual", saldo_actual_lento)
    resultado = {}

    def ajustar():
        c = db.conectar(ruta)
        try:
            resultado["diferencia"] = componer_saldo(c).ajustar_saldo(90_000_00)
        finally:
            c.close()

    hilo_ajuste = threading.Thread(target=ajustar)
    hilo_ajuste.start()
    assert calculado.wait(5)

    compra_hecha = threading.Event()
    hilo_compra = threading.Thread(
        target=_insertar_compra_en_otra_conexion,
        args=(ruta, 7_000_00, "2026-09-15T11:00:00", compra_hecha),
    )
    hilo_compra.start()
    # Mientras el ajuste no termina, la compra no puede escribir.
    assert not compra_hecha.wait(0.3)
    seguir.set()
    hilo_ajuste.join(5)
    hilo_compra.join(5)
    assert compra_hecha.is_set()

    monkeypatch.setattr(OperarSaldo, "saldo_actual", original)
    assert resultado["diferencia"] == -10_000_00  # calculado sin la compra
    assert componer_saldo(configurada).saldo_actual() == 90_000_00 - 7_000_00


def test_compra_en_curso_entra_antes_del_ajuste(configurada, ruta):
    """Si la compra ya tiene la escritura, el ajuste espera y la tiene en cuenta."""
    otra = db.conectar(ruta)
    sql(otra, "BEGIN IMMEDIATE")
    sql(
        otra,
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen, gmail_id) "
        "VALUES ('2026-09-15T11:00:00', 700000, 'compra', 'TIENDA', 'gmail', 'msg-carrera')"
    )
    resultado = {}

    def ajustar():
        c = db.conectar(ruta)
        try:
            resultado["diferencia"] = componer_saldo(c).ajustar_saldo(90_000_00)
        finally:
            c.close()

    hilo = threading.Thread(target=ajustar)
    hilo.start()
    hilo.join(0.3)
    assert hilo.is_alive()  # esperando la escritura
    otra.commit()
    otra.close()
    hilo.join(5)
    assert not hilo.is_alive()

    assert resultado["diferencia"] == 90_000_00 - (100_000_00 - 7_000_00)
    assert componer_saldo(configurada).saldo_actual() == 90_000_00


def test_ajustar_nunca_guarda_cero_aunque_la_base_lo_admita(configurada):
    """Desde la 0008 la base admite un ajuste en 0 (D45: lo importado del banco
    puede reducirlo del todo), pero ``ajustar_saldo`` sigue sin guardarlo."""
    antes = contar(configurada, "ajuste")
    assert componer_saldo(configurada).ajustar_saldo(componer_saldo(configurada).saldo_actual()) == 0
    assert contar(configurada, "ajuste") == antes
    insertar(configurada, "ajuste", 0, "2026-08-02T10:00:00")
    with pytest.raises(sqlite3.IntegrityError):
        insertar(configurada, "compra", 0, "2026-08-02T10:00:00")
