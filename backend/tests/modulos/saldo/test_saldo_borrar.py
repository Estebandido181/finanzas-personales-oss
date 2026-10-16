"""Ítem 16: desglose del saldo, ingresos y ajustes del mes y borrado de ingresos manuales.

Lógica del servicio de Saldo sin la API. Todos los montos, fechas y nombres
son inventados.
"""

from __future__ import annotations
from finanzas.bootstrap.saldo import componer_saldo
from finanzas.modulos.saldo import politica as saldo_politica
from finanzas.modulos.saldo import contratos as saldo_contratos

from finanzas.modulos.saldo.aplicacion import OperarSaldo

import threading
from datetime import date, datetime

import pytest

from finanzas import db
from finanzas.compartido import hora
from finanzas.modulos.saldo.contratos import BorradoNoPermitido, MovimientoNoEncontrado
from tests.soporte.ayudas_db import sql

INICIO = date(2026, 8, 1)
AHORA = datetime(2026, 9, 15, 12, 0, 0)
SEPTIEMBRE = (datetime(2026, 9, 1), datetime(2026, 10, 1))


@pytest.fixture
def ruta(tmp_path):
    return str(tmp_path / "saldo-borrar.db")


@pytest.fixture
def conn(ruta):
    c = db.conectar(ruta)
    db.inicializar(c)
    yield c
    c.close()


@pytest.fixture
def reloj(monkeypatch):
    class Reloj:
        actual = AHORA

        def poner(self, momento):
            self.actual = momento

    r = Reloj()
    monkeypatch.setattr(hora, "ahora_colombia", lambda: r.actual)
    return r


@pytest.fixture
def configurada(conn, reloj):
    componer_saldo(conn).configurar(100_000_00, INICIO)
    return conn


_contador = iter(range(1, 10**6))


def insertar_gmail(conn, tipo, monto, fecha_hora, descripcion="REMITENTE INVENTADO"):
    """Movimiento como lo guarda la sincronización (origen Gmail)."""
    with db.transaccion(conn):
        return sql(
            conn,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen, gmail_id) "
            "VALUES (?, ?, ?, ?, 'gmail', ?)",
            (fecha_hora, monto, tipo, descripcion, f"msg-borrar-{next(_contador)}"),
        ).lastrowid


def ingreso(conn, monto, fecha_hora, descripcion="Efectivo inventado"):
    return componer_saldo(conn).registrar_ingreso(monto, datetime.fromisoformat(fecha_hora), descripcion)


def ajuste_en(conn, reloj, momento, saldo_real):
    """Ajuste hecho a la hora ``momento`` (se guarda con la hora actual)."""
    reloj.poner(momento)
    diferencia = componer_saldo(conn).ajustar_saldo(saldo_real)
    reloj.poner(AHORA)
    return diferencia


def foto(conn):
    return sql(conn, "SELECT * FROM movimientos ORDER BY id").fetchall()


# --- Desglose ------------------------------------------------------------------------------

def test_desglose_cuadra_con_saldo_actual(configurada, reloj):
    insertar_gmail(configurada, "compra", 12_345_67, "2026-08-03T10:00:00")
    insertar_gmail(configurada, "transferencia", 2_000_00, "2026-08-04T10:00:00")
    insertar_gmail(configurada, "ingreso", 50_000_00, "2026-08-05T10:00:00")
    insertar_gmail(configurada, "compra", 9_999_99, "2026-07-31T23:59:59")  # antes del inicio: no cuenta
    ingreso(configurada, 1_500_00, "2026-08-06T09:00")
    ajuste_en(configurada, reloj, datetime(2026, 8, 7, 8, 0), 130_000_00)

    desglose = componer_saldo(configurada).desglose_saldo()
    assert desglose.saldo_inicial_centavos == 100_000_00
    assert desglose.ingresos_centavos == 50_000_00 + 1_500_00
    assert desglose.gastos_centavos == 12_345_67 + 2_000_00
    assert desglose.ajustes_centavos == 130_000_00 - (100_000_00 + 51_500_00 - 14_345_67)
    assert desglose.saldo_centavos == componer_saldo(configurada).saldo_actual() == 130_000_00
    assert all(isinstance(v, int) for v in vars(desglose).values())


def test_desglose_sin_movimientos_y_sin_configurar(conn, reloj):
    with pytest.raises(saldo_contratos.SaldoNoConfigurado):
        componer_saldo(conn).desglose_saldo()
    componer_saldo(conn).configurar(7_00, INICIO)
    assert componer_saldo(conn).desglose_saldo() == saldo_contratos.Desglose(7_00, 0, 0, 0)


# --- Ingresos y ajustes del mes -------------------------------------------------------------

def test_lista_del_mes_y_total_de_ajustes(configurada, reloj):
    insertar_gmail(configurada, "ingreso", 4_800_000_00, "2026-09-02T08:00:00", "EMPRESA EJEMPLO S.A.S.")
    insertar_gmail(configurada, "compra", 1_000_00, "2026-09-03T08:00:00")  # no es ingreso ni ajuste
    ingreso(configurada, 3_00, "2026-08-31T23:59:59", "agosto")  # otro mes
    ajuste_en(configurada, reloj, datetime(2026, 9, 5, 9, 10), 4_899_000_00)
    ajuste_en(configurada, reloj, datetime(2026, 9, 10, 9, 10), 4_898_000_00)
    viejo = ingreso(configurada, 2_00, "2026-09-04T10:00", "antes del ajuste")
    nuevo = ingreso(configurada, 150_000_00, "2026-09-12T10:00", "Efectivo venta inventada")

    filas = componer_saldo(configurada).ingresos_y_ajustes_entre(*SEPTIEMBRE)
    assert [f["descripcion"] for f in filas] == [
        "Efectivo venta inventada", "Ajuste de saldo", "Ajuste de saldo",
        "antes del ajuste", "EMPRESA EJEMPLO S.A.S.",
    ]
    borrables = {f["id"] for f in filas if f["se_puede_borrar"]}
    assert borrables == {nuevo}
    assert viejo not in borrables
    assert {f["origen"] for f in filas} == {"manual", "gmail"}

    total, cantidad = componer_saldo(configurada).ajustes_entre(*SEPTIEMBRE)
    assert cantidad == 2
    assert total == sum(f["monto_centavos"] for f in filas if f["tipo"] == "ajuste")
    assert componer_saldo(configurada).ajustes_entre(datetime(2026, 8, 1), datetime(2026, 9, 1)) == (0, 0)


def test_la_marca_de_la_lista_coincide_con_lo_que_permite_borrar(configurada, reloj, ruta):
    """Para cada fila, ``se_puede_borrar`` dice exactamente si ``borrar_ingreso`` funciona."""
    ingreso(configurada, 1_00, "2026-09-01T08:00")
    insertar_gmail(configurada, "ingreso", 2_00, "2026-09-02T08:00:00")
    ajuste_en(configurada, reloj, datetime(2026, 9, 3, 8, 0), 90_000_00)
    ingreso(configurada, 3_00, "2026-09-02T09:00")  # registrado después, fecha anterior
    ingreso(configurada, 4_00, "2026-09-04T08:00")
    ingreso(configurada, 5_00, "2026-09-05T08:00")

    for fila in componer_saldo(configurada).ingresos_y_ajustes_entre(*SEPTIEMBRE):
        otra = db.conectar(ruta)
        try:
            # Solo la comprobación, en una lectura que se deshace: la base no cambia.
            with db.lectura_consistente(otra):
                try:
                    componer_saldo(otra).comprobar_borrable(fila["id"])
                    permitido = True
                except BorradoNoPermitido:
                    permitido = False
        finally:
            otra.close()
        assert permitido == fila["se_puede_borrar"], fila


# --- Borrar: el saldo cambia exactamente en el monto ------------------------------------------

def test_borrar_ingreso_baja_el_saldo_exactamente_en_su_monto(configurada):
    insertar_gmail(configurada, "compra", 3_333_33, "2026-08-10T10:00:00")
    otro = ingreso(configurada, 1_00, "2026-08-11T10:00")
    id_ingreso = ingreso(configurada, 123_456_78, "2026-08-12T10:00")
    antes = componer_saldo(configurada).saldo_actual()

    assert componer_saldo(configurada).borrar_ingreso(id_ingreso) == (123_456_78, antes - 123_456_78)
    assert componer_saldo(configurada).saldo_actual() == antes - 123_456_78
    assert sql(configurada, "SELECT COUNT(*) FROM movimientos WHERE id = ?", (id_ingreso,)).fetchone()[0] == 0
    # Lo demás sigue igual.
    assert componer_saldo(configurada).borrar_ingreso(otro) == (1_00, antes - 123_456_78 - 1_00)
    assert componer_saldo(configurada).saldo_actual() == antes - 123_456_78 - 1_00 == 100_000_00 - 3_333_33


def test_borrar_ingreso_posterior_al_ultimo_ajuste(configurada, reloj):
    ajuste_en(configurada, reloj, datetime(2026, 9, 1, 8, 0), 95_000_00)
    ajuste_en(configurada, reloj, datetime(2026, 9, 2, 8, 0), 96_000_00)
    id_ingreso = ingreso(configurada, 10_000_00, "2026-09-03T08:00")
    assert componer_saldo(configurada).saldo_actual() == 106_000_00
    assert componer_saldo(configurada).borrar_ingreso(id_ingreso) == (10_000_00, 96_000_00)
    # Vuelve exactamente al saldo que se cuadró.
    assert componer_saldo(configurada).saldo_actual() == 96_000_00


def test_ingreso_en_el_mismo_segundo_que_el_ajuste_registrado_despues_se_borra(configurada, reloj):
    ajuste_en(configurada, reloj, datetime(2026, 9, 2, 8, 0, 0), 96_000_00)
    id_ingreso = ingreso(configurada, 5_00, "2026-09-02T08:00:00")
    assert componer_saldo(configurada).borrar_ingreso(id_ingreso)[0] == 5_00


# --- Borrar: casos prohibidos ----------------------------------------------------------------

def _prohibido(conn, movimiento_id, mensaje):
    antes, saldo_antes = foto(conn), componer_saldo(conn).saldo_actual()
    with pytest.raises(BorradoNoPermitido) as error:
        componer_saldo(conn).borrar_ingreso(movimiento_id)
    assert str(error.value) == mensaje
    assert foto(conn) == antes
    assert componer_saldo(conn).saldo_actual() == saldo_antes


def test_no_se_borra_un_ajuste(configurada, reloj):
    ajuste_en(configurada, reloj, datetime(2026, 9, 1, 8, 0), 95_000_00)
    id_ajuste = sql(configurada, "SELECT id FROM movimientos WHERE tipo = 'ajuste'").fetchone()[0]
    _prohibido(configurada, id_ajuste, saldo_politica.MENSAJE_NO_SE_BORRA_AJUSTE)


@pytest.mark.parametrize("tipo", ["ingreso", "compra", "transferencia"])
def test_no_se_borra_un_movimiento_de_gmail(configurada, tipo):
    id_gmail = insertar_gmail(configurada, tipo, 7_00, "2026-09-01T08:00:00")
    _prohibido(configurada, id_gmail, saldo_politica.MENSAJE_NO_SE_BORRA_GMAIL)


def test_no_se_borra_un_ingreso_anterior_al_ultimo_ajuste(configurada, reloj):
    id_ingreso = ingreso(configurada, 10_000_00, "2026-09-01T08:00")
    ajuste_en(configurada, reloj, datetime(2026, 9, 2, 8, 0), 95_000_00)
    _prohibido(configurada, id_ingreso, saldo_politica.MENSAJE_ANTERIOR_AL_AJUSTE)


def test_no_se_borra_si_hay_un_ajuste_posterior_aunque_no_sea_el_ultimo_registrado(configurada, reloj):
    id_ingreso = ingreso(configurada, 10_000_00, "2026-09-01T08:00")
    ajuste_en(configurada, reloj, datetime(2026, 9, 2, 8, 0), 95_000_00)
    ajuste_en(configurada, reloj, datetime(2026, 9, 3, 8, 0), 96_000_00)
    _prohibido(configurada, id_ingreso, saldo_politica.MENSAJE_ANTERIOR_AL_AJUSTE)


def test_no_se_borra_un_ingreso_registrado_despues_del_ajuste_con_fecha_anterior(configurada, reloj):
    """Se registró después del ajuste, pero su fecha es anterior: en la lista queda antes del ajuste."""
    ajuste_en(configurada, reloj, datetime(2026, 9, 10, 8, 0), 95_000_00)
    id_ingreso = ingreso(configurada, 10_000_00, "2026-09-09T08:00")
    _prohibido(configurada, id_ingreso, saldo_politica.MENSAJE_ANTERIOR_AL_AJUSTE)


def test_no_se_borra_un_ingreso_con_fecha_posterior_registrado_antes_del_ajuste(configurada, reloj):
    """Fecha unos minutos en el futuro (tolerancia del reloj), pero el ajuste ya lo contó."""
    reloj.poner(datetime(2026, 9, 10, 8, 0))
    id_ingreso = ingreso(configurada, 10_000_00, "2026-09-10T08:04")
    ajuste_en(configurada, reloj, datetime(2026, 9, 10, 8, 1), 95_000_00)
    _prohibido(configurada, id_ingreso, saldo_politica.MENSAJE_ANTERIOR_AL_AJUSTE)


def test_no_se_borra_un_gasto_manual(configurada):
    """Hoy no hay gastos manuales, pero si llegan no se borran por aquí."""
    with db.transaccion(configurada):
        id_compra = sql(
            configurada,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen) "
            "VALUES ('2026-09-01T08:00:00', 100, 'compra', 'TIENDA INVENTADA', 'manual')",
        ).lastrowid
    _prohibido(configurada, id_compra, saldo_politica.MENSAJE_NO_SE_BORRA_GASTO)


@pytest.mark.parametrize("movimiento_id", [999, 0, -1, True, "1", 1.0, None])
def test_inexistente_o_id_invalido(configurada, movimiento_id):
    ingreso(configurada, 1_00, "2026-09-01T08:00")
    antes = foto(configurada)
    with pytest.raises(MovimientoNoEncontrado):
        componer_saldo(configurada).borrar_ingreso(movimiento_id)
    assert foto(configurada) == antes


def test_borrar_dos_veces(configurada):
    id_ingreso = ingreso(configurada, 1_00, "2026-09-01T08:00")
    componer_saldo(configurada).borrar_ingreso(id_ingreso)
    with pytest.raises(MovimientoNoEncontrado):
        componer_saldo(configurada).borrar_ingreso(id_ingreso)
    assert componer_saldo(configurada).saldo_actual() == 100_000_00


# --- Carreras: comprobación y borrado en una sola transacción inmediata --------------------------

def test_ajuste_en_curso_gana_y_el_ingreso_ya_no_se_borra(configurada, ruta, reloj):
    """Si un ajuste ya tiene la escritura, el borrado espera, lo ve y se niega."""
    id_ingreso = ingreso(configurada, 10_000_00, "2026-09-01T08:00")
    otra = db.conectar(ruta)
    sql(otra, "BEGIN IMMEDIATE")
    sql(
        otra,
        "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen) "
        "VALUES ('2026-09-15T12:00:00', -500, 'ajuste', 'Ajuste de saldo', 'manual')",
    )
    resultado = {}

    def borrar():
        c = db.conectar(ruta)
        try:
            componer_saldo(c).borrar_ingreso(id_ingreso)
            resultado["borrado"] = True
        except BorradoNoPermitido:
            resultado["borrado"] = False
        finally:
            c.close()

    hilo = threading.Thread(target=borrar)
    hilo.start()
    hilo.join(0.3)
    assert hilo.is_alive()  # esperando la escritura
    otra.commit()
    otra.close()
    hilo.join(5)
    assert not hilo.is_alive()
    assert resultado["borrado"] is False
    assert sql(configurada, "SELECT COUNT(*) FROM movimientos WHERE id = ?", (id_ingreso,)).fetchone()[0] == 1


def test_ajuste_que_llega_durante_el_borrado_espera_y_no_cuenta_el_ingreso(configurada, ruta, reloj, monkeypatch):
    """Pausa entre la comprobación y el DELETE: el ajuste no puede meterse en medio."""
    id_ingreso = ingreso(configurada, 10_000_00, "2026-09-01T08:00")
    original = OperarSaldo.comprobar_borrable
    comprobado, seguir = threading.Event(), threading.Event()

    def comprobar_y_pausar(conn, movimiento_id):
        monto = original(conn, movimiento_id)
        comprobado.set()
        assert seguir.wait(5)
        return monto

    monkeypatch.setattr(OperarSaldo, "comprobar_borrable", comprobar_y_pausar)
    resultado = {}

    def borrar():
        c = db.conectar(ruta)
        try:
            resultado["monto"], resultado["saldo"] = componer_saldo(c).borrar_ingreso(id_ingreso)
        finally:
            c.close()

    def ajustar():
        c = db.conectar(ruta)
        try:
            resultado["diferencia"] = componer_saldo(c).ajustar_saldo(95_000_00)
        finally:
            c.close()
        ajuste_hecho.set()

    ajuste_hecho = threading.Event()
    hilo_borrar = threading.Thread(target=borrar)
    hilo_borrar.start()
    assert comprobado.wait(5)
    hilo_ajuste = threading.Thread(target=ajustar)
    hilo_ajuste.start()
    assert not ajuste_hecho.wait(0.3)  # el ajuste no puede escribir mientras dura el borrado
    seguir.set()
    hilo_borrar.join(5)
    hilo_ajuste.join(5)
    assert ajuste_hecho.is_set()

    monkeypatch.setattr(OperarSaldo, "comprobar_borrable", original)
    assert resultado["monto"] == 10_000_00
    assert resultado["saldo"] == 100_000_00  # leído antes de que entrara el ajuste
    # El ajuste se calculó ya sin el ingreso borrado: 95.000 − 100.000.
    assert resultado["diferencia"] == -5_000_00
    assert componer_saldo(configurada).saldo_actual() == 95_000_00


def test_dos_borrados_simultaneos_del_mismo_ingreso_bajan_el_saldo_una_vez(configurada, ruta, monkeypatch):
    id_ingreso = ingreso(configurada, 10_000_00, "2026-09-01T08:00")
    original = OperarSaldo.comprobar_borrable
    primero = threading.Event()

    def comprobar_lento(conn, movimiento_id):
        monto = original(conn, movimiento_id)
        primero.set()
        threading.Event().wait(0.3)  # deja al otro llegar mientras este borra
        return monto

    monkeypatch.setattr(OperarSaldo, "comprobar_borrable", comprobar_lento)
    resultados = []
    barrera = threading.Barrier(2)

    def borrar():
        c = db.conectar(ruta)
        try:
            barrera.wait(5)
            resultados.append(componer_saldo(c).borrar_ingreso(id_ingreso)[0])
        except MovimientoNoEncontrado:
            resultados.append("no existe")
        finally:
            c.close()

    hilos = [threading.Thread(target=borrar) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(10)
    assert sorted(resultados, key=str) == [10_000_00, "no existe"]
    monkeypatch.setattr(OperarSaldo, "comprobar_borrable", original)
    assert componer_saldo(configurada).saldo_actual() == 100_000_00


def test_el_saldo_devuelto_se_lee_dentro_de_la_transaccion(configurada, ruta, monkeypatch):
    """Una compra que llega mientras se borra no se cuela entre el DELETE y la lectura del saldo."""
    id_ingreso = ingreso(configurada, 10_000_00, "2026-09-01T08:00")
    original = OperarSaldo.saldo_actual
    leido, seguir, compra_hecha = threading.Event(), threading.Event(), threading.Event()
    dentro = []

    def saldo_y_pausar(conn):
        dentro.append(conn._unidad.en_transaccion())
        valor = original(conn)
        leido.set()
        assert seguir.wait(5)
        return valor

    monkeypatch.setattr(OperarSaldo, "saldo_actual", saldo_y_pausar)
    resultado = {}

    def borrar():
        c = db.conectar(ruta)
        try:
            resultado["borrado"] = componer_saldo(c).borrar_ingreso(id_ingreso)
        finally:
            c.close()

    def comprar():
        c = db.conectar(ruta)
        try:
            with db.transaccion(c, inmediata=True):
                sql(
                    c,
                    "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen, gmail_id) "
                    "VALUES ('2026-09-15T11:00:00', 700000, 'compra', 'TIENDA INVENTADA', 'gmail', 'msg-durante')",
                )
        finally:
            c.close()
        compra_hecha.set()

    hilo_borrar = threading.Thread(target=borrar)
    hilo_borrar.start()
    assert leido.wait(5)
    hilo_compra = threading.Thread(target=comprar)
    hilo_compra.start()
    assert not compra_hecha.wait(0.3)  # la compra espera a que termine el borrado
    seguir.set()
    hilo_borrar.join(5)
    hilo_compra.join(5)
    assert compra_hecha.is_set()

    monkeypatch.setattr(OperarSaldo, "saldo_actual", original)
    assert dentro == [True]
    assert resultado["borrado"] == (10_000_00, 100_000_00)  # sin la compra, que entró después
    assert componer_saldo(configurada).saldo_actual() == 100_000_00 - 7_000_00


def test_borrar_sin_saldo_configurado_devuelve_saldo_none(conn, reloj):
    with db.transaccion(conn):
        id_ingreso = sql(
            conn,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, origen) "
            "VALUES ('2026-09-01T08:00:00', 100, 'ingreso', 'Efectivo inventado', 'manual')",
        ).lastrowid
    assert componer_saldo(conn).borrar_ingreso(id_ingreso) == (100, None)
