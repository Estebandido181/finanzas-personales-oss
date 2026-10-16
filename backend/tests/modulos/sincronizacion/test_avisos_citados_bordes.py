"""Ítem 21, casos borde: avisos citados vs. variaciones de la plantilla real.

Dos riesgos opuestos:

* **falso rechazo** (el más grave): un aviso legítimo de Bancolombia, con
  variaciones normales de la plantilla HTML (logo con ``alt``, preencabezado
  oculto vacío, ``&nbsp;`` y entidades, "¡Listo!" y "Todo salió bien..." en
  elementos separados, mayúsculas, multipart con un texto plano distinto),
  queda como "no reconocido";
* **falso positivo**: un aviso citado (texto delante, encabezado parecido o
  repetido, texto entre el encabezado y "Bancolombia:") crea un movimiento.

Cada correo se construye como respuesta de la API de Gmail y pasa por la
sincronización completa (``correo_desde_mensaje`` + ``sincronizar``), igual
que los reales. La plantilla imita
tests/fixtures/gmail/autenticacion/legitimo_*_real_anonimizado.json.
Todos los datos son inventados.
"""

from __future__ import annotations

import base64
from datetime import date

import pytest

from finanzas import db
from finanzas.gmail import CorreoGmail, correo_desde_mensaje
from finanzas.sincronizacion import ResultadoSincronizacion, sincronizar
from tests.soporte.ayudas_db import sql
from tests.soporte.gmail_falso import ENCABEZADOS_LEGITIMOS
from tests.soporte.avisos_citados_bordes import _Cliente, _b64, _mensaje, _movimientos, _parte, _plano, _plantilla, _sincronizar, conn  # ayudas compartidas

# --- Construcción de correos inventados --------------------------------------------------

AVISOS = {
    "compraste": "Bancolombia: Compraste $87.350,00 en SUPERMERCADO EJEMPLO con tu T.Deb *4321, "
    "el 12/08/2026 a las&nbsp;19:05. Si tienes dudas, encuentranos aqui: 018000000000.",
    "transferiste": "Bancolombia: Transferiste $6,000.00 desde tu cuenta *1234 a la cuenta *3000000000 "
    "el 14/08/26 a las 7:05 p. m. ¿Dudas? Llamanos al 018000000000.",
    "recibiste": "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO en tu cuenta "
    "**1234, el 29/08/2026 a las&nbsp;10:00. Si tienes dudas, hablemos: 018000000000.",
    "transferiste_llave": "Bancolombia: PERSONA EJEMPLO, transferiste $6,200.00 a la llave 3000000000 "
    "desde tu cuenta *1234 a NOMBRE DESTINO EJEMPLO el 29/08/26 a las&nbsp;21:28. Con Bre-b es de "
    "una y gratis. Dudas al 018000000000.",
}
FORMATOS = list(AVISOS)
# Encabezado tal como viene en el HTML real anonimizado.
H1 = "<h1>&iexcl;Listo! Todo sali&oacute; bien con tus movimientos</h1>"
ENCABEZADO = "¡Listo! Todo salió bien con tus movimientos"




















# --- Falsos rechazos: variaciones de la plantilla real que deben leerse ------------------

# (cabecera, texto antes de la tabla)
VARIANTES_LEGITIMAS = {
    "logo_con_alt": (H1, ""),
    "preencabezado_oculto_vacio": (H1, '<div style="display:none;max-height:0">&nbsp;</div>'),
    "preencabezado_relleno_847_zwnj": (
        H1,
        '<div style="display:none">' + "&#847;&zwnj;&nbsp;" * 30 + "</div>",
    ),
    "preencabezado_relleno_8199_bom": (
        H1,
        '<span style="display:none">' + "&#8199;&#65279;&#847; " * 20 + "</span>",
    ),
    "nbsp_entre_palabras": (
        "<h1>&iexcl;Listo!&nbsp;Todo&nbsp;sali&oacute;&nbsp;bien&nbsp;con&nbsp;tus&nbsp;movimientos</h1>",
        "",
    ),
    "iexcl_decimal": ("<h1>&#161;Listo! Todo sali&#243; bien con tus movimientos</h1>", ""),
    "iexcl_hexadecimal": ("<h1>&#xA1;Listo! Todo sali&#xF3; bien con tus movimientos</h1>", ""),
    "iexcl_literal": ("<h1>¡Listo! Todo salió bien con tus movimientos</h1>", ""),
    "separados_h1_y_p": ("<h1>&iexcl;Listo!</h1><p>Todo sali&oacute; bien con tus movimientos</p>", ""),
    "separados_en_celdas": (
        "<table><tr><td>&iexcl;Listo!</td><td>Todo sali&oacute; bien con tus movimientos</td></tr></table>",
        "",
    ),
    "separados_con_br": ("&iexcl;Listo!<br>Todo sali&oacute; bien con tus movimientos", ""),
    "spans_con_salto_en_fuente": (
        "<span>&iexcl;Listo!</span>\n<span>Todo sali&oacute; bien con tus movimientos</span>",
        "",
    ),
    "mayusculas": ("<h1>&iexcl;LISTO! TODO SALI&Oacute; BIEN CON TUS MOVIMIENTOS</h1>", ""),
    "mayusculas_mezcladas": ("<h1>&iexcl;listo! todo Sali&oacute; Bien Con Tus Movimientos</h1>", ""),
    "negritas_dentro_de_palabra": (
        "<h1><b>&iexcl;Lis</b>to! <i>Todo</i> sali&oacute; bien con tus movimientos</h1>",
        "",
    ),
    "guion_suave_y_espacio_cero": (
        "<h1>&iexcl;Lis&shy;to! Todo&#8203; sali&oacute; bien con tus movimientos</h1>",
        "",
    ),
    "comentario_condicional_outlook": (
        "<!--[if mso]><p>Solo Outlook</p><![endif]-->" + H1,
        "",
    ),
    "sin_encabezado": ("", ""),
}


@pytest.mark.parametrize("variante", list(VARIANTES_LEGITIMAS))
@pytest.mark.parametrize("formato", FORMATOS)
def test_variante_de_plantilla_legitima_crea_movimiento(conn, formato, variante):
    cabecera, antes = VARIANTES_LEGITIMAS[variante]
    resultado = _sincronizar(conn, html=_plantilla(cabecera, AVISOS[formato], antes))
    assert resultado == ResultadoSincronizacion(nuevos=1)
    assert _movimientos(conn) == 1


@pytest.mark.parametrize("formato", FORMATOS)
def test_bancolombia_en_su_propio_span_crea_movimiento(conn, formato):
    aviso = AVISOS[formato].replace("Bancolombia:", "<span><b>Bancolombia</b></span>:")
    assert _sincronizar(conn, html=_plantilla(H1, aviso)) == ResultadoSincronizacion(nuevos=1)


# (texto plano distinto del HTML, que es el correcto)
PLANOS_DISTINTOS = {
    "plano_de_relleno": "Para ver este mensaje usa un cliente de correo compatible con HTML.",
    "plano_crlf_encabezado_partido": "\r\n¡Listo!\r\nTodo salió bien con tus movimientos\r\n\r\n{aviso}\r\n",
    "plano_igual": ENCABEZADO + "\n\n{aviso}",
    # ítem 21 (ronda 2): el encabezado se compara solo por sus letras, sin
    # tildes ni signos, así que un text/plain sin ellos ya no veta el correo.
    "plano_sin_tildes_ni_iexcl": "Listo! Todo salio bien con tus movimientos\n\n{aviso}",
}


@pytest.mark.parametrize("plano", list(PLANOS_DISTINTOS))
@pytest.mark.parametrize("formato", FORMATOS)
def test_multipart_con_plano_distinto_crea_un_movimiento(conn, formato, plano):
    aviso = AVISOS[formato]
    texto_plano = PLANOS_DISTINTOS[plano].format(aviso=_plano(aviso))
    resultado = _sincronizar(conn, html=_plantilla(H1, aviso), plano=texto_plano)
    assert resultado == ResultadoSincronizacion(nuevos=1)
    assert _movimientos(conn) == 1


# Planos con otro texto delante del aviso (antes estaban en PLANOS_DISTINTOS).
PLANOS_CON_OTRO_ENCABEZADO = {
    "plano_con_alt_del_logo": "[Bancolombia]\n\n" + ENCABEZADO + "\n\n{aviso}",
}


@pytest.mark.parametrize("plano", list(PLANOS_CON_OTRO_ENCABEZADO))
@pytest.mark.parametrize("formato", FORMATOS)
def test_multipart_con_plano_de_otro_encabezado_queda_no_reconocido(conn, formato, plano):
    # ítem 21 (ronda 1): antes se creaba el movimiento con el HTML; ahora queda
    # no reconocido porque el text/plain tiene un texto no permitido delante
    # del aviso (lo cita) y cualquier versión que cite el aviso veta el correo
    # (decisión del team leader). La prueba en seco lo detectaría en la VM.
    aviso = AVISOS[formato]
    texto_plano = PLANOS_CON_OTRO_ENCABEZADO[plano].format(aviso=_plano(aviso))
    resultado = _sincronizar(conn, html=_plantilla(H1, aviso), plano=texto_plano)
    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == 0


@pytest.mark.parametrize("formato", FORMATOS)
def test_multipart_con_html_de_otra_plantilla_queda_no_reconocido(conn, formato):
    # ítem 21 (ronda 1): antes se usaba el text/plain limpio; ahora queda no
    # reconocido porque el HTML cita el aviso tras "Otra plantilla" y
    # cualquier versión que cite el aviso veta el correo.
    aviso = AVISOS[formato]
    resultado = _sincronizar(
        conn,
        html=_plantilla("<h1>Otra plantilla</h1>", aviso),
        plano=ENCABEZADO + "\n\n" + _plano(aviso),
    )
    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == 0


# --- Falsos positivos: avisos citados que no deben crear movimiento ----------------------

# (cabecera, texto antes de la tabla)
CITAS_HTML = {
    # Un display:none no esconde texto para el conversor: mejor rechazar.
    "reverso_en_preencabezado_oculto": (H1, '<div style="display:none">Reversamos la siguiente transacción</div>'),
    "reverso_en_noscript": (H1, "<noscript>Reversamos esta transacción</noscript>"),
    "reverso_en_texto_svg": (H1, "<svg><text>Reversamos esta transacción</text></svg>"),
    "reverso_en_texto_blanco": (H1, '<p style="color:#fff;font-size:1px">Reversamos</p>'),
    # Encabezados parecidos: la comparación no usa NFKC ni confusables.
    "homoglifo_cirilico": ("<h1>&iexcl;List\u043e! Todo sali&oacute; bien con tus movimientos</h1>", ""),
    "i_sin_punto_turca": ("<h1>&iexcl;L\u0131sto! Todo sali&oacute; bien con tus movimientos</h1>", ""),
    "ligadura_fi": ("<h1>&iexcl;Listo! Todo sali&oacute; bien con tus movimientos\ufb01</h1>", ""),
    # Encabezado repetido o con texto entre él y "Bancolombia:".
    "encabezado_repetido": (H1 + H1, ""),
    "encabezado_repetido_en_bloques": (H1, "<p>" + ENCABEZADO + "</p>"),
    "texto_entre_encabezado_y_aviso": (H1 + "<p>Reversamos:</p>", ""),
    "reverso_pegado_al_encabezado": ("<h1>&iexcl;Listo! Todo sali&oacute; bien con tus movimientosReversamos</h1>", ""),
    "encabezado_dentro_de_cita": (
        "<p>Hola, no reconozco esto.</p><blockquote>" + H1 + "</blockquote>",
        "",
    ),
    "reenvio_con_encabezado": ("<p>---------- Forwarded message ---------</p>" + H1, ""),
}


@pytest.mark.parametrize("cita", list(CITAS_HTML))
@pytest.mark.parametrize("formato", FORMATOS)
def test_aviso_citado_en_html_queda_no_reconocido(conn, formato, cita):
    cabecera, antes = CITAS_HTML[cita]
    resultado = _sincronizar(conn, html=_plantilla(cabecera, AVISOS[formato], antes))
    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == 0


# ítem 21 (ronda 2): antes quedaban no reconocidos; ahora se leen porque el
# encabezado se compara solo por sus letras (los signos no pueden esconder una
# cita: cualquier palabra de más sigue vetando el correo).
ENCABEZADOS_CON_OTROS_SIGNOS = {
    "exclamacion_ancha": ("<h1>&iexcl;Listo\uff01 Todo sali&oacute; bien con tus movimientos</h1>", ""),
    "exclamacion_doble": ("<h1>&iexcl;Listo!! Todo sali&oacute; bien con tus movimientos</h1>", ""),
    "solo_un_signo": ("<p>.</p>" + H1, ""),
}


@pytest.mark.parametrize("variante", list(ENCABEZADOS_CON_OTROS_SIGNOS))
@pytest.mark.parametrize("formato", FORMATOS)
def test_encabezado_con_otros_signos_crea_movimiento(conn, formato, variante):
    cabecera, antes = ENCABEZADOS_CON_OTROS_SIGNOS[variante]
    resultado = _sincronizar(conn, html=_plantilla(cabecera, AVISOS[formato], antes))
    assert resultado == ResultadoSincronizacion(nuevos=1)


CITAS_PLANAS = {
    "invisible_no_cf_hangul": "\u3164Reversamos\u3164 ",
    "rtl_override": "\u202esomasreveR\u202c ",
    "encabezado_y_texto_tras_bancolombia": ENCABEZADO + " Bancolombia: Reversamos. ",
    "texto_tras_bancolombia_dos_puntos": "Bancolombia: Reversamos: ",
}


@pytest.mark.parametrize("cita", list(CITAS_PLANAS))
@pytest.mark.parametrize("formato", FORMATOS)
def test_aviso_citado_en_texto_plano_queda_no_reconocido(conn, formato, cita):
    aviso = _plano(AVISOS[formato])
    if cita.startswith("encabezado_y_texto") or cita.startswith("texto_tras"):
        # "Bancolombia: Reversamos. Compraste ..." (sin el segundo "Bancolombia:")
        aviso = aviso.removeprefix("Bancolombia: ")
    resultado = _sincronizar(conn, plano=CITAS_PLANAS[cita] + aviso)
    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == 0


@pytest.mark.parametrize("formato", FORMATOS)
def test_multipart_citado_en_ambas_versiones_queda_no_reconocido(conn, formato):
    aviso = AVISOS[formato]
    resultado = _sincronizar(
        conn,
        html=_plantilla("<h2>Reversamos la siguiente transacción</h2>", aviso),
        plano="Reversamos la siguiente transacción:\n" + _plano(aviso),
    )
    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == 0
