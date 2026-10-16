"""Casos borde del aviso "Recibiste una transferencia" (ingresos, D12 / ítem 09).

Complementa ``tests/modulos/sincronizacion/test_recibiste.py``. Todo es inventado: nombres
(PERSONA EJEMPLO, INVERSIONES EJEMPLO & CÍA. S.A.S....), cuentas (**1234,
**4321, **5678, **9999) y teléfonos (018000000000).
"""

from __future__ import annotations
from finanzas.bootstrap.saldo import componer_saldo

import base64
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from finanzas import categorizacion, db
from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import MovimientoExtraido, extraer, extraer_recibiste
from finanzas.gmail import ZONA_COLOMBIA, CorreoGmail, correo_desde_mensaje
from finanzas.sincronizacion import ResultadoSincronizacion, extraer_aviso, sincronizar
from tests.soporte.gmail_falso import ENCABEZADOS_LEGITIMOS, LEGITIMO
from tests.soporte.ayudas_db import sql

GMAIL = Path(__file__).resolve().parents[2] / "fixtures" / "gmail"
FINAL = ". Si tienes dudas, hablemos: 018000000000. Siempre a tu lado."


def recibiste(
    monto="$160,000",
    nombre="PERSONA EJEMPLO",
    cuenta="**1234",
    fecha="29/09/2026",
    hora="10:00",
    final=FINAL,
    prefijo="Bancolombia: ",
):
    return (
        f"{prefijo}Recibiste una transferencia por {monto} de {nombre} en tu cuenta {cuenta}, "
        f"el {fecha} a las {hora}{final}"
    )


def _cargar(ruta: Path) -> CorreoGmail:
    return correo_desde_mensaje(json.loads(ruta.read_text(encoding="utf-8")))


def _mensaje_html(gmail_id: str, html: str) -> dict:
    datos = base64.urlsafe_b64encode(html.encode("utf-8")).decode("ascii").rstrip("=")
    return {
        "id": gmail_id,
        "threadId": "hilo-" + gmail_id,
        "internalDate": "1790694030000",
        "payload": {
            "mimeType": "text/html",
            "headers": [*ENCABEZADOS_LEGITIMOS, {"name": "Content-Type", "value": "text/html; charset=utf-8"}],
            "body": {"data": datos},
        },
    }


# --- HTML real -------------------------------------------------------------------

def test_fixture_html_con_br_nbsp_y_prefijo_en_celda_aparte():
    """<br>, &nbsp;, &amp; y "Bancolombia:" en su propia <td>."""
    correo = _cargar(GMAIL / "recibiste_html_celdas.json")
    assert extraer_aviso(correo.texto) == MovimientoExtraido(
        "ingreso", 125000000, datetime(2026, 9, 15, 7, 45), "INVERSIONES EJEMPLO & CÍA. S.A.S."
    )


@pytest.mark.parametrize(
    "html",
    [
        # "Bancolombia:" en un <p> y el aviso en otro.
        "<p><b>Bancolombia:</b></p><p>Recibiste una transferencia por $160,000 de PERSONA EJEMPLO "
        "en tu cuenta **1234, el 29/09/2026 a las 10:00. Siempre a tu lado.</p>",
        # Todos los espacios como &nbsp; y saltos <br> en medio del nombre.
        "<td>Bancolombia:&nbsp;Recibiste&nbsp;una&nbsp;transferencia&nbsp;por&nbsp;$160,000&nbsp;de"
        "&nbsp;PERSONA<br>EJEMPLO&nbsp;en&nbsp;tu&nbsp;cuenta&nbsp;**1234,&nbsp;el&nbsp;29/09/2026"
        "&nbsp;a&nbsp;las&nbsp;10:00.</td>",
        # Entidades numéricas en el monto y el asterisco.
        "<p>Bancolombia: Recibiste una transferencia por &#36;160&#44;000 de PERSONA EJEMPLO en tu "
        "cuenta &#42;&#42;1234, el 29/09/2026 a las 10:00.</p>",
    ],
    ids=["prefijo_en_parrafo_aparte", "nbsp_y_br", "entidades_numericas"],
)
def test_html_partido_se_reconoce(html):
    correo = correo_desde_mensaje(_mensaje_html("html-1", html))
    mov = extraer_aviso(correo.texto)
    assert mov == MovimientoExtraido("ingreso", 16000000, datetime(2026, 9, 29, 10, 0), "PERSONA EJEMPLO")


def test_html_prefijo_pegado_a_span_tras_texto_desconocido_no_se_reconoce():
    """Antes era el caso "prefijo_pegado_a_span" de ``test_html_partido_se_reconoce``."""
    html = (
        "<div>Alertas<span>Bancolombia:</span> Recibiste una transferencia por $160,000.00 de "
        "PERSONA EJEMPLO en tu cuenta **1234, el 29/09/2026 a las 10:00.</div>"
    )
    # ítem 21: antes se reconocía; ahora queda no reconocido porque "Alertas"
    # no es un encabezado de plantilla conocido (el aviso estaría citado).
    assert extraer_aviso(correo_desde_mensaje(_mensaje_html("html-1", html)).texto) is None


def test_html_prefijo_pegado_a_span_tras_el_encabezado_conocido_se_reconoce():
    html = (
        "<div>¡Listo! Todo salió bien con tus movimientos<span>Bancolombia:</span> Recibiste una "
        "transferencia por $160,000.00 de PERSONA EJEMPLO en tu cuenta **1234, el 29/09/2026 a las "
        "10:00.</div>"
    )
    mov = extraer_aviso(correo_desde_mensaje(_mensaje_html("html-1", html)).texto)
    assert mov == MovimientoExtraido("ingreso", 16000000, datetime(2026, 9, 29, 10, 0), "PERSONA EJEMPLO")


def test_html_con_prefijo_en_celda_y_otra_celda_en_medio_no_se_reconoce():
    """Si entre "Bancolombia:" y "Recibiste" hay otro texto (otra celda), no
    hay inicio de aviso válido: queda como no reconocido."""
    html = (
        "<table><tr><td>Bancolombia:</td><td>Hola, PERSONA</td>"
        "<td>Recibiste una transferencia por $160,000 de PERSONA EJEMPLO en tu cuenta **1234, "
        "el 29/09/2026 a las 10:00.</td></tr></table>"
    )
    assert extraer_aviso(correo_desde_mensaje(_mensaje_html("html-2", html)).texto) is None


# --- Nombres ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "nombre",
    [
        "INVERSIONES 123 EJEMPLO",               # números
        "EMPRESA 2026 LTDA",
        "J. P. EJEMPLO",                          # puntos
        "COMERCIALIZADORA EJEMPLO S.A.S.",        # S.A.S. al final (punto antes de " en tu")
        '"LA TIENDITA" EJEMPLO',                  # comillas dobles
        "“PERSONA” EJEMPLO",                      # comillas tipográficas
        "PERSONA & PERSONA EJEMPLO",              # &
        "PERSONA EJEMPLO 😀",                     # emoji
        "😀" * 100,                               # 100 caracteres justos (emoji = 1 carácter)
        "B" * 99 + ".",                           # 100 justos terminando en punto
        "FONDO DE EMPLEADOS DE EJEMPLO",          # " de " varias veces
        "DE LA CRUZ EJEMPLO",                     # empieza por "DE"
        "PERSONA DE",                             # termina en "DE"
        "PAGOS EN TU CASA EJEMPLO",               # "en tu" sin "cuenta *"
        "NOMINA EN TU CUENTA EJEMPLO",            # "en tu cuenta" sin "*" detrás
        "PERSONA POR EJEMPLO",                    # " por " dentro del nombre
        "PERSONA, EJEMPLO",                       # coma
        "PERSONA 1234",                           # dígitos sin "*" delante
        "PERSONA 12/34",                          # parece fecha pero no dd/mm/aa
    ],
)
def test_nombres_raros_se_devuelven_tal_cual(nombre):
    mov = extraer_recibiste(recibiste(nombre=nombre))
    assert mov is not None, nombre
    assert mov.descripcion == nombre
    assert mov.monto_centavos == 16000000


@pytest.mark.parametrize(
    "nombre",
    [
        "😀" * 101,                  # 101 caracteres
        "PERSONA **9999",            # cuenta dentro del nombre
        "PERSONA 29/09/2026",        # fecha dentro del nombre
        "PERSONA en tu cuenta *5",   # " en tu cuenta *" dentro del nombre
        "RECIBISTEMOS EJEMPLO",      # la guarda no usa límites de palabra (consecuencia aceptada)
        "PERSONA bancolombia: X",
    ],
)
def test_nombres_bloqueados_por_la_guarda(nombre):
    assert extraer_recibiste(recibiste(nombre=nombre)) is None
    assert extraer_aviso(recibiste(nombre=nombre)) is None


def test_nombre_con_zwj_pierde_el_invisible():
    """Documenta: los invisibles (categoría Cf, como el ZWJ de los emojis
    compuestos) se eliminan antes de extraer, así que la descripción guarda
    el emoji compuesto separado. Nunca se inventa texto."""
    familia = "\U0001F468‍\U0001F469‍\U0001F467"
    mov = extraer_recibiste(recibiste(nombre=f"PERSONA {familia}"))
    assert mov.descripcion == "PERSONA \U0001F468\U0001F469\U0001F467"


def test_nombre_con_saltos_de_linea_se_normaliza():
    mov = extraer_recibiste(recibiste(nombre="PERSONA\n\n  EJEMPLO\t S.A.S."))
    assert mov.descripcion == "PERSONA EJEMPLO S.A.S."


# --- Nombre que se come el resto ---------------------------------------------------

@pytest.mark.parametrize(
    "texto",
    [
        # Aviso válido seguido de texto que repite un final válido con otra cuenta.
        recibiste(final=". Tambien en tu cuenta **9999, el 30/09/2026 a las 11:00."),
        # ...con otra fecha y hora.
        recibiste(final=". Si no eres tu en tu cuenta **1234, el 01/10/2026 a las 23:00."),
        # ...con otro monto en el texto adicional.
        recibiste(final=". Otro de $999,999 en tu cuenta **5678, el 29/09/2026 a las 10:00."),
        # Un segundo aviso completo detrás.
        recibiste(final=". " + recibiste(monto="$999,999.99", nombre="OTRA PERSONA", cuenta="**9999")),
    ],
    ids=["otra_cuenta", "otra_fecha", "otro_monto", "segundo_aviso"],
)
def test_texto_adicional_no_cambia_el_primer_aviso(texto):
    esperado = MovimientoExtraido("ingreso", 16000000, datetime(2026, 9, 29, 10, 0), "PERSONA EJEMPLO")
    assert extraer_recibiste(texto) == esperado
    assert extraer_aviso(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        # Primer aviso con cuenta deformada; repetición válida detrás.
        recibiste(cuenta="*1234", final=". Dudas en tu cuenta **9999, el 30/09/2026 a las 11:00."),
        recibiste(cuenta="**12345", final=". en tu cuenta **9999, el 30/09/2026 a las 11:00."),
        # Primer aviso sin cuenta ni coma; repetición válida detrás.
        "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO el 29/09/2026 a las "
        "10:00. Info en tu cuenta **9999, el 30/09/2026 a las 11:00.",
        # Primer aviso con fecha dd/mm/aa; repetición con fecha larga detrás.
        recibiste(fecha="29/09/26", final=". Info de X en tu cuenta **9999, el 30/09/2026 a las 11:00."),
        # Nombre de más de 100 caracteres hasta el primer final válido.
        "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO sin cuenta. "
        + "texto de relleno " * 6 + "en tu cuenta **9999, el 30/09/2026 a las 11:00.",
    ],
    ids=["un_asterisco", "cinco_digitos", "sin_cuenta", "fecha_corta", "relleno_largo"],
)
def test_aviso_deformado_no_se_completa_con_texto_adicional(texto):
    assert extraer_recibiste(texto) is None
    assert extraer_aviso(texto) is None


# --- Correos que citan el aviso ---------------------------------------------------

@pytest.mark.parametrize(
    "texto",
    [
        "Bancolombia: Reversamos: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO en tu "
        "cuenta **1234, el 29/09/2026 a las 10:00.",
        "Reversamos: " + recibiste(prefijo=""),
        "Bancolombia: Rechazamos la transferencia. Recibiste una transferencia por $160,000 de PERSONA "
        "EJEMPLO en tu cuenta **1234, el 29/09/2026 a las 10:00.",
        "Bancolombia: No recibiste una transferencia por $160,000 de PERSONA EJEMPLO en tu cuenta **1234, "
        "el 29/09/2026 a las 10:00.",
        "¿Reconoces este movimiento? Recibiste una transferencia por $160,000 de PERSONA EJEMPLO en tu "
        "cuenta **1234, el 29/09/2026 a las 10:00.",
        "Si no recibiste una transferencia por $160,000 de PERSONA EJEMPLO en tu cuenta **1234, el "
        "29/09/2026 a las 10:00, llámanos.",
        "Bancolombia: Recibiste una transferencia rechazada por $160,000 de PERSONA EJEMPLO en tu cuenta "
        "**1234, el 29/09/2026 a las 10:00.",
        "Bancolombia: Recibiste una devolución por $160,000 de PERSONA EJEMPLO en tu cuenta **1234, el "
        "29/09/2026 a las 10:00.",
        "Bancolombia: Recibiste una transferencia programada por $160,000 de PERSONA EJEMPLO en tu cuenta "
        "**1234, el 29/09/2026 a las 10:00.",
        "Bancolombia: Enviaste una transferencia por $160,000 a PERSONA EJEMPLO desde tu cuenta **1234, "
        "el 29/09/2026 a las 10:00.",
        "Bancolombia: RecibisteUna transferencia por $160,000 de PERSONA EJEMPLO en tu cuenta **1234, el "
        "29/09/2026 a las 10:00.",
        # Promoción que contiene la palabra pero no el aviso.
        "Bancolombia: Recibiste una transferencia? Gana puntos. Aplican condiciones.",
    ],
    ids=["reversamos_tras_prefijo", "reversamos_sin_prefijo", "rechazo", "no_recibiste",
         "reconoces_movimiento", "si_no_recibiste", "transferencia_rechazada", "devolucion",
         "programada", "enviaste", "palabras_pegadas", "promocion"],
)
def test_correos_que_citan_el_aviso_no_crean_ingreso(texto):
    assert extraer_aviso(texto) is None


def test_aviso_citado_con_prefijo_completo_no_crea_ingreso():
    """Un correo (reverso, educativo...) que cita el aviso completo CON su
    prefijo. Antes era el riesgo conocido
    ``test_riesgo_conocido_aviso_citado_con_prefijo_completo_se_reconoce``."""
    texto = "Reversamos la siguiente transacción. " + recibiste()
    # ítem 21: antes se reconocía (riesgo conocido); ahora queda no reconocido
    # porque "Reversamos la siguiente transacción." no es un encabezado conocido.
    assert extraer_aviso(texto) is None


# --- Ingreso de Gmail y saldo ------------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "recibiste_bordes.db"))
    db.inicializar(conexion)
    componer_saldo(conexion).configurar(100000000, date(2026, 9, 1))
    yield conexion
    conexion.close()


class Cliente:
    def __init__(self, correos):
        self.correos = {c.gmail_id: c for c in correos}

    def listar_ids(self, desde):
        return list(self.correos)

    def obtener(self, gmail_id):
        return self.correos[gmail_id]


def _correo(gmail_id, texto, fecha=datetime(2026, 9, 15, 9, 0, tzinfo=ZONA_COLOMBIA)):
    return CorreoGmail(gmail_id, fecha, "Alerta (ejemplo)", texto, **LEGITIMO)


def _filas(conn):
    return [dict(f) for f in sql(
        conn,
        "SELECT tipo, monto_centavos, descripcion, origen, gmail_id, categoria_id FROM movimientos ORDER BY id"
    )]


def test_ingreso_de_gmail_y_manual_el_mismo_dia_no_se_deduplican(conn):
    """Documenta (D12): un ingreso de Gmail y uno manual con el mismo monto y
    el mismo día NO se deduplican; los dos suman al saldo. Es lo esperado: los
    manuales son para dinero sin aviso, y registrar a mano un "Recibiste" lo
    cuenta dos veces (lo advierte ``registrar_ingreso``)."""
    sincronizar(conn, Cliente([_correo("rec-1", recibiste(fecha="15/09/2026", hora="08:00"))]))
    componer_saldo(conn).registrar_ingreso(16000000, datetime(2026, 9, 15, 8, 0), "PERSONA EJEMPLO")

    filas = _filas(conn)
    assert [(f["tipo"], f["origen"], f["monto_centavos"]) for f in filas] == [
        ("ingreso", "gmail", 16000000),
        ("ingreso", "manual", 16000000),
    ]
    assert componer_saldo(conn).saldo_actual() == 100000000 + 2 * 16000000


def test_ajuste_despues_de_un_recibiste(conn):
    sincronizar(conn, Cliente([_correo("rec-1", recibiste(fecha="15/09/2026"))]))
    assert componer_saldo(conn).saldo_actual() == 116000000

    # En el banco hay $15.000,00 menos (cuota de manejo inventada): ajuste negativo.
    diferencia = componer_saldo(conn).ajustar_saldo(116000000 - 1500000)
    assert diferencia == -1500000
    assert componer_saldo(conn).saldo_actual() == 114500000
    # Ni el ingreso ni el ajuste son gasto.
    assert componer_saldo(conn).gasto_entre(datetime(2026, 9, 1), datetime(2026, 10, 1)) == 0

    # Un ajuste que ya coincide no se guarda.
    assert componer_saldo(conn).ajustar_saldo(114500000) == 0
    assert [f["tipo"] for f in _filas(conn)] == ["ingreso", "ajuste"]


def test_ajuste_antes_y_recibiste_despues_sigue_sumando(conn):
    assert componer_saldo(conn).ajustar_saldo(90000000) == -10000000
    sincronizar(conn, Cliente([_correo("rec-1", recibiste(fecha="15/09/2026"))]))
    assert componer_saldo(conn).saldo_actual() == 90000000 + 16000000


# --- Transacciones mezcladas --------------------------------------------------------

def test_compraste_transferiste_y_recibiste_en_la_misma_sincronizacion(conn):
    correos = [
        # ítem 21: el encabezado era "¡Listo!" a secas, que no es el de la
        # plantilla real; con él quedaría no reconocido. Se usa el completo.
        _correo("mix-compra", "¡Listo! Todo salió bien con tus movimientos\n\nBancolombia: Compraste $68.630,00 en MERPAGO*TIENDA con tu T.Deb "
                              "*1234, el 15/09/2026 a las 09:00. Si tienes dudas, encuentranos aqui."),
        _correo("mix-transf", "Bancolombia: Transferiste $4,500.00 desde tu cuenta *1234 a la cuenta "
                              "*3000000000 el 15/09/26 a las 19:05. ¿Dudas? Llamanos."),
        _correo("mix-rec-1", recibiste(fecha="15/09/2026")),
        _correo("mix-rec-2", recibiste(monto="$1,000.50", nombre="EMPRESA EJEMPLO S.A.S.",
                                       fecha="16/09/2026", hora="8:00 p. m.")),
        _correo("mix-rec-malo", recibiste(cuenta="*1234")),
    ]
    resultado = sincronizar(conn, Cliente(correos))
    assert resultado == ResultadoSincronizacion(nuevos=4, no_reconocidos=1)

    filas = {f["gmail_id"]: f for f in _filas(conn)}
    assert filas["mix-compra"]["tipo"] == "compra"
    assert filas["mix-transf"]["tipo"] == "transferencia"
    assert (filas["mix-rec-1"]["tipo"], filas["mix-rec-1"]["monto_centavos"]) == ("ingreso", 16000000)
    assert (filas["mix-rec-2"]["descripcion"], filas["mix-rec-2"]["monto_centavos"]) == (
        "EMPRESA EJEMPLO S.A.S.", 100050
    )
    assert all(f["origen"] == "gmail" for f in filas.values())

    assert componer_saldo(conn).saldo_actual() == 100000000 - 6863000 - 450000 + 16000000 + 100050
    assert componer_saldo(conn).gasto_entre(datetime(2026, 9, 1), datetime(2026, 10, 1)) == 6863000 + 450000
    # Todos quedan en la bandeja (los ingresos también, ítem 15).
    pendientes = [m["tipo"] for m in categorizacion.sin_categorizar(conn)]
    assert sorted(pendientes) == ["compra", "ingreso", "ingreso", "transferencia"]

    # Segunda sincronización: nada nuevo.
    assert sincronizar(conn, Cliente(correos)) == ResultadoSincronizacion()
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 4


# --- Autenticación con encabezados reales anonimizados -----------------------------

def test_recibiste_con_authentication_results_real_anonimizado(conn):
    correo = _cargar(GMAIL / "autenticacion" / "legitimo_recibiste_real_anonimizado.json")
    assert sincronizar(conn, Cliente([correo])) == ResultadoSincronizacion(nuevos=1)
    assert _filas(conn) == [{
        "tipo": "ingreso",
        "monto_centavos": 16000000,
        "descripcion": "PERSONA EJEMPLO",
        "origen": "gmail",
        "gmail_id": "real-recibiste-0001",
        "categoria_id": None,
    }]


@pytest.mark.parametrize(
    "cambio",
    [
        ("dmarc=pass", "dmarc=fail"),
        ("mx.google.com;", "mx.ejemplo-falso.com;"),
        ("header.from=notificacionesbancolombia.com", "header.from=notificacionesbancolombia.co"),
    ],
    ids=["dmarc_falla", "no_es_de_gmail", "dominio_parecido"],
)
def test_recibiste_real_anonimizado_alterado_se_rechaza(conn, cambio):
    mensaje = json.loads(
        (GMAIL / "autenticacion" / "legitimo_recibiste_real_anonimizado.json").read_text(encoding="utf-8")
    )
    for encabezado in mensaje["payload"]["headers"]:
        if encabezado["name"] == "Authentication-Results":
            encabezado["value"] = encabezado["value"].replace(*cambio)
    correo = correo_desde_mensaje(mensaje)
    assert extraer(correo.texto) is None  # el aviso no está al inicio: lo localiza la sincronización
    assert extraer_aviso(correo.texto) is not None

    assert sincronizar(conn, Cliente([correo])) == ResultadoSincronizacion(rechazados_autenticacion=1)
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 0
