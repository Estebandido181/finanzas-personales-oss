"""Pruebas de finanzas.sincronizacion con un cliente de Gmail falso (sin red)."""

from __future__ import annotations
from finanzas.modulos.sincronizacion import registro_sqlite

import base64
import logging
import sqlite3
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from finanzas import db, sincronizacion
from finanzas.modulos.sincronizacion.adaptadores.avisos import extractor
from finanzas.gmail import (
    ZONA_COLOMBIA,
    CorreoGmail,
    ErrorAutorizacionGmail,
    correo_desde_mensaje,
    html_a_texto,
)
from finanzas.sincronizacion import (
    ResultadoSincronizacion,
    SincronizacionNoConfigurada,
    extraer_aviso,
    localizar_aviso,
    sincronizar,
)
from tests.soporte.gmail_falso import ENCABEZADOS_LEGITIMOS, LEGITIMO, ClienteFalso, correo_fixture
from tests.soporte.ayudas_db import sql


def _b64(texto: str) -> str:
    return base64.urlsafe_b64encode(texto.encode("utf-8")).decode().rstrip("=")


def _correo(gmail_id: str) -> CorreoGmail:
    return correo_fixture(gmail_id)


@pytest.fixture
def ruta_db(tmp_path):
    return str(tmp_path / "sinc.db")


@pytest.fixture
def conn(ruta_db):
    conexion = db.conectar(ruta_db)
    db.inicializar(conexion)
    yield conexion
    conexion.close()


def _configurar_saldo(conn, fecha_inicio="2026-08-01"):
    with db.transaccion(conn):
        sql(
            conn,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, ?, ?)",
            (100000000, fecha_inicio),
        )


def _movimientos(conn):
    return {
        fila["gmail_id"]: dict(fila)
        for fila in sql(conn, "SELECT * FROM movimientos ORDER BY gmail_id")
    }


# --- Movimientos ------------------------------------------------------------------

def test_avisos_se_convierten_en_movimientos(conn):
    _configurar_saldo(conn)
    cliente = ClienteFalso()

    resultado = sincronizar(conn, cliente)

    assert resultado == ResultadoSincronizacion(nuevos=3, duplicados=0, no_reconocidos=1, errores=0)
    assert cliente.llamadas_listar == [date(2026, 8, 1)]
    movimientos = _movimientos(conn)
    assert set(movimientos) == {"msg-0001", "msg-0002", "msg-0004"}

    compra = movimientos["msg-0001"]
    assert compra["tipo"] == "compra"
    assert compra["monto_centavos"] == 24570000
    assert compra["fecha_hora"] == "2026-08-07T16:42:00"
    assert compra["descripcion"] == "MERPAGO*TIENDAEJEMPLO"
    assert compra["origen"] == "gmail"
    assert compra["categoria_id"] is None

    transferencia = movimientos["msg-0002"]
    assert transferencia["tipo"] == "transferencia"
    assert transferencia["monto_centavos"] == 450000
    assert transferencia["fecha_hora"] == "2026-08-14T19:05:00"
    assert transferencia["descripcion"] == "*0000"

    anidado = movimientos["msg-0004"]
    assert (anidado["monto_centavos"], anidado["descripcion"]) == (6863000, "RESTAURANTE EJEMPLO")


def test_sincronizar_dos_veces_no_duplica_ni_descarga_otra_vez(conn):
    _configurar_saldo(conn)
    sincronizar(conn, ClienteFalso())

    segundo = ClienteFalso()
    resultado = sincronizar(conn, segundo)

    assert resultado == ResultadoSincronizacion()
    assert segundo.llamadas_obtener == []  # ni siquiera se descargan
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 3
    assert sql(conn, "SELECT COUNT(*) FROM correos_no_reconocidos").fetchone()[0] == 1


def test_ids_repetidos_en_la_lista_se_procesan_una_vez(conn):
    _configurar_saldo(conn)

    class Repite(ClienteFalso):
        def listar_ids(self, desde):
            return ["msg-0001", "msg-0001"]

    cliente = Repite()
    assert sincronizar(conn, cliente).nuevos == 1
    assert cliente.llamadas_obtener == ["msg-0001"]


# --- No reconocidos ------------------------------------------------------------------

# msg-0003 ("Recibiste un pago de ...") sigue sin reconocerse tras el ítem 09 (D12):
# solo se lee la redacción "Recibiste una transferencia por ... en tu cuenta **dddd".
def test_no_reconocido_solo_guarda_id_fecha_y_asunto(conn):
    _configurar_saldo(conn)
    sincronizar(conn, ClienteFalso())

    columnas = [fila[1] for fila in sql(conn, "PRAGMA table_info(correos_no_reconocidos)")]
    assert columnas == ["gmail_id", "fecha", "asunto"]  # ninguna columna para el cuerpo

    filas = [dict(f) for f in sql(conn, "SELECT * FROM correos_no_reconocidos")]
    assert filas == [{
        "gmail_id": "msg-0003",
        "fecha": "2026-08-10T09:15:00",
        "asunto": "Recibiste un pago (ejemplo)",
    }]


def test_el_cuerpo_no_queda_en_ninguna_parte_de_la_base(conn, ruta_db):
    _configurar_saldo(conn)
    sincronizar(conn, ClienteFalso())
    conn.close()
    contenido = Path(ruta_db).read_bytes()
    for fragmento in (b"NOMBRE EJEMPLO", b"Recibiste un pago de", b"Consejos de seguridad", b"Estamos cerca"):
        assert fragmento not in contenido


# --- Fecha de inicio ---------------------------------------------------------------

def test_correo_anterior_a_la_fecha_de_inicio_se_descarta(conn):
    _configurar_saldo(conn, "2026-08-08")
    anterior = replace(_correo("msg-0001"), fecha=datetime(2026, 8, 7, 23, 59, tzinfo=ZONA_COLOMBIA))
    cliente = ClienteFalso({"msg-0001": anterior, "msg-0002": _correo("msg-0002")})

    resultado = sincronizar(conn, cliente)

    assert cliente.llamadas_listar == [date(2026, 8, 8)]
    assert resultado == ResultadoSincronizacion(nuevos=1)
    assert set(_movimientos(conn)) == {"msg-0002"}
    assert sql(conn, "SELECT COUNT(*) FROM correos_no_reconocidos").fetchone()[0] == 0


def test_correo_del_mismo_dia_de_inicio_se_acepta(conn):
    _configurar_saldo(conn, "2026-08-07")
    temprano = replace(_correo("msg-0001"), fecha=datetime(2026, 8, 7, 0, 0, tzinfo=ZONA_COLOMBIA))
    assert sincronizar(conn, ClienteFalso({"msg-0001": temprano})).nuevos == 1


def test_sin_configuracion_de_saldo_no_llama_a_gmail(conn):
    cliente = ClienteFalso()
    with pytest.raises(SincronizacionNoConfigurada, match="fecha de inicio"):
        sincronizar(conn, cliente)
    assert cliente.llamadas_listar == []
    assert cliente.llamadas_obtener == []


def test_ejecutar_sin_configuracion_ni_crea_el_cliente(conn):
    def fabrica():
        raise AssertionError("no debía crear el cliente")

    with pytest.raises(SincronizacionNoConfigurada):
        sincronizacion.ejecutar(conn, fabrica)


# --- Errores -------------------------------------------------------------------------

def test_error_en_un_correo_no_detiene_los_demas(conn):
    _configurar_saldo(conn)
    cliente = ClienteFalso(fallan={"msg-0099": ConnectionError("fallo de red inventado")})

    resultado = sincronizar(conn, cliente)

    assert resultado == ResultadoSincronizacion(nuevos=3, no_reconocidos=1, errores=1)
    # El que falló no queda registrado: se reintenta en la siguiente sincronización.
    assert "msg-0099" not in _movimientos(conn)
    otra = ClienteFalso(fallan={"msg-0099": ConnectionError("otra vez")})
    assert sincronizar(conn, otra).errores == 1
    assert otra.llamadas_obtener == ["msg-0099"]


def test_error_al_procesar_no_pierde_los_ya_guardados(conn, monkeypatch):
    _configurar_saldo(conn)
    original = registro_sqlite._guardar_movimiento

    def falla_en_el_segundo(conexion, gmail_id, movimiento, **kwargs):
        if gmail_id == "msg-0002":
            raise sqlite3.OperationalError("database is locked")
        return original(conexion, gmail_id, movimiento, **kwargs)

    monkeypatch.setattr(registro_sqlite, "_guardar_movimiento", falla_en_el_segundo)
    resultado = sincronizar(conn, ClienteFalso())

    assert resultado == ResultadoSincronizacion(nuevos=2, no_reconocidos=1, errores=1)
    assert set(_movimientos(conn)) == {"msg-0001", "msg-0004"}


def test_error_de_autorizacion_detiene_pero_conserva_lo_guardado(conn):
    _configurar_saldo(conn)
    correos = {"msg-0001": _correo("msg-0001")}
    cliente = ClienteFalso(correos, fallan={"msg-0002": ErrorAutorizacionGmail("revocado")})
    with pytest.raises(ErrorAutorizacionGmail):
        sincronizar(conn, cliente)
    assert set(_movimientos(conn)) == {"msg-0001"}


# --- Concurrencia -----------------------------------------------------------------------

def test_insercion_concurrente_del_mismo_gmail_id_no_duplica(conn, ruta_db):
    """Otro proceso (el temporizador) guarda el mismo correo entre la
    comprobación de ids y la inserción: no se duplica y cuenta como duplicado."""
    _configurar_saldo(conn)
    otro_proceso = db.conectar(ruta_db)

    class Carrera(ClienteFalso):
        def obtener(self, gmail_id):
            correo = super().obtener(gmail_id)
            sincronizar(otro_proceso, ClienteFalso({gmail_id: correo}))
            return correo

    try:
        resultado = sincronizar(conn, Carrera({"msg-0001": _correo("msg-0001"), "msg-0003": _correo("msg-0003")}))
    finally:
        otro_proceso.close()

    assert resultado == ResultadoSincronizacion(duplicados=2)
    assert sql(conn, "SELECT COUNT(*) FROM movimientos WHERE gmail_id = 'msg-0001'").fetchone()[0] == 1
    assert sql(conn, "SELECT COUNT(*) FROM correos_no_reconocidos").fetchone()[0] == 1


def test_restriccion_check_no_se_confunde_con_duplicado(conn, monkeypatch):
    """ON CONFLICT(gmail_id) solo ignora el choque del id: otro fallo es un error."""
    from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import MovimientoExtraido

    _configurar_saldo(conn)
    monkeypatch.setattr(
        sincronizacion.extractor, "extraer",
        lambda texto: MovimientoExtraido("compra", 0, datetime(2026, 8, 7), "X"),
    )
    resultado = sincronizar(conn, ClienteFalso({"msg-0001": _correo("msg-0001")}))
    assert resultado == ResultadoSincronizacion(errores=1)


# --- Logs ------------------------------------------------------------------------------

def test_logs_sin_montos_comercios_cuentas_ni_asuntos(conn, caplog):
    _configurar_saldo(conn)
    cliente = ClienteFalso(fallan={"msg-0099": ValueError("Compraste $245.700,00 en MERPAGO")})
    with caplog.at_level(logging.DEBUG):
        sincronizar(conn, cliente)

    texto = caplog.text
    assert "msg-0001" in texto and "msg-0099" in texto  # ids sí
    for prohibido in (
        "245.700", "24570000", "4,500", "450000", "68.630", "MERPAGO", "TIENDAEJEMPLO",
        "RESTAURANTE", "*1234", "3000000000", "NOMBRE EJEMPLO", "Alerta de", "Recibiste",
        "Bancolombia:",
    ):
        assert prohibido not in texto, prohibido


# --- Localizar el aviso ---------------------------------------------------------------

AVISO_COMPRA = (
    "Compraste $68.630,00 en MERPAGO*TIENDA con tu T.Deb *1234, el 15/08/2026 a las 14:32."
)


def test_localizar_aviso_salta_el_encabezado():
    texto = (
        "¡Listo! Todo salió bien con tus movimientos\n\n"
        "Bancolombia: Compraste $1.000,00 en TIENDA con tu T.Deb *1234,\n"
        "el 07/08/2026 a las 16:42.\n\n"
        "Bancolombia: Transferiste otro bloque"
    )
    assert localizar_aviso(texto).startswith(
        "Bancolombia: Compraste $1.000,00 en TIENDA con tu T.Deb *1234, el 07/08/2026 a las 16:42."
    )
    movimiento = extraer_aviso(texto)
    assert (movimiento.monto_centavos, movimiento.descripcion) == (100000, "TIENDA")


@pytest.mark.parametrize(
    "html",
    [
        # Dos <br> seguidos dentro del párrafo del aviso.
        "<p>Bancolombia: Compraste $68.630,00 en MERPAGO*TIENDA con tu T.Deb *1234,<br><br>"
        "el 15/08/2026 a las 14:32.</p>",
        # "Bancolombia:" en su propio párrafo.
        "<p><b>Bancolombia:</b></p><p>" + AVISO_COMPRA + "</p>",
        # "Bancolombia:" en su propia celda.
        "<table><tr><td><b>Bancolombia:</b></td><td>" + AVISO_COMPRA + "</td></tr></table>",
        # Carácter invisible y minúsculas en el prefijo.
        "<p>\u200bbancolombia: " + AVISO_COMPRA + "</p>",
    ],
    ids=["br_doble", "prefijo_parrafo_aparte", "prefijo_celda_aparte", "invisible_y_minusculas"],
)
def test_aviso_partido_en_bloques_se_reconoce(html):
    for movimiento in (extraer_aviso(html_a_texto(html)), extractor.extraer(localizar_aviso(html_a_texto(html)))):
        assert movimiento is not None
        assert (movimiento.monto_centavos, movimiento.descripcion) == (6863000, "MERPAGO*TIENDA")
        assert movimiento.fecha_hora == datetime(2026, 8, 15, 14, 32)


def test_aviso_sin_prefijo_queda_como_no_reconocido(conn):
    """Decisión del dueño (ronda 3): sin "Bancolombia:" delante no se acepta
    como aviso, aunque el resto coincida. Antes esta prueba esperaba un
    movimiento; ahora el correo queda registrado para revisión."""
    _configurar_saldo(conn)
    correo = CorreoGmail(
        "msg-0100", datetime(2026, 8, 15, 14, 33, tzinfo=ZONA_COLOMBIA), "Aviso (ejemplo)",
        "¡Listo! Todo salió bien con tus movimientos\n\n" + AVISO_COMPRA + "\n\nPie de página",
        **LEGITIMO,
    )
    assert extraer_aviso(correo.texto) is None
    assert sincronizar(conn, ClienteFalso({"msg-0100": correo})) == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == {}


AVISO_TRANSFERENCIA = (
    "Transferiste $6,000.00 desde tu cuenta *1234 a la cuenta *5678 el 16/08/26 a las 09:15."
)


@pytest.mark.parametrize(
    "texto",
    [
        "Bancolombia: Anulamos esta transacción y devolvimos el dinero a tu cuenta: "
        + AVISO_COMPRA + " Estamos cerca.",
        "Bancolombia: ¿Reconoces este movimiento? " + AVISO_COMPRA + " Si no fuiste tú, llámanos al 000 000 0000.",
        "Bancolombia: Si no compraste $68.630,00 en MERPAGO*TIENDA con tu T.Deb *1234, el 15/08/2026 "
        "a las 14:32. bloquea tu tarjeta.",
        "Bancolombia: Tu transferencia fue rechazada. Detalle: " + AVISO_TRANSFERENCIA,
    ],
    ids=["anulacion", "reconoces", "si_no_compraste", "transferencia_rechazada"],
)
def test_correo_que_cita_un_aviso_no_inventa_movimiento(conn, texto):
    _configurar_saldo(conn)
    assert extraer_aviso(texto) is None
    correo = CorreoGmail(
        "msg-0200", datetime(2026, 8, 16, 10, 0, tzinfo=ZONA_COLOMBIA), "Novedad (ejemplo)", texto, **LEGITIMO
    )
    assert sincronizar(conn, ClienteFalso({"msg-0200": correo})) == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == {}


@pytest.mark.parametrize(
    "promocion",
    [
        "Compraste $5.000,00 en tu tienda favorita y ganaste puntos. ",
        # Con prefijo: el comercio se extendería hasta el aviso real y el monto
        # sería 5.000,00; se descarta porque la descripción contiene otro aviso.
        "Bancolombia: Compraste $5.000,00 en tu tienda favorita y ganaste puntos. ",
    ],
    ids=["sin_prefijo", "con_prefijo"],
)
def test_promocion_antes_del_aviso_real_queda_no_reconocido(promocion):
    # Antes: test_promocion_antes_del_aviso_real_toma_el_monto_correcto.
    # ítem 21: antes se reconocía el aviso real; ahora queda no reconocido
    # porque la promoción no es un encabezado conocido: el aviso está citado.
    # Lo importante se mantiene: nunca se toma el monto de la promoción.
    assert extraer_aviso(promocion + "Bancolombia: " + AVISO_COMPRA + " Estamos cerca.") is None


def test_correo_educativo_que_cita_un_aviso_completo_queda_no_reconocido():
    """Un correo educativo que cita un aviso completo con su prefijo. Antes era
    el riesgo conocido ``test_riesgo_conocido_correo_educativo_que_cita_un_aviso_completo``."""
    texto = "Así se ven nuestras alertas: Bancolombia: " + AVISO_COMPRA + " Nunca te pediremos claves."
    # ítem 21: antes se reconocía (riesgo documentado); ahora queda no
    # reconocido porque "Así se ven nuestras alertas:" no es un encabezado conocido.
    assert extraer_aviso(texto) is None


def test_mencion_suelta_no_se_confunde_con_un_aviso():
    texto = "Recuerda: si compraste algo que no reconoces, llámanos. Transferiste dinero? Revisa."
    assert extraer_aviso(texto) is None


def test_aviso_tras_un_inicio_incompleto_queda_no_reconocido():
    # Antes: test_se_queda_con_la_primera_posicion_que_reconoce.
    texto = (
        "Compraste algo incompleto. Bancolombia: " + AVISO_COMPRA
        + " Bancolombia: Transferiste $4,500.00 desde tu cuenta *1234 a la cuenta *5678 "
        "el 14/08/26 a las 19:05."
    )
    # ítem 21: antes se reconocía la compra; ahora queda no reconocido porque
    # "Compraste algo incompleto." no es un encabezado conocido y ya no se
    # busca una segunda posición.
    assert extraer_aviso(texto) is None


def test_texto_plano_de_relleno_usa_el_html(conn):
    """Si la parte text/plain no trae el aviso, se prueba con la HTML."""
    _configurar_saldo(conn)
    mensaje = {
        "id": "msg-0101",
        "internalDate": str(int(datetime(2026, 8, 15, 14, 33, tzinfo=ZONA_COLOMBIA).timestamp() * 1000)),
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [*ENCABEZADOS_LEGITIMOS, {"name": "Subject", "value": "Aviso (ejemplo)"}],
            "parts": [
                {"mimeType": "text/plain",
                 "body": {"data": _b64("Tu cliente de correo no muestra HTML. Abre la versión web.")}},
                {"mimeType": "text/html",
                 "body": {"data": _b64("<p>Bancolombia: " + AVISO_COMPRA + "</p>")}},
            ],
        },
    }
    correo = correo_desde_mensaje(mensaje)
    assert "Abre la versión web" in correo.texto
    assert len(correo.textos) == 2

    assert sincronizar(conn, ClienteFalso({"msg-0101": correo})) == ResultadoSincronizacion(nuevos=1)
    assert _movimientos(conn)["msg-0101"]["descripcion"] == "MERPAGO*TIENDA"


def test_localizar_aviso_sin_prefijo_devuelve_texto_normalizado():
    assert localizar_aviso("  Compraste   algo\n\n en  X ") == "Compraste algo en X"


# --- Comando python -m finanzas.sincronizacion -------------------------------------------

@pytest.fixture
def entorno(monkeypatch, ruta_db):
    from finanzas.seguridad import generar_hash

    monkeypatch.setenv("APP_PASSWORD_HASH", generar_hash("clave-de-prueba-inventada"))
    monkeypatch.setenv("SESSION_SECRET", "secreto-de-prueba-inventado-de-mas-de-32-caracteres")
    monkeypatch.setenv("DB_PATH", ruta_db)
    monkeypatch.setenv("GMAIL_TOKEN", "/ruta/inventada/token.json")
    monkeypatch.delenv("GMAIL_REMITENTE", raising=False)


def test_comando_exito_codigo_0(entorno, conn, capsys):
    _configurar_saldo(conn)
    codigo = sincronizacion.main([], fabrica_cliente=lambda config: ClienteFalso())
    assert codigo == 0
    salida = capsys.readouterr().out
    assert "3 nuevos, 0 duplicados, 1 no reconocidos, 0 errores" in salida
    assert "0 rechazados por remitente o autenticación" in salida


def test_comando_con_errores_codigo_1(entorno, conn):
    _configurar_saldo(conn)
    fabrica = lambda config: ClienteFalso(fallan={"msg-0099": TimeoutError()})  # noqa: E731
    assert sincronizacion.main([], fabrica_cliente=fabrica) == 1


def test_comando_sin_saldo_configurado_codigo_2(entorno, conn, capsys):
    assert sincronizacion.main([], fabrica_cliente=lambda config: ClienteFalso()) == 2
    assert "fecha de inicio" in capsys.readouterr().err


def test_comando_sin_gmail_token_codigo_2(entorno, conn, monkeypatch, capsys):
    _configurar_saldo(conn)
    monkeypatch.delenv("GMAIL_TOKEN")
    assert sincronizacion.main([]) == 2
    assert "GMAIL_TOKEN" in capsys.readouterr().err


def test_comando_token_inexistente_codigo_2(entorno, conn, capsys):
    _configurar_saldo(conn)
    assert sincronizacion.main([]) == 2  # usa ClienteGmailReal con una ruta que no existe
    assert "autorizar" in capsys.readouterr().err


def test_comando_sin_configuracion_de_la_app_codigo_2(entorno, monkeypatch):
    monkeypatch.delenv("SESSION_SECRET")
    assert sincronizacion.main([]) == 2
