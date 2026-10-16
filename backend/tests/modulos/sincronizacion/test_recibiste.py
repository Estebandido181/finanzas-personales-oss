"""Pruebas del aviso "Recibiste una transferencia" (ingresos, D12 / ítem 09).

Todo es inventado: nombres (PERSONA EJEMPLO, MARÍA JOSÉ PEÑA ÑUÑEZ...),
cuentas (**1234, **5678, **0000) y teléfonos (018000000000).
"""

from __future__ import annotations
from finanzas.bootstrap.saldo import componer_saldo

import json
import logging
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from finanzas import categorizacion, db
from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import (
    MovimientoExtraido,
    extraer,
    extraer_compraste,
    extraer_recibiste,
    extraer_transferiste,
)
from finanzas.gmail import ZONA_COLOMBIA, CorreoGmail, correo_desde_mensaje
from finanzas.sincronizacion import ResultadoSincronizacion, extraer_aviso, sincronizar
from tests.soporte.gmail_falso import AUTENTICACION_LEGITIMA, LEGITIMO, REMITENTE_OFICIAL
from tests.soporte.ayudas_db import sql

AVISOS = Path(__file__).resolve().parents[2] / "fixtures" / "avisos"
GMAIL = Path(__file__).resolve().parents[2] / "fixtures" / "gmail"


def leer(nombre: str) -> str:
    return (AVISOS / nombre).read_text(encoding="utf-8")


def recibiste(
    monto="$160,000",
    nombre="PERSONA EJEMPLO",
    cuenta="**1234",
    fecha="29/09/2026",
    hora="10:00",
    final=". Si tienes dudas, hablemos: 018000000000. Siempre a tu lado.",
    prefijo="Bancolombia: ",
):
    return (
        f"{prefijo}Recibiste una transferencia por {monto} de {nombre} en tu cuenta {cuenta}, "
        f"el {fecha} a las {hora}{final}"
    )


# --- Extractor: fixtures -----------------------------------------------------------

@pytest.mark.parametrize(
    "archivo, esperado",
    [
        (
            "recibiste_basico.txt",
            MovimientoExtraido("ingreso", 16000000, datetime(2026, 9, 29, 10, 0), "PERSONA EJEMPLO"),
        ),
        (
            "recibiste_con_decimales.txt",
            MovimientoExtraido("ingreso", 16000000, datetime(2026, 9, 29, 10, 0), "PERSONA EJEMPLO"),
        ),
        (
            "recibiste_monto_grande.txt",
            MovimientoExtraido(
                "ingreso", 1234567890, datetime(2025, 12, 31, 23, 59, 58), "EMPRESA EJEMPLO S.A.S."
            ),
        ),
        (
            "recibiste_nombre_tilde_y_enie.txt",
            MovimientoExtraido(
                "ingreso", 50000, datetime(2027, 2, 1, 20, 5), "MARÍA JOSÉ PEÑA ÑUÑEZ"
            ),
        ),
    ],
)
def test_avisos_recibiste_reconocidos(archivo, esperado):
    assert extraer(leer(archivo)) == esperado
    assert extraer_recibiste(leer(archivo)) == esperado


def test_monto_sin_decimales_se_lee_en_centavos():
    assert extraer_recibiste(recibiste(monto="$160,000")).monto_centavos == 16000000


def test_la_cuenta_no_se_devuelve():
    mov = extraer_recibiste(recibiste(cuenta="**1234"))
    assert mov is not None
    assert "1234" not in repr(mov)


def test_extractores_especificos_no_se_cruzan():
    texto = leer("recibiste_basico.txt")
    assert extraer_compraste(texto) is None
    assert extraer_transferiste(texto) is None
    assert extraer_recibiste(leer("compraste_merpago.txt")) is None
    assert extraer_recibiste(leer("transferiste_basico.txt")) is None


# --- Extractor: variantes válidas --------------------------------------------------

@pytest.mark.parametrize(
    "monto, esperado",
    [
        ("$160,000", 16000000),
        ("$160,000.00", 16000000),
        ("$160,000.50", 16000050),
        ("$500", 50000),
        ("$500.00", 50000),
        ("$1", 100),
        ("$999", 99900),
        ("$1,000", 100000),
        ("$1,234,567", 123456700),
        ("$1,234,567.89", 123456789),
        ("$0.50", 50),  # como en los otros avisos, 50 centavos es válido
    ],
)
def test_montos_validos(monto, esperado):
    assert extraer_recibiste(recibiste(monto=monto)).monto_centavos == esperado


@pytest.mark.parametrize(
    "nombre",
    [
        "PERSONA EJEMPLO",
        "MARÍA JOSÉ PEÑA ÑUÑEZ",
        "O'NEIL-EJEMPLO & CÍA. S.A.S.",
        "X",
        "A" * 100,
        "PERSONA DE LOS EJEMPLOS",        # " de " dentro del nombre
        "PERSONA EN TU CASA",             # "en tu" sin "cuenta *"
        "PAGOS*EJEMPLO",                  # "*" sin dígito detrás
        "persona ejemplo minúsculas",
    ],
)
def test_nombres_validos_se_devuelven_tal_cual(nombre):
    assert extraer_recibiste(recibiste(nombre=nombre)).descripcion == nombre


@pytest.mark.parametrize(
    "hora, esperado",
    [
        ("10:00", (10, 0, 0)),
        ("7:05", (7, 5, 0)),
        ("23:59:59", (23, 59, 59)),
        ("00:00", (0, 0, 0)),
        ("8:05 p. m.", (20, 5, 0)),
        ("12:30 a. m.", (0, 30, 0)),
        ("12:30 p.m.", (12, 30, 0)),
        ("9:15 am", (9, 15, 0)),
    ],
)
def test_horas_24_y_12(hora, esperado):
    mov = extraer_recibiste(recibiste(hora=hora))
    assert (mov.fecha_hora.hour, mov.fecha_hora.minute, mov.fecha_hora.second) == esperado


def test_hora_12h_con_punto_doble_y_sin_texto_adicional():
    assert extraer_recibiste(recibiste(hora="8:05 p. m.", final=".")) is not None
    assert extraer_recibiste(recibiste(hora="8:05 p. m.", final=". Siempre a tu lado.")) is not None
    assert extraer_recibiste(recibiste(hora="8:05 p. m.", final=" Siempre a tu lado.")) is not None


def test_tolerancias_inocuas():
    texto = (
        "  RECIBISTE   UNA TRANSFERENCIA\tpor $160,000 de\nPERSONA   EJEMPLO\n\nEN TU CUENTA **1234,"
        "  el 29/09/2026 A LAS 10:00.  "
    )
    assert extraer_recibiste(texto) == MovimientoExtraido(
        "ingreso", 16000000, datetime(2026, 9, 29, 10, 0), "PERSONA EJEMPLO"
    )


def test_sin_prefijo_y_con_invisibles():
    assert extraer_recibiste(recibiste(prefijo="")) is not None
    texto = recibiste().replace("Recibiste", "Reci​biste").replace("$160", "$­160")
    assert extraer_recibiste(texto).monto_centavos == 16000000


def test_solo_se_toma_el_primer_aviso():
    texto = recibiste(final=". " + recibiste(monto="$999,999", nombre="OTRA PERSONA"))
    assert extraer_recibiste(texto).descripcion == "PERSONA EJEMPLO"
    assert extraer_recibiste(texto).monto_centavos == 16000000


# --- Extractor: casos negativos ----------------------------------------------------

@pytest.mark.parametrize(
    "texto",
    [
        # Monto
        recibiste(monto="$160.000"),          # formato colombiano (punto de miles)
        recibiste(monto="$160.000,00"),       # formato de "Compraste"
        recibiste(monto="$160,000.0"),        # 1 decimal
        recibiste(monto="$160,000.000"),      # 3 decimales
        recibiste(monto="$16,0000"),          # miles mal agrupados
        recibiste(monto="$1600,000"),         # miles mal agrupados
        recibiste(monto="$160000"),           # sin separador de miles (>= 1.000)
        recibiste(monto="$1000"),             # sin separador de miles (>= 1.000)
        recibiste(monto="$0160,000"),         # cero a la izquierda
        recibiste(monto="$0"),                # cero
        recibiste(monto="$0.00"),             # cero
        recibiste(monto="$-160,000"),         # negativo
        recibiste(monto="-$160,000"),         # negativo
        recibiste(monto="160,000"),           # sin signo $
        recibiste(monto="$ 160,000"),         # espacio tras el $
        recibiste(monto="$١٦٠,٠٠٠"),          # dígitos no ASCII (árabe-índicos)
        recibiste(monto="$１６０,０００"),       # dígitos de ancho completo
        recibiste(monto="$160,000."),         # punto sin decimales
        # Fecha
        recibiste(fecha="29/09/26"),          # dd/mm/aa
        recibiste(fecha="31/02/2026"),        # fecha imposible
        recibiste(fecha="29/13/2026"),        # mes imposible
        recibiste(fecha="29/09/1999"),        # año fuera de 2000-2099
        recibiste(fecha="29/09/2100"),        # año fuera de 2000-2099
        recibiste(fecha="29-09-2026"),        # separador distinto
        recibiste(fecha="9/9/2026"),          # sin dos dígitos
        recibiste(fecha="29/09/２０２６"),       # dígitos no ASCII
        # Hora
        recibiste(hora="25:00"),
        recibiste(hora="10:60"),
        recibiste(hora="13:00 p. m."),
        recibiste(hora="0:30 a. m."),
        recibiste(hora="10"),
        # Cuenta
        recibiste(cuenta="*1234"),            # un asterisco
        recibiste(cuenta="***1234"),          # tres asteriscos
        recibiste(cuenta="**123"),            # 3 dígitos
        recibiste(cuenta="**12345"),          # 5 dígitos
        recibiste(cuenta="**12a4"),           # no es número
        recibiste(cuenta="**١٢٣٤"),           # dígitos no ASCII
        recibiste(cuenta="1234"),             # sin asteriscos
        # Nombre
        recibiste(nombre=""),                 # vacío
        recibiste(nombre="A" * 101),          # más de 100 caracteres
        recibiste(nombre="PERSONA *1234"),    # "*" + dígito
        recibiste(nombre="PERSONA 01/02/26"),  # fecha
        recibiste(nombre="Bancolombia: PERSONA"),
        recibiste(nombre="PERSONA COMPRASTE"),
        recibiste(nombre="PERSONA Transferiste"),
        recibiste(nombre="RECIBISTE PERSONA"),
        # Estructura
        recibiste(final=""),                  # sin punto final
        recibiste(final="Si tienes dudas."),  # texto pegado a la hora
    ],
)
def test_variantes_invalidas_no_se_reconocen(texto):
    assert extraer_recibiste(texto) is None
    assert extraer(texto) is None


@pytest.mark.parametrize(
    "texto",
    [
        # Otra redacción de "Recibiste": nunca se adivina.
        "Bancolombia: Recibiste un pago por $160,000 de PERSONA EJEMPLO en tu cuenta **1234, "
        "el 29/09/2026 a las 10:00.",
        "Bancolombia: Recibiste dinero por $160,000 de PERSONA EJEMPLO en tu cuenta **1234, "
        "el 29/09/2026 a las 10:00.",
        "Bancolombia: Recibiste una transferencia de PERSONA EJEMPLO por $160,000 en tu cuenta **1234, "
        "el 29/09/2026 a las 10:00.",                               # orden cambiado
        "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO, "
        "el 29/09/2026 a las 10:00.",                               # sin "en tu cuenta"
        "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO en tu cuenta **1234 "
        "el 29/09/2026 a las 10:00.",                               # sin coma antes de "el"
        "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO en tu cuenta de ahorros "
        "**1234, el 29/09/2026 a las 10:00.",                       # texto extra antes de la cuenta
        "Bancolombia: Recibiste transferencia por $160,000 de PERSONA EJEMPLO en tu cuenta **1234, "
        "el 29/09/2026 a las 10:00.",                               # sin "una"
        "Bancolombia: Recibiste una transferencia por $160,000 en tu cuenta **1234, "
        "el 29/09/2026 a las 10:00.",                               # sin quien envía
        "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO en tu cuenta **1234, "
        "el 29/09/2026.",                                           # sin hora
        "¿Recibiste una transferencia por $160,000 de PERSONA EJEMPLO en tu cuenta **1234, "
        "el 29/09/2026 a las 10:00.",                               # no está al inicio
        # El fixture que existía antes del ítem 09: otra redacción, sigue sin reconocerse.
        leer("no_reconocido_recibiste.txt"),
    ],
    ids=["pago", "dinero", "orden_cambiado", "sin_en_tu_cuenta", "sin_coma", "cuenta_de_ahorros",
         "sin_una", "sin_nombre", "sin_hora", "no_al_inicio", "fixture_recibiste_un_pago"],
)
def test_recibiste_con_otro_texto_sigue_no_reconocido(texto):
    assert extraer(texto) is None


@pytest.mark.parametrize(
    "texto",
    [
        # Caso del tester (ronda 1): fecha y hora propias deformadas; sin la
        # guarda, el nombre llegaba hasta la cuenta y la fecha del texto adicional.
        "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO, 29-09-2026 10:00. "
        "Recuerda: en tu cuenta **9999, el 30/09/2026 a las 11:00.",
        # Variantes: fecha con "." o "/" de otro largo, solo la hora, ", el " y " a las ".
        "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO, 29.09.2026. "
        "Recuerda: en tu cuenta **9999, el 30/09/2026 a las 11:00.",
        "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO, 1/9/26. "
        "Recuerda: en tu cuenta **9999, el 30/09/2026 a las 11:00.",
        "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO a las 10:00. "
        "Recuerda: en tu cuenta **9999, el 30/09/2026 a las 11:00.",
        "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO hoy 10:00. "
        "Recuerda: en tu cuenta **9999, el 30/09/2026 a las 11:00.",
        "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO, el 29 de septiembre. "
        "Recuerda: en tu cuenta **9999, el 30/09/2026 a las 11:00.",
        "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO a las 9 de la mañana. "
        "Recuerda: en tu cuenta **9999, el 30/09/2026 a las 11:00.",
    ],
    ids=["tester_fecha_con_guiones", "fecha_con_puntos", "fecha_corta_con_barras", "a_las_hora",
         "solo_hora", "coma_el_digito", "a_las_digito"],
)
def test_el_nombre_no_cruza_fecha_ni_hora_deformadas(texto):
    assert extraer_recibiste(texto) is None
    assert extraer(texto) is None
    assert extraer_aviso(texto) is None


@pytest.mark.parametrize(
    "nombre",
    ["PERSONA 1-2-2026", "PERSONA 01.02.26", "TIENDA 24:00", "PERSONA, el 2", "PERSONA a las 3"],
)
def test_nombres_con_fecha_u_hora_no_se_reconocen(nombre):
    """Consecuencia aceptada de la guarda: se prefiere no reconocer."""
    assert extraer_recibiste(recibiste(nombre=nombre)) is None


@pytest.mark.parametrize(
    "nombre",
    ["PERSONA 12/34", "PERSONA 1234", "EMPRESA 2026 LTDA", "J. P. EJEMPLO", "EMPRESA EJEMPLO S.A.S.",
     "PERSONA, ELENA EJEMPLO", "PERSONA A LAS PALMAS", "PERSONA 1.5", "PERSONA 10 30", "TIENDA 24:7"],
)
def test_nombres_legitimos_con_numeros_y_puntos_siguen_valiendo(nombre):
    assert extraer_recibiste(recibiste(nombre=nombre)).descripcion == nombre


def test_el_nombre_no_cruza_hasta_un_segundo_aviso():
    """Si el primer aviso viene deformado (cuenta con un asterisco), el nombre
    no puede extenderse hasta la cuenta ni la fecha de una repetición válida
    en el texto adicional."""
    deformado = recibiste(cuenta="*1234", final=". ")
    assert extraer_recibiste(deformado + recibiste()) is None
    assert extraer_recibiste(recibiste(cuenta="*1234", final=". en tu cuenta **1234, el 29/09/2026 a las 10:00.")) is None


# --- Sincronización ----------------------------------------------------------------

@pytest.fixture
def ruta_db(tmp_path):
    return str(tmp_path / "recibiste.db")


@pytest.fixture
def conn(ruta_db):
    conexion = db.conectar(ruta_db)
    db.inicializar(conexion)
    yield conexion
    conexion.close()


class Cliente:
    def __init__(self, correos):
        self.correos = {c.gmail_id: c for c in correos}
        self.llamadas_obtener = []

    def listar_ids(self, desde):
        return list(self.correos)

    def obtener(self, gmail_id):
        self.llamadas_obtener.append(gmail_id)
        return self.correos[gmail_id]


def _correo_fixture() -> CorreoGmail:
    return correo_desde_mensaje(json.loads((GMAIL / "recibiste_html.json").read_text(encoding="utf-8")))


def _correo(gmail_id="rec-1", texto=None, **encabezados) -> CorreoGmail:
    datos = {**LEGITIMO, **encabezados}
    return CorreoGmail(
        gmail_id,
        datetime(2026, 9, 29, 10, 1, tzinfo=ZONA_COLOMBIA),
        "Alerta (ejemplo)",
        texto if texto is not None else recibiste(),
        **datos,
    )


def _configurar(conn, saldo_inicial=100000000, fecha_inicio=date(2026, 9, 1)):
    componer_saldo(conn).configurar(saldo_inicial, fecha_inicio)


def _movimientos(conn):
    return [dict(f) for f in sql(
        conn,
        "SELECT fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, gmail_id "
        "FROM movimientos ORDER BY id"
    )]


def test_extraer_aviso_acepta_recibiste_con_prefijo():
    texto = "¡Listo! Todo salió bien con tus movimientos\n\n" + recibiste() + "\n\nOtro texto."
    assert extraer_aviso(texto) == MovimientoExtraido(
        "ingreso", 16000000, datetime(2026, 9, 29, 10, 0), "PERSONA EJEMPLO"
    )


def test_extraer_aviso_exige_el_prefijo():
    """Como con los otros avisos (decisión del dueño, ronda 3): sin
    "Bancolombia:" queda como no reconocido."""
    assert extraer_aviso(recibiste(prefijo="")) is None
    assert extraer_aviso("Encabezado. " + recibiste(prefijo="")) is None


def test_extraer_aviso_prefijo_pegado_a_la_palabra_anterior():
    """Igual que con "Compraste": "Bancolombia:" puede venir pegado al texto
    anterior (HTML convertido), pero el extractor exige el espacio tras los
    dos puntos."""
    # ítem 21: antes se reconocía; ahora queda no reconocido porque "Alertas"
    # no es un encabezado de plantilla conocido (el aviso estaría citado).
    assert extraer_aviso("Alertas" + recibiste(prefijo="Bancolombia: ")) is None
    assert extraer_aviso("Alertas" + recibiste(prefijo="Bancolombia:")) is None


def test_extraer_aviso_no_cruza_a_otro_aviso():
    """Un "Recibiste" deformado seguido de un aviso válido: se reconoce el
    segundo, nunca un nombre que contenga el primero."""
    texto = recibiste(cuenta="*1234", monto="$999,999", nombre="FALSO") + " " + recibiste()
    # ítem 21: antes se reconocía el segundo aviso; ahora queda no reconocido
    # porque ya no se busca una segunda posición: el segundo aviso tiene
    # delante otro texto (el primero) y se trata como citado.
    assert extraer_aviso(texto) is None


def test_correo_legitimo_crea_un_ingreso_de_gmail(conn):
    _configurar(conn)
    resultado = sincronizar(conn, Cliente([_correo_fixture()]))

    assert resultado == ResultadoSincronizacion(nuevos=1)
    assert _movimientos(conn) == [{
        "fecha_hora": "2026-09-29T10:00:00",
        "monto_centavos": 16000000,
        "tipo": "ingreso",
        "descripcion": "PERSONA EJEMPLO",
        "categoria_id": None,
        "origen": "gmail",
        "gmail_id": "msg-recibiste-0001",
    }]


def test_sincronizar_dos_veces_no_duplica(conn):
    _configurar(conn)
    sincronizar(conn, Cliente([_correo_fixture()]))

    segundo = Cliente([_correo_fixture()])
    assert sincronizar(conn, segundo) == ResultadoSincronizacion()
    assert segundo.llamadas_obtener == []
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 1


def test_el_saldo_suma_el_ingreso(conn):
    _configurar(conn, saldo_inicial=100000000)
    compra = _correo(
        "compra-1",
        "Bancolombia: Compraste $68.630,00 en MERPAGO*TIENDA con tu T.Deb *1234, "
        "el 29/09/2026 a las 09:00.",
    )
    sincronizar(conn, Cliente([_correo_fixture(), compra]))

    assert componer_saldo(conn).saldo_actual() == 100000000 + 16000000 - 6863000


def test_el_ingreso_no_cuenta_como_gasto_y_queda_pendiente_con_su_monto_aparte(conn):
    _configurar(conn)
    sincronizar(conn, Cliente([_correo_fixture()]))

    assert componer_saldo(conn).gasto_entre(datetime(2026, 9, 1), datetime(2026, 10, 1)) == 0
    # Ítem 15: un ingreso sin categoría es pendiente, pero su monto va aparte.
    assert [m["tipo"] for m in categorizacion.sin_categorizar(conn)] == ["ingreso"]
    assert categorizacion.contar_sin_categorizar(conn) == 1
    assert categorizacion.resumen_sin_categorizar(conn) == categorizacion.ResumenPendientes(
        cuantos=1, gastos_centavos=0, ingresos_centavos=16000000
    )


def test_las_reglas_de_gasto_no_se_aplican_a_ingresos(conn):
    assert categorizacion.campo_para_tipo("ingreso") == "quien_envia"
    _configurar(conn)
    categoria_id = sql(conn, "SELECT id FROM categorias ORDER BY id LIMIT 1").fetchone()[0]
    with db.transaccion(conn):
        for campo in ("comercio", "cuenta_destino"):
            sql(
                conn,
                "INSERT INTO reglas (campo, texto, categoria_id) VALUES (?, ?, ?)",
                (campo, categorizacion.normalizar("PERSONA EJEMPLO"), categoria_id),
            )
    sincronizar(conn, Cliente([_correo_fixture()]))

    assert _movimientos(conn)[0]["categoria_id"] is None


@pytest.mark.parametrize(
    "encabezados",
    [
        {"remitente": "alertasynotificaciones@an.notificacionesbancolombia.co"},
        {"remitente": "alertas@ejemplo-falso.com"},
        {"remitente": ""},
        {"autenticacion": ""},
        {"autenticacion": AUTENTICACION_LEGITIMA.replace("dkim=pass", "dkim=fail")
                                                  .replace("dmarc=pass", "dmarc=fail")},
        {"autenticacion": "mx.ejemplo-falso.com; dkim=pass header.i=@notificacionesbancolombia.com; "
                          "dmarc=pass header.from=notificacionesbancolombia.com"},
    ],
    ids=["dominio_parecido", "remitente_falso", "sin_remitente", "sin_autenticacion",
         "dkim_y_dmarc_fallan", "autenticacion_no_es_de_gmail"],
)
def test_recibiste_falso_no_crea_ingreso(conn, encabezados):
    _configurar(conn)
    correo = _correo(**encabezados)
    assert extraer_aviso(correo.texto) is not None  # el cuerpo sí es un aviso válido

    resultado = sincronizar(conn, Cliente([correo]))

    assert resultado == ResultadoSincronizacion(rechazados_autenticacion=1)
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 0
    assert componer_saldo(conn).saldo_actual() == 100000000


def test_fixture_de_gmail_usa_los_encabezados_legitimos():
    correo = _correo_fixture()
    assert correo.remitente == REMITENTE_OFICIAL
    assert correo.autenticacion == AUTENTICACION_LEGITIMA


def test_recibiste_con_otro_texto_por_gmail_queda_no_reconocido(conn):
    _configurar(conn)
    texto = recibiste().replace("Recibiste una transferencia por", "Recibiste un pago por")
    resultado = sincronizar(conn, Cliente([_correo(texto=texto)]))

    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 0


def test_logs_no_incluyen_nombre_monto_ni_cuenta(conn, caplog):
    _configurar(conn)
    correos = [
        _correo_fixture(),
        _correo("rec-2", recibiste(nombre="MARÍA JOSÉ PEÑA ÑUÑEZ", monto="$777,777.77")),
        _correo("rec-3", recibiste(nombre="NOMBRE FALSIFICADO"), remitente="alertas@ejemplo-falso.com"),
        _correo("rec-4", recibiste(nombre="NOMBRE SIN FORMATO", cuenta="*1234")),
    ]
    with caplog.at_level(logging.DEBUG):
        resultado = sincronizar(conn, Cliente(correos))

    assert resultado == ResultadoSincronizacion(nuevos=2, no_reconocidos=1, rechazados_autenticacion=1)
    texto = caplog.text
    assert "rec-2" in texto  # los ids sí
    for prohibido in (
        "PERSONA EJEMPLO", "MARÍA", "PEÑA", "ÑUÑEZ", "NOMBRE FALSIFICADO", "NOMBRE SIN FORMATO",
        "160,000", "16000000", "777,777", "77777777", "**1234", "*1234", "Recibiste", "Bancolombia:",
    ):
        assert prohibido not in texto, prohibido


def test_ingreso_de_gmail_y_manual_conviven(conn):
    """Un ingreso manual no choca con el de Gmail (gmail_id NULL vs. id)."""
    _configurar(conn)
    sincronizar(conn, Cliente([_correo_fixture()]))
    componer_saldo(conn).registrar_ingreso(5000000, datetime(2026, 9, 2, 8, 0), "Efectivo (ejemplo)")

    assert componer_saldo(conn).saldo_actual() == 100000000 + 16000000 + 5000000
    origenes = sorted(f["origen"] for f in _movimientos(conn))
    assert origenes == ["gmail", "manual"]


def test_ingreso_anterior_a_la_fecha_de_inicio_se_descarta(conn):
    _configurar(conn, fecha_inicio=date(2026, 9, 1))
    correo = replace(_correo(), fecha=datetime(2026, 8, 31, 23, 59, tzinfo=ZONA_COLOMBIA))
    assert sincronizar(conn, Cliente([correo])) == ResultadoSincronizacion()
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 0
