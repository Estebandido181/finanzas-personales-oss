"""Casos borde del aviso "transferiste ... a la llave" (Bre-B) a través de la
sincronización completa (Gmail falso, sin red).

Todo es inventado: nombres (PERSONA EJEMPLO, NOMBRE DESTINO EJEMPLO), llaves
(3000000000), cuentas (*1234) y teléfonos (018000000000).
"""

from __future__ import annotations
from finanzas.bootstrap.saldo import componer_saldo

import base64
import time
from datetime import date, datetime
from pathlib import Path

import pytest

from finanzas import db
from finanzas.modulos.sincronizacion.adaptadores.avisos import extractor
from finanzas.gmail import ZONA_COLOMBIA, CorreoGmail, correo_desde_mensaje, html_a_texto
from finanzas.sincronizacion import ResultadoSincronizacion, extraer_aviso, sincronizar
from tests.soporte.ayudas_db import sql
from tests.soporte.gmail_falso import ENCABEZADOS_LEGITIMOS, LEGITIMO, ClienteFalso

AVISOS = Path(__file__).resolve().parents[2] / "fixtures" / "avisos"

# Cuerpo del aviso nuevo sin el prefijo "Bancolombia: ".
CUERPO = (
    "PERSONA EJEMPLO, transferiste $6,200.00 a la llave 3000000000 desde tu cuenta *1234 "
    "a NOMBRE DESTINO EJEMPLO el 29/09/26 a las 21:28. Con Bre-b es de una y gratis. "
    "Dudas al 018000000000."
)
AVISO = "Bancolombia: " + CUERPO
ESPERADO = extractor.MovimientoExtraido(
    "transferencia", 620000, datetime(2026, 9, 29, 21, 28), "NOMBRE DESTINO EJEMPLO"
)


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "llave_bordes.db"))
    db.inicializar(conexion)
    componer_saldo(conexion).configurar(100000000, date(2026, 8, 1))
    yield conexion
    conexion.close()


def _texto(gmail_id: str, texto: str) -> CorreoGmail:
    return CorreoGmail(
        gmail_id, datetime(2026, 9, 29, 21, 29, tzinfo=ZONA_COLOMBIA), "Alerta (ejemplo)", texto, **LEGITIMO
    )


def _html(gmail_id: str, html: str) -> CorreoGmail:
    """Correo construido como respuesta simulada de la API (cuerpo text/html)."""
    datos = base64.urlsafe_b64encode(html.encode("utf-8")).decode("ascii").rstrip("=")
    return correo_desde_mensaje({
        "id": gmail_id,
        "threadId": "hilo-" + gmail_id,
        "labelIds": ["INBOX"],
        "snippet": "",
        "internalDate": "1790734140000",
        "payload": {
            "partId": "",
            "mimeType": "text/html",
            "filename": "",
            "headers": ENCABEZADOS_LEGITIMOS + [{"name": "Subject", "value": "Alerta (ejemplo)"}],
            "body": {"size": len(html), "data": datos},
        },
    })


def _movimientos(conn):
    return [tuple(f) for f in sql(
        conn, "SELECT gmail_id, tipo, monto_centavos, descripcion FROM movimientos ORDER BY gmail_id"
    )]


# --- Textos que NO deben crear movimiento -------------------------------------------------

@pytest.mark.parametrize(
    "texto",
    [
        # Publicidad que empieza como el aviso pero no sigue el formato.
        "Bancolombia: Hola, transferiste tu primer pago con Bre-B. Sigue así.",
        "Bancolombia: Hola, transferiste $6,200.00 con Bre-B y ganaste puntos. Estamos cerca.",
        "Bancolombia: Hola, transferiste $6,200.00 a la llave 3000000000 desde tu cuenta *1234 "
        "y ganaste puntos. Estamos cerca.",
        "Bancolombia: PERSONA EJEMPLO, transferiste a la llave 3000000000 sin monto el 29/09/26 a las 21:28.",
        # Cita dentro de un rechazo con dos puntos: el ":" corta el nombre del titular.
        "Bancolombia: Tu transferencia fue rechazada. Detalle: " + CUERPO,
        "Bancolombia: ¿Reconoces este movimiento? " + CUERPO,
        # Sin "Bancolombia:" delante (decisión del dueño, ronda 3).
        "Reversamos la transferencia. " + CUERPO,
        # Mención suelta.
        "Recuerda: si transferiste a la llave equivocada, llámanos al 018000000000.",
    ],
    ids=["hola_corto", "hola_con_monto", "hola_sin_destino", "sin_monto", "rechazada",
         "reconoces", "sin_prefijo", "mencion_suelta"],
)
def test_textos_que_no_son_aviso_no_crean_movimiento(conn, texto):
    assert extraer_aviso(texto) is None
    resultado = sincronizar(conn, ClienteFalso({"llave-no": _texto("llave-no", texto)}))
    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == []


def test_primer_aviso_deformado_no_cruza_al_segundo(conn):
    """El primer aviso con llave de correo no se reconoce; el nombre de quien
    recibe no puede extenderse hasta la fecha del segundo aviso."""
    deformado = CUERPO.replace("3000000000", "persona@ejemplo.com").replace("$6,200.00", "$999,999.00")
    texto = "Bancolombia: " + deformado + " Bancolombia: " + CUERPO
    # ítem 21: antes se reconocía el segundo aviso; ahora queda no reconocido
    # porque el segundo tiene delante otro texto (el primero): está citado.
    resultado = sincronizar(conn, ClienteFalso({"llave-2": _texto("llave-2", texto)}))
    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == []


def test_dos_avisos_validos_en_un_correo_crean_uno_solo_el_primero(conn):
    segundo = AVISO.replace("$6,200.00", "$9,999.00")
    resultado = sincronizar(conn, ClienteFalso({"llave-dos": _texto("llave-dos", AVISO + " " + segundo)}))
    assert resultado == ResultadoSincronizacion(nuevos=1)
    assert _movimientos(conn) == [("llave-dos", "transferencia", 620000, "NOMBRE DESTINO EJEMPLO")]


# --- HTML y espacios ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "html",
    [
        # Nombres partidos por etiquetas en línea.
        "<p>Bancolombia: PER<span>SONA</span> EJEMPLO, transferiste $6,200.00 a la llave 3000000000 "
        "desde tu cuenta *1234 a NOM<b>BRE</b> DESTINO <span style=\"color:#000\">EJEMPLO</span> "
        "el 29/09/26 a las 21:28. Con Bre-b es de una y gratis.</p>",
        # Nombres partidos en bloques.
        "<table><tr><td>Bancolombia:</td></tr><tr><td>PERSONA</td></tr><tr><td>EJEMPLO, transferiste "
        "$6,200.00 a la llave 3000000000 desde tu cuenta *1234 a NOMBRE<br>DESTINO<br><br>EJEMPLO el "
        "29/09/26 a las 21:28.</td></tr></table>",
        # Espacios no separables como entidades HTML.
        "<p>Bancolombia:&nbsp;PERSONA&nbsp;EJEMPLO,&nbsp;transferiste&nbsp;$6,200.00&nbsp;a&nbsp;la"
        "&nbsp;llave&nbsp;3000000000&nbsp;desde&nbsp;tu&nbsp;cuenta&nbsp;*1234&nbsp;a&nbsp;NOMBRE"
        "&nbsp;DESTINO&nbsp;EJEMPLO&nbsp;el&nbsp;29/09/26&nbsp;a&nbsp;las&nbsp;21:28.</p>",
        # Invisibles de ancho cero dentro de los nombres y la palabra clave.
        "<p>Bancolombia: PER&#8203;SONA EJEMPLO, trans&#8204;feriste $6,200.00 a la llave 3000000000 "
        "desde tu cuenta *1234 a NOMBRE DES&#65279;TINO EJEMPLO el 29/09/26 a las 21:28.</p>",
    ],
    ids=["etiquetas_en_linea", "bloques", "nbsp", "invisibles"],
)
def test_html_con_nombres_partidos_crea_la_transferencia(conn, html):
    correo = _html("llave-html", html)
    assert sincronizar(conn, ClienteFalso({"llave-html": correo})) == ResultadoSincronizacion(nuevos=1)
    assert _movimientos(conn) == [("llave-html", "transferencia", 620000, "NOMBRE DESTINO EJEMPLO")]


@pytest.mark.parametrize("espacio", [" ", " ", " ", "　", "\t", "\r\n"])
def test_espacios_unicode_se_normalizan(espacio):
    assert extraer_aviso(AVISO.replace(" ", espacio)) == ESPERADO


def test_html_nombre_partido_en_palabra_no_une_letras():
    """Una etiqueta de bloque dentro de una palabra la parte: la descripción
    lleva el espacio, nunca letras pegadas de celdas distintas."""
    texto = html_a_texto(
        "<p>Bancolombia: PERSONA EJEMPLO, transferiste $6,200.00 a la llave 3000000000 desde tu "
        "cuenta *1234 a NOMBRE DES</p><p>TINO EJEMPLO el 29/09/26 a las 21:28.</p>"
    )
    movimiento = extraer_aviso(texto)
    assert movimiento is not None and movimiento.descripcion == "NOMBRE DES TINO EJEMPLO"


# --- Textos largos ------------------------------------------------------------------------

_BASURA = (
    "Bancolombia: PERSONA EJEMPLO, transferiste $6,200.00 a la llave 3000000000 desde tu cuenta *1234 a "
    + "NOMBRE DESTINO " * 30
)


@pytest.mark.parametrize(
    "texto",
    [
        (_BASURA * 300)[:100_000],
        "Bancolombia: " + ("A " * 50_000),
        "Bancolombia: PERSONA, transferiste $6,200.00 a la llave 3000000000 desde tu cuenta *1234 a "
        + ("B, " * 34_000),
        ("PERSONA EJEMPLO, transferiste $6,200.00 a la llave " + "1" * 30 + " ") * 1200,
    ],
    ids=["aviso_repetido", "nombre_titular_largo", "destino_largo_con_comas", "llaves_largas"],
)
def test_extractor_con_100_kb_de_basura_tarda_menos_de_un_segundo(texto):
    texto = texto[:100_000]
    inicio = time.perf_counter()
    for funcion in (extractor.extraer_transferiste_llave, extractor.extraer):
        assert funcion(texto) is None
    assert time.perf_counter() - inicio < 1.0


def test_nombre_de_quien_recibe_de_mas_de_100_caracteres_no_se_reconoce():
    assert extraer_aviso(AVISO.replace("NOMBRE DESTINO EJEMPLO", "N" * 101)) is None
    assert extraer_aviso(AVISO.replace("NOMBRE DESTINO EJEMPLO", "N" * 100)).descripcion == "N" * 100


# --- Los tres formatos anteriores siguen leyéndose de extremo a extremo --------------------

def test_los_cuatro_formatos_juntos_en_una_sincronizacion(conn):
    correos = {
        "f-compraste": _texto("f-compraste", (AVISOS / "compraste_formato_real.txt").read_text(encoding="utf-8")),
        "f-transferiste": _html(
            "f-transferiste",
            "<p>" + (AVISOS / "transferiste_formato_real.txt").read_text(encoding="utf-8") + "</p>",
        ),
        "f-recibiste": _texto("f-recibiste", (AVISOS / "recibiste_basico.txt").read_text(encoding="utf-8")),
        "f-llave": _html("f-llave", "<div><span>" + AVISO + "</span></div>"),
    }
    assert sincronizar(conn, ClienteFalso(correos)) == ResultadoSincronizacion(nuevos=4)
    assert _movimientos(conn) == [
        ("f-compraste", "compra", 24570000, "MERPAGO*TIENDAEJEMPLO"),
        ("f-llave", "transferencia", 620000, "NOMBRE DESTINO EJEMPLO"),
        ("f-recibiste", "ingreso", 16000000, "PERSONA EJEMPLO"),
        ("f-transferiste", "transferencia", 450000, "*0000"),
    ]
    # Una segunda sincronización no duplica nada.
    assert sincronizar(conn, ClienteFalso(correos)) == ResultadoSincronizacion()
    assert len(_movimientos(conn)) == 4


# --- Ronda 1 de revisión: el titular es un nombre de pila, no una frase ---

CUERPO_LLAVE = (
    "PERSONA EJEMPLO, transferiste $6,200.00 a la llave 3000000000 desde tu cuenta *1234 "
    "a NOMBRE DESTINO EJEMPLO el 29/09/26 a las 21:28. Con Bre-b es de una y gratis."
)


@pytest.mark.parametrize(
    "texto",
    [
        "Bancolombia: Reversamos esta transferencia. " + CUERPO_LLAVE,
        "Bancolombia: Anulamos la operacion de " + CUERPO_LLAVE,
        "Bancolombia: Reconoces este movimiento " + CUERPO_LLAVE,
        "Bancolombia: Si no fuiste tu quien dice " + CUERPO_LLAVE,
    ],
    ids=["reversamos", "anulamos", "reconoces_sin_signo", "si_no_fuiste"],
)
def test_frase_tras_el_prefijo_no_se_toma_como_titular(conn, texto):
    assert extraer_aviso(texto) is None
    correo = _texto("x", texto)
    assert sincronizar(conn, ClienteFalso({"x": correo})) == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == []


@pytest.mark.parametrize(
    "titular",
    ["ANA", "María José", "JOSÉ ÑUÑEZ PÉREZ"],
    ids=["una_palabra", "dos_palabras", "tres_palabras_con_tildes"],
)
def test_titular_de_una_a_tres_palabras_se_reconoce(titular):
    texto = "Bancolombia: " + titular + CUERPO_LLAVE[len("PERSONA EJEMPLO"):]
    movimiento = extraer_aviso(texto)
    assert movimiento is not None
    assert movimiento.descripcion == "NOMBRE DESTINO EJEMPLO"
    assert movimiento.monto_centavos == 620000


@pytest.mark.parametrize(
    "titular",
    [
        "ANA MARIA PEREZ GOMEZ",  # 4 palabras
        "A. PERSONA",  # con punto
        "ANA-MARIA",  # con otro signo
        "ANA  MARIA",  # doble espacio (tras normalizar sigue siendo 1; ver abajo)
        "A" * 41,  # más de 40 caracteres
    ],
    ids=["cuatro_palabras", "punto", "guion", "doble_espacio", "mas_de_40"],
)
def test_titular_fuera_de_forma_no_se_reconoce(titular):
    texto = "Bancolombia: " + titular + CUERPO_LLAVE[len("PERSONA EJEMPLO"):]
    if titular == "ANA  MARIA":
        # La normalización deja un solo espacio: es un nombre válido de 2 palabras.
        assert extraer_aviso(texto) is not None
        return
    assert extraer_aviso(texto) is None
    assert extractor.extraer(texto) is None


def test_aviso_citado_con_su_prefijo_completo_queda_no_reconocido():
    """Un aviso completo con su propio "Bancolombia:" citado dentro de otro
    texto. Antes era el riesgo conocido
    ``test_riesgo_conocido_aviso_citado_con_su_prefijo_completo``."""
    # ítem 21: antes se reconocía (riesgo conocido); ahora queda no reconocido
    # porque "Reversamos la transferencia:" no es un encabezado conocido.
    assert extraer_aviso("Reversamos la transferencia: Bancolombia: " + CUERPO_LLAVE) is None


@pytest.mark.parametrize(
    ("destino", "reconocido"),
    [
        ("EMPRESA EJEMPLO S.A.S.", True),
        ("PERSONA EJEMPLO", True),
        ("PERSONA EJEMPLO,", False),
        ("PERSONA EJEMPLO..", False),
        ("PERSONA EJEMPLO -", False),
    ],
    ids=["sas_con_punto", "letra", "coma_final", "dos_puntos", "guion_final"],
)
def test_final_del_nombre_de_quien_recibe(destino, reconocido):
    texto = CUERPO_LLAVE.replace("NOMBRE DESTINO EJEMPLO", destino)
    movimiento = extractor.extraer("Bancolombia: " + texto)
    if reconocido:
        assert movimiento is not None and movimiento.descripcion == destino
    else:
        assert movimiento is None
