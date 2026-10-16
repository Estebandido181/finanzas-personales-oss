"""Casos borde del ítem 05: saldo, ingresos manuales y ajustes.

Complementa ``test_saldo.py`` y ``test_api_saldo.py``. Todos los montos,
fechas, comercios y correos son inventados.
"""

from __future__ import annotations
from finanzas.bootstrap.saldo import componer_saldo
from finanzas.modulos.saldo import politica as saldo_politica
from finanzas.modulos.saldo import contratos as saldo_contratos
from finanzas.modulos.saldo.aplicacion import OperarSaldo

import base64
import json
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finanzas import db
from finanzas.compartido import hora
from finanzas.compartido.config import Config
from finanzas.gmail import correo_desde_mensaje
from finanzas.modulos.saldo.contratos import ErrorSaldo
from finanzas.sincronizacion import sincronizar
from finanzas.web.app import crear_app

from tests.soporte.ayudas_api import ClienteApi, hash_barato
from tests.soporte.gmail_falso import ClienteFalso, correo_fixture
from tests.soporte.ayudas_db import sql

INICIO = date(2026, 8, 1)
AHORA = datetime(2026, 9, 15, 12, 0, 0)  # hora de Colombia fija
ZONA_COL = timezone(timedelta(hours=-5))
BORDES = Path(__file__).resolve().parents[2] / "fixtures" / "gmail" / "bordes"

CONTRASENA = "clave-de-prueba-inventada-bordes"
SECRETO = "secreto-de-prueba-inventado-bordes-de-mas-de-32-caracteres"


# --- Utilidades -------------------------------------------------------------------------

@pytest.fixture
def ruta(tmp_path):
    return str(tmp_path / "bordes.db")


@pytest.fixture
def conn(ruta):
    c = db.conectar(ruta)
    db.inicializar(c)
    yield c
    c.close()


@pytest.fixture
def reloj(monkeypatch):
    """Fija la hora de Colombia (``reloj.poner`` la cambia)."""

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


_ids = iter(range(1, 10**6))


def insertar(conn, tipo, monto, fecha_hora, descripcion="MOVIMIENTO INVENTADO"):
    origen = "gmail" if tipo in ("compra", "transferencia") else "manual"
    gmail_id = f"borde-saldo-{next(_ids)}" if origen == "gmail" else None
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


def _correo_compra(gmail_id, texto_aviso, recibido):
    """Correo legítimo (encabezados del fixture de medianoche) con otro aviso y otra hora."""
    mensaje = json.loads((BORDES / "medianoche_colombia.json").read_text(encoding="utf-8"))
    mensaje["id"] = gmail_id
    mensaje["threadId"] = "hilo-" + gmail_id
    mensaje["internalDate"] = str(int(recibido.timestamp() * 1000))
    mensaje["payload"]["body"]["data"] = (
        base64.urlsafe_b64encode(texto_aviso.encode("utf-8")).decode().rstrip("=")
    )
    return correo_desde_mensaje(mensaje)


# --- Formato de fecha_hora ------------------------------------------------------------------

def test_mezcla_de_formatos_se_guarda_uniforme_y_cuenta_bien(conn, reloj):
    """Gmail, ingresos con y sin segundos y ajustes quedan como aaaa-mm-ddThh:mm:ss."""
    componer_saldo(conn).configurar(1_000_00, date(2026, 8, 10))
    # Sincronización real: compra el 10/08 a las 00:00 (cuenta) y otra el 09/08 23:59
    # recibida después de la medianoche (se guarda, pero es anterior al inicio).
    correos = [
        _correo_compra(
            "borde-mix-1",
            "Bancolombia: Compraste $100,00 en TIENDA UNO con tu T.Deb *1234, el 10/08/2026 a las 00:00.",
            datetime(2026, 8, 10, 0, 0, 30, tzinfo=ZONA_COL),
        ),
        _correo_compra(
            "borde-mix-2",
            "Bancolombia: Compraste $7,00 en TIENDA DOS con tu T.Deb *1234, el 09/08/2026 a las 23:59.",
            datetime(2026, 8, 10, 0, 1, 0, tzinfo=ZONA_COL),
        ),
    ]
    cliente = ClienteFalso({c.gmail_id: c for c in correos})
    assert sincronizar(conn, cliente).nuevos == 2
    componer_saldo(conn).registrar_ingreso(10_00, saldo_politica.leer_fecha_hora("2026-08-10T00:00"), "sin segundos")
    componer_saldo(conn).registrar_ingreso(20_00, saldo_politica.leer_fecha_hora("2026-08-10T08:30:45"), "con segundos")
    componer_saldo(conn).ajustar_saldo(900_00)

    filas = sql(conn, "SELECT fecha_hora, tipo, monto_centavos FROM movimientos ORDER BY id").fetchall()
    fechas = [f[0] for f in filas]
    assert fechas == [
        "2026-08-10T00:00:00",
        "2026-08-09T23:59:00",
        "2026-08-10T00:00:00",
        "2026-08-10T08:30:45",
        "2026-09-15T12:00:00",
    ]
    assert all(len(f) == 19 for f in fechas)
    # Antes del ajuste: 1.000 − 100 + 10 + 20 = 930 (los $7 del 09/08 no cuentan).
    assert filas[-1]["monto_centavos"] == 900_00 - 930_00
    assert componer_saldo(conn).saldo_actual() == 900_00


def test_movimiento_un_segundo_antes_del_inicio_no_cuenta_y_medianoche_si(configurada):
    insertar(configurada, "compra", 1_00, "2026-07-31T23:59:59")
    insertar(configurada, "transferencia", 2_00, "2026-07-31T23:59:00")
    assert componer_saldo(configurada).saldo_actual() == 100_000_00
    componer_saldo(configurada).registrar_ingreso(5_00, datetime(2026, 8, 1, 0, 0), "medianoche")
    assert componer_saldo(configurada).saldo_actual() == 100_005_00


def test_gasto_entre_hasta_medianoche_del_mes_siguiente(configurada):
    insertar(configurada, "compra", 1_00, "2026-08-31T23:59:59")
    insertar(configurada, "compra", 10_00, "2026-09-01T00:00:00")
    agosto = (datetime(2026, 8, 1), datetime(2026, 9, 1))
    assert componer_saldo(configurada).gasto_entre(*agosto) == 1_00
    assert componer_saldo(configurada).gasto_entre(datetime(2026, 9, 1), datetime(2026, 10, 1)) == 10_00
    # Mismo límite escrito como lo daría el formulario o con zona.
    assert componer_saldo(configurada).gasto_entre(INICIO_DT(), saldo_politica.leer_fecha_hora("2026-09-01T00:00")) == 1_00
    hasta_utc = datetime(2026, 9, 1, 5, 0, tzinfo=timezone.utc)
    assert componer_saldo(configurada).gasto_entre(INICIO_DT(), hasta_utc) == 1_00
    assert componer_saldo(configurada).gasto_entre(INICIO_DT(), hasta_utc + timedelta(seconds=1)) == 11_00


def INICIO_DT():
    return datetime(2026, 8, 1)


# --- Montos -------------------------------------------------------------------------------

def test_muchos_ajustes_sucesivos(configurada):
    insertar(configurada, "compra", 12_345_67, "2026-08-02T10:00:00")
    esperado_ajustes = []
    anterior = componer_saldo(configurada).saldo_actual()
    for i in range(60):
        real = (i * 7_919_13) % 500_000_00  # valores inventados, a veces iguales al anterior
        diferencia = componer_saldo(configurada).ajustar_saldo(real)
        assert diferencia == real - anterior
        if diferencia:
            esperado_ajustes.append(diferencia)
        assert componer_saldo(configurada).saldo_actual() == real
        anterior = real
    montos = [f[0] for f in sql(configurada,
        "SELECT monto_centavos FROM movimientos WHERE tipo = 'ajuste' ORDER BY id")]
    assert montos == esperado_ajustes
    assert 0 not in montos
    # Ningún ajuste es gasto.
    assert componer_saldo(configurada).gasto_entre(datetime(2026, 1, 1), datetime(2027, 1, 1)) == 12_345_67


def test_saldo_real_cero(configurada):
    assert componer_saldo(configurada).ajustar_saldo(0) == -100_000_00
    assert componer_saldo(configurada).saldo_actual() == 0
    assert componer_saldo(configurada).ajustar_saldo(0) == 0  # ya coincide
    assert contar(configurada, "ajuste") == 1


def test_saldo_inicial_cero_y_real_cero_no_guarda_nada(conn, reloj):
    componer_saldo(conn).configurar(0, INICIO)
    assert componer_saldo(conn).ajustar_saldo(0) == 0
    assert contar(conn) == 0
    # Un ajuste de 0 no cuenta como movimiento: todavía se puede reconfigurar.
    componer_saldo(conn).configurar(5_00, INICIO)
    assert componer_saldo(conn).saldo_actual() == 5_00


def test_montos_en_el_tope(conn, reloj):
    tope = saldo_politica.MAXIMO_CENTAVOS
    componer_saldo(conn).configurar(tope, INICIO)
    assert componer_saldo(conn).saldo_actual() == tope
    for _ in range(50):
        componer_saldo(conn).registrar_ingreso(tope, datetime(2026, 8, 2), "tope")
    assert componer_saldo(conn).saldo_actual() == 51 * tope
    # Ajuste al tope desde un saldo enorme: diferencia de −50 × 10^12, sin desbordes.
    assert componer_saldo(conn).ajustar_saldo(tope) == -50 * tope
    assert componer_saldo(conn).saldo_actual() == tope
    # Y desde muy negativo hasta el tope: la diferencia supera el tope y se guarda igual.
    insertar(conn, "compra", 3 * tope, "2026-08-03T00:00:00")
    assert componer_saldo(conn).ajustar_saldo(tope) == 3 * tope
    assert componer_saldo(conn).saldo_actual() == tope
    assert saldo_politica.leer_pesos("$10.000.000.000,00") == tope
    with pytest.raises(ErrorSaldo, match="demasiado grande"):
        saldo_politica.leer_pesos("10.000.000.000,01")


# --- leer_pesos ----------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("texto", "centavos"),
    [
        ("$1.234", 123400),
        ("$0,50", 50),
        ("$1234567,89", 123456789),
        ("00,50", 50),
        ("1.234,5", 123450),
        ("$1.234,5", 123450),
        ("　$ 1.234,5\t", 123450),  # espacios Unicode solo al inicio y al final
    ],
)
def test_leer_pesos_bordes_validos(texto, centavos):
    assert saldo_politica.leer_pesos(texto) == centavos


@pytest.mark.parametrize(
    "texto",
    [
        ",5",
        "$,5",
        "1. 234",
        "1 .234",
        "$ 1 234,00",
        "1,  50",
        "1 234",  # espacio duro como separador de miles
        "1 234",  # espacio fino (formato francés)
        "1\t234",
        "1\n234",
        "٥,٠٠",  # arábigo-índicas
        "۱۲۳",  # persas
        "१२३",  # devanagari
        "１.２３４",  # ancho completo con punto
        "1２3",  # mezcla
        "＄5",  # signo de pesos de ancho completo
        "5$",
    ],
)
def test_leer_pesos_bordes_invalidos(texto):
    with pytest.raises(ErrorSaldo):
        saldo_politica.leer_pesos(texto)


# --- Configuración ---------------------------------------------------------------------------

def test_configurar_a_las_23_59_de_colombia(conn, reloj):
    reloj.poner(datetime(2026, 9, 15, 23, 59, 59))  # en UTC ya es 16/09
    with pytest.raises(ErrorSaldo, match="futura"):
        componer_saldo(conn).configurar(1_00, date(2026, 9, 16))
    componer_saldo(conn).configurar(1_00, date(2026, 9, 15))
    assert componer_saldo(conn).leer_configuracion().fecha_inicio == date(2026, 9, 15)


def test_configurar_a_las_00_00_de_colombia(conn, reloj):
    reloj.poner(datetime(2026, 9, 16, 0, 0, 0))
    componer_saldo(conn).configurar(1_00, date(2026, 9, 16))
    assert componer_saldo(conn).leer_configuracion().fecha_inicio == date(2026, 9, 16)
    with pytest.raises(ErrorSaldo, match="futura"):
        componer_saldo(conn).configurar(1_00, date(2026, 9, 17))


def test_reconfigurar_varias_veces_sin_movimientos(conn, reloj):
    for valor, fecha in [(1_00, date(2026, 9, 1)), (0, date(2025, 1, 1)), (77_77, INICIO)]:
        componer_saldo(conn).configurar(valor, fecha)
        assert componer_saldo(conn).leer_configuracion() == saldo_contratos.Configuracion(valor, fecha)
        assert componer_saldo(conn).saldo_actual() == valor
    assert sql(conn, "SELECT COUNT(*) FROM configuracion_saldo").fetchone()[0] == 1


def test_reconfigurar_con_solo_correos_no_reconocidos_se_permite(conn, reloj):
    """``configurar`` solo mira ``movimientos``: los no reconocidos no lo bloquean."""
    componer_saldo(conn).configurar(1_000_00, INICIO)
    cliente = ClienteFalso({"msg-0003": correo_fixture("msg-0003")})
    resultado = sincronizar(conn, cliente)
    assert (resultado.nuevos, resultado.no_reconocidos) == (0, 1)
    assert contar(conn) == 0

    componer_saldo(conn).configurar(2_000_00, date(2026, 8, 5))
    assert componer_saldo(conn).leer_configuracion() == saldo_contratos.Configuracion(2_000_00, date(2026, 8, 5))
    # El registro del correo no reconocido se conserva.
    assert sql(conn, "SELECT COUNT(*) FROM correos_no_reconocidos").fetchone()[0] == 1


def test_despues_de_sincronizar_una_compra_ya_no_se_puede_reconfigurar(conn, reloj):
    componer_saldo(conn).configurar(1_000_00, INICIO)
    sincronizar(conn, ClienteFalso({"msg-0001": correo_fixture("msg-0001")}))
    with pytest.raises(ErrorSaldo, match="ajuste"):
        componer_saldo(conn).configurar(2_000_00, INICIO)


# --- Ingresos ---------------------------------------------------------------------------------

def test_ingreso_en_el_limite_de_5_minutos(configurada, reloj):
    limite = AHORA + timedelta(minutes=5)
    componer_saldo(configurada).registrar_ingreso(1_00, limite, "")
    # Los microsegundos se descartan antes de comparar: sigue en el límite.
    componer_saldo(configurada).registrar_ingreso(1_00, limite + timedelta(microseconds=999_999), "")
    with pytest.raises(ErrorSaldo, match="futura"):
        componer_saldo(configurada).registrar_ingreso(1_00, limite + timedelta(seconds=1), "")
    # El límite se mueve con el reloj.
    reloj.poner(AHORA + timedelta(minutes=1))
    componer_saldo(configurada).registrar_ingreso(1_00, limite + timedelta(seconds=1), "")
    assert contar(configurada, "ingreso") == 3


def test_ingreso_con_zona_ajena(configurada):
    tokio = timezone(timedelta(hours=9))
    hawai = timezone(timedelta(hours=-10))
    # 01/08 13:59:59 en Tokio = 31/07 23:59:59 en Colombia: anterior al inicio.
    with pytest.raises(ErrorSaldo, match="anterior"):
        componer_saldo(configurada).registrar_ingreso(1_00, datetime(2026, 8, 1, 13, 59, 59, tzinfo=tokio), "")
    id_ = componer_saldo(configurada).registrar_ingreso(1_00, datetime(2026, 8, 1, 14, 0, tzinfo=tokio), "")
    fila = sql(configurada, "SELECT fecha_hora FROM movimientos WHERE id = ?", (id_,)).fetchone()
    assert fila[0] == "2026-08-01T00:00:00"
    # 07:05 en Hawái = 12:05 en Colombia (ahora + 5 min): sí; 07:06: no.
    componer_saldo(configurada).registrar_ingreso(1_00, datetime(2026, 9, 15, 7, 5, tzinfo=hawai), "")
    with pytest.raises(ErrorSaldo, match="futura"):
        componer_saldo(configurada).registrar_ingreso(1_00, datetime(2026, 9, 15, 7, 6, tzinfo=hawai), "")
    assert componer_saldo(configurada).saldo_actual() == 100_002_00


# --- API (desde el ítem 20, la única interfaz) ------------------------------------------------

@pytest.fixture
def config(tmp_path):
    configuracion = Config(
        db_path=str(tmp_path / "api-bordes.db"),
        app_password_hash=hash_barato(CONTRASENA),
        session_secret=SECRETO,
        cookie_secure=False,
    )
    db.preparar(configuracion.db_path)  # la app exige la base migrada (ítem 22)
    return configuracion


@pytest.fixture
def gmail():
    return ClienteFalso()  # los 4 correos inventados de tests/fixtures/gmail


@pytest.fixture
def app(config, gmail):
    return crear_app(config, fabrica_cliente_gmail=lambda: gmail)


def _entrar(app, cookies=None) -> ClienteApi:
    """Cliente con sesión; con ``cookies``, reutiliza las de otro (como otra pestaña)."""
    c = TestClient(app, follow_redirects=False)
    if cookies:
        for nombre, valor in cookies.items():
            c.cookies.set(nombre, valor)
        return ClienteApi(c, c.get("/api/sesion").json()["csrf_token"])
    r = c.post("/api/sesion", json={"contrasena": CONTRASENA})
    assert r.status_code == 200
    return ClienteApi(c, r.json()["csrf_token"])


@pytest.fixture
def cliente(app, reloj):
    c = _entrar(app)
    with c.cliente:
        yield c


@pytest.fixture
def web(cliente):
    r = cliente.put(
        "/api/saldo/configuracion", json={"saldo_inicial_centavos": 1_000_000_00, "fecha_inicio": "2026-08-01"}
    )
    assert r.status_code == 200
    return cliente


def _db(config):
    return db.conectar(config.db_path)


def _token(cliente):
    """Token de un solo uso para registrar un ingreso (como lo recibe la app)."""
    return cliente.get("/api/saldo").json()["token_ingreso"]


def _ingreso(cliente, datos, token=None):
    """POST /api/ingresos con un token nuevo, como la app."""
    return cliente.post("/api/ingresos", json={**datos, "token": token if token is not None else _token(cliente)})


def _estado(config):
    c = sqlite3.connect(config.db_path)
    try:
        return (
            c.execute("SELECT * FROM configuracion_saldo").fetchall(),
            c.execute("SELECT * FROM movimientos ORDER BY id").fetchall(),
        )
    finally:
        c.close()


def test_configurar_a_las_23_59_y_00_00(cliente, config, reloj):
    reloj.poner(datetime(2026, 9, 15, 23, 59))
    assert cliente.get("/api/saldo").json()["hoy"] == "2026-09-15"
    datos = {"saldo_inicial_centavos": 1, "fecha_inicio": "2026-09-16"}
    r = cliente.put("/api/saldo/configuracion", json=datos)
    assert r.status_code == 400 and "futura" in r.json()["detalle"]
    assert _estado(config) == ([], [])
    reloj.poner(datetime(2026, 9, 16, 0, 0))
    assert cliente.get("/api/saldo").json()["hoy"] == "2026-09-16"
    assert cliente.put("/api/saldo/configuracion", json=datos).status_code == 200


# --- Integración con la sincronización real ------------------------------------------------------

def test_flujo_completo_con_sincronizacion_real(web, config, gmail):
    """Configurar → sincronizar (cliente falso) → ingreso → ajuste → resincronizar."""
    r = web.post("/api/sincronizacion")
    assert r.status_code == 200 and r.json()["estado"] == "ok"
    c = _db(config)
    try:
        compras = sql(
            c,
            "SELECT tipo, monto_centavos, fecha_hora FROM movimientos WHERE origen = 'gmail' ORDER BY fecha_hora"
        ).fetchall()
        gastado = sum(f["monto_centavos"] for f in compras)
        assert [f["tipo"] for f in compras] == ["compra", "transferencia", "compra"]
        assert gastado == 245_700_00 + 4_500_00 + 68_630_00
        assert all(len(f["fecha_hora"]) == 19 for f in compras)
        assert sql(c, "SELECT COUNT(*) FROM correos_no_reconocidos").fetchone()[0] == 1
        assert componer_saldo(c).saldo_actual() == 1_000_000_00 - gastado
    finally:
        c.close()

    datos = {"monto_centavos": 200_000_00, "fecha_hora": "2026-08-25T08:00", "descripcion": "Pago inventado"}
    assert _ingreso(web, datos).status_code == 201
    r = web.post("/api/ajustes", json={"saldo_real_centavos": 880_000_00})
    assert r.status_code == 200
    assert r.json() == {"registrado": True, "diferencia_centavos": -1_170_00, "saldo_centavos": 880_000_00}

    # Resincronizar no duplica nada ni mueve el saldo.
    r = web.post("/api/sincronizacion")
    assert r.status_code == 200 and r.json()["contadores"]["nuevos"] == 0
    assert web.get("/api/saldo").json()["saldo_centavos"] == 880_000_00
    c = _db(config)
    try:
        assert componer_saldo(c).saldo_actual() == 880_000_00
        assert contar(c) == 5
        # Solo compras y transferencias son gasto.
        assert componer_saldo(c).gasto_entre(datetime(2026, 8, 1), datetime(2026, 9, 1)) == gastado
        assert componer_saldo(c).gasto_entre(datetime(2026, 9, 1), datetime(2026, 10, 1)) == 0
    finally:
        c.close()
    r = web.put("/api/saldo/configuracion", json={"saldo_inicial_centavos": 1, "fecha_inicio": "2026-08-01"})
    assert r.status_code == 400


def test_fecha_de_inicio_posterior_excluye_compras_anteriores(cliente, config, gmail):
    # La compra del 07/08 y la transferencia del 14/08 quedan antes del inicio.
    r = cliente.put(
        "/api/saldo/configuracion", json={"saldo_inicial_centavos": 500_000_00, "fecha_inicio": "2026-08-15"}
    )
    assert r.status_code == 200
    assert cliente.post("/api/sincronizacion").status_code == 200
    c = _db(config)
    try:
        assert gmail.llamadas_listar == [date(2026, 8, 15)]
        assert componer_saldo(c).saldo_actual() == 500_000_00 - 68_630_00
    finally:
        c.close()


# --- Ronda 2: gasto_entre --------------------------------------------------------------------

def test_gasto_entre_con_microsegundos_respeta_desde_y_hasta(configurada):
    """Contrato: desde <= fecha_hora < hasta, también si los límites traen microsegundos."""
    insertar(configurada, "compra", 1_00, "2026-08-01T00:00:00")
    insertar(configurada, "compra", 10_00, "2026-09-01T00:00:00")
    desde = datetime(2026, 8, 1, 0, 0, 0, 500_000)  # 00:00:00 queda antes de desde
    hasta = datetime(2026, 9, 1, 0, 0, 0, 500_000)  # 00:00:00 queda antes de hasta
    assert componer_saldo(configurada).gasto_entre(desde, hasta) == 10_00
    # Con zona y microsegundos: 05:00:00.000001 UTC es 00:00:00.000001 en Colombia.
    desde_utc = datetime(2026, 8, 1, 5, 0, 0, 1, tzinfo=timezone.utc)
    assert componer_saldo(configurada).gasto_entre(desde_utc, datetime(2026, 8, 2)) == 0


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        (datetime(2026, 9, 1), datetime(2026, 8, 1)),
        (datetime(2026, 8, 1, 0, 0, 1), datetime(2026, 8, 1)),
        (datetime(2026, 8, 1, 0, 0, 0, 1), datetime(2026, 8, 1, 0, 0, 0, 1)),  # vacío
        (datetime(2026, 8, 1, 0, 0, 0, 2), datetime(2026, 8, 1, 0, 0, 0, 1)),
    ],
)
def test_gasto_entre_con_desde_mayor_o_igual_que_hasta_es_cero(configurada, desde, hasta):
    for segundo in range(3):
        insertar(configurada, "compra", 1_00, f"2026-08-01T00:00:0{segundo}")
    insertar(configurada, "compra", 1_00, "2026-08-15T10:00:00")
    assert componer_saldo(configurada).gasto_entre(desde, hasta) == 0


# --- Ronda 2: token de un solo uso para registrar un ingreso -----------------------------------

DATOS_INGRESO = {"monto_centavos": 1_000_00, "fecha_hora": "2026-08-05T09:00", "descripcion": "Ingreso inventado"}


def _ingresos(config):
    c = _db(config)
    try:
        return contar(c, "ingreso")
    finally:
        c.close()


def test_token_reutilizado_con_la_cookie_anterior(web, config, app):
    """Reenvío con la cookie de antes del primer envío (como un doble clic)."""
    token = _token(web)
    cookie_vieja = dict(web.cliente.cookies.items())
    assert _ingreso(web, DATOS_INGRESO, token).status_code == 201
    assert _ingresos(config) == 1

    with _entrar(app, cookie_vieja).cliente as otro:
        r = otro.post("/api/ingresos", json={**DATOS_INGRESO, "token": token}, headers={"X-CSRF-Token": web.csrf})
    assert r.status_code == 409
    assert "ya se envió" in r.json()["detalle"]
    assert _ingresos(config) == 1
    # Con la cookie nueva, también.
    assert _ingreso(web, DATOS_INGRESO, token).status_code == 409
    assert _ingresos(config) == 1


def test_token_reutilizado_tras_reiniciar_la_app_con_la_cookie_nueva(web, config, gmail):
    """Tras un reinicio (registro en memoria vacío), la lista de la sesión lo frena."""
    token = _token(web)
    assert _ingreso(web, DATOS_INGRESO, token).status_code == 201
    reiniciada = crear_app(config, fabrica_cliente_gmail=lambda: gmail)
    with _entrar(reiniciada, dict(web.cliente.cookies.items())).cliente as otro:
        r = otro.post("/api/ingresos", json={**DATOS_INGRESO, "token": token}, headers={"X-CSRF-Token": web.csrf})
    assert r.status_code == 409
    assert _ingresos(config) == 1


@pytest.mark.parametrize("token", ["", " ", "x" * 100, "../../etc", "<script>"])
def test_token_ausente_o_inventado_se_rechaza(web, config, token):
    _token(web)
    r = _ingreso(web, DATOS_INGRESO, token)
    assert r.status_code == 400
    assert _ingresos(config) == 0


def test_token_enorme_se_rechaza_sin_eco(web, config):
    _token(web)
    r = _ingreso(web, DATOS_INGRESO, "x" * 5000)
    assert r.status_code == 422
    assert "x" * 50 not in r.text
    assert _ingresos(config) == 0


def test_muchos_get_agotan_la_lista_de_10_tokens(web, config):
    tokens = [_token(web) for _ in range(11)]
    assert len(set(tokens)) == 11
    # El primero salió de la lista: se rechaza sin guardar nada.
    r = _ingreso(web, DATOS_INGRESO, tokens[0])
    assert r.status_code == 400
    assert "Vuelve a abrir la pantalla de saldo" in r.json()["detalle"]
    assert _ingresos(config) == 0
    # El segundo (el más antiguo que queda) y el último sí sirven.
    assert _ingreso(web, DATOS_INGRESO, tokens[1]).status_code == 201
    assert _ingreso(web, DATOS_INGRESO, tokens[-1]).status_code == 201
    assert _ingresos(config) == 2


def test_ingreso_invalido_no_gasta_el_token(web, config):
    token = _token(web)
    r = _ingreso(web, {**DATOS_INGRESO, "fecha_hora": "2026-07-31T23:59"}, token)  # antes del inicio
    assert r.status_code == 400
    assert _ingreso(web, DATOS_INGRESO, token).status_code == 201
    assert _ingresos(config) == 1


def test_doble_post_concurrente_guarda_un_solo_ingreso(web, config, app, monkeypatch):
    token = _token(web)
    cookies = dict(web.cliente.cookies.items())
    original = OperarSaldo.registrar_ingreso
    dentro = threading.Event()

    def registrar_lento(*args, **kwargs):
        dentro.set()
        threading.Event().wait(0.3)  # deja al otro envío llegar mientras este guarda
        return original(*args, **kwargs)

    monkeypatch.setattr(OperarSaldo, "registrar_ingreso", registrar_lento)
    clientes = [_entrar(app, cookies) for _ in range(2)]
    barrera = threading.Barrier(2)
    respuestas = [None, None]

    def enviar(i):
        barrera.wait()
        respuestas[i] = clientes[i].post("/api/ingresos", json={**DATOS_INGRESO, "token": token})

    hilos = [threading.Thread(target=enviar, args=(i,)) for i in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=10)
    assert sorted(r.status_code for r in respuestas) == [201, 409]
    assert _ingresos(config) == 1
