"""Ítem 21, ronda 1: defectos que encontró el tester y sus arreglos.

1. Multipart: cualquier versión del cuerpo (text/plain o HTML) que cite el
   aviso veta el correo, aunque otra lo traiga limpio.
2. Encabezado partido sin espacio ("¡Listo!Todo salió..." al unir dos <span>).
3. Rellenos invisibles que no son Cf (U+115F, U+1160, U+2800, U+3164, U+FFA0)
   delante del aviso.

Reusan las ayudas de test_avisos_citados_bordes. Datos inventados.
"""

from __future__ import annotations

import pytest

from finanzas import db
from finanzas.sincronizacion import (
    AVISO_CITADO,
    AVISO_VALIDO,
    SIN_AVISO,
    ResultadoSincronizacion,
    clasificar_correo,
)
from tests.soporte.ayudas_db import sql
from tests.soporte.avisos_citados_bordes import (
    AVISOS, ENCABEZADO, FORMATOS, H1, _movimientos, _plano, _plantilla, _sincronizar,
)


@pytest.fixture
def conn(tmp_path):
    """La misma base de prueba que test_avisos_citados_bordes."""
    conexion = db.conectar(str(tmp_path / "citados_defectos.db"))
    db.inicializar(conexion)
    with db.transaccion(conexion):
        sql(
            conexion,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, ?, ?)",
            (100000000, "2026-08-01"),
        )
    yield conexion
    conexion.close()


# --- Defecto 1: una versión citada veta el correo -----------------------------------------

# Antes: la versión HTML (la que ve el dueño) citaba el aviso tras
# "Reversamos...", pero el text/plain traía el aviso limpio. Como se probaba
# primero el plano y bastaba con que UNA versión se reconociera, se creaba el
# movimiento.
@pytest.mark.parametrize("formato", FORMATOS)
def test_html_citado_con_plano_limpio_queda_no_reconocido(conn, formato):
    aviso = AVISOS[formato]
    resultado = _sincronizar(
        conn,
        html=_plantilla(H1, aviso, "<h2>Reversamos la siguiente transacción</h2>"),
        plano=ENCABEZADO + "\n\n" + _plano(aviso),
    )
    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == 0


@pytest.mark.parametrize("formato", FORMATOS)
def test_plano_citado_con_html_limpio_queda_no_reconocido(conn, formato):
    aviso = AVISOS[formato]
    resultado = _sincronizar(
        conn,
        html=_plantilla(H1, aviso),
        plano="Reversamos la siguiente transacción:\n\n" + _plano(aviso),
    )
    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == 0


@pytest.mark.parametrize("formato", FORMATOS)
def test_plano_de_relleno_con_html_limpio_crea_movimiento(conn, formato):
    resultado = _sincronizar(
        conn, html=_plantilla(H1, AVISOS[formato]), plano="Tu cliente de correo no muestra HTML."
    )
    assert resultado == ResultadoSincronizacion(nuevos=1)


LIMPIO = ENCABEZADO + " " + _plano(AVISOS["compraste"])
CITADO = "Reversamos: " + _plano(AVISOS["compraste"])


@pytest.mark.parametrize(
    ("textos", "estado"),
    [
        ([LIMPIO], AVISO_VALIDO),
        ([LIMPIO, LIMPIO], AVISO_VALIDO),
        (["Relleno sin aviso.", LIMPIO], AVISO_VALIDO),
        ([CITADO], AVISO_CITADO),
        ([LIMPIO, CITADO], AVISO_CITADO),
        ([CITADO, LIMPIO], AVISO_CITADO),
        (["Relleno sin aviso.", CITADO], AVISO_CITADO),
        # Un primer inicio que no se lee seguido de otro: el segundo está citado.
        (["Bancolombia: Compraste algo. " + _plano(AVISOS["compraste"])], AVISO_CITADO),
        # Un único inicio que no se lee: no hay aviso, pero tampoco cita.
        (["Bancolombia: Compraste algo que no es un aviso."], SIN_AVISO),
        (["Relleno sin aviso."], SIN_AVISO),
        ([], SIN_AVISO),
    ],
    ids=["limpio", "dos_limpios", "relleno_y_limpio", "citado", "limpio_y_citado", "citado_y_limpio",
         "relleno_y_citado", "inicio_incompleto_y_otro", "inicio_incompleto", "relleno", "vacio"],
)
def test_clasificar_correo(textos, estado):
    resultado, movimiento = clasificar_correo(textos)
    assert resultado == estado
    assert (movimiento is not None) == (estado == AVISO_VALIDO)


# --- Defecto 2: encabezado partido sin espacio ----------------------------------------------

# "¡Listo!" y "Todo salió bien..." en dos <span> seguidos (p. ej. con
# display:block por CSS) quedan pegados al convertir el HTML.
@pytest.mark.parametrize("formato", FORMATOS)
def test_encabezado_en_spans_sin_espacio_crea_movimiento(conn, formato):
    cabecera = "<span>&iexcl;Listo!</span><span>Todo sali&oacute; bien con tus movimientos</span>"
    assert _sincronizar(conn, html=_plantilla(cabecera, AVISOS[formato])) == ResultadoSincronizacion(nuevos=1)


def test_encabezado_sin_espacios_no_admite_otras_letras(conn):
    cabecera = "<span>&iexcl;Listo!</span><span>Todo sali&oacute; bien con tus movimientos</span><span>X</span>"
    resultado = _sincronizar(conn, html=_plantilla(cabecera, AVISOS["compraste"]))
    assert resultado == ResultadoSincronizacion(no_reconocidos=1)


# --- Defecto 3: rellenos invisibles no-Cf -------------------------------------------------

# Rellenos de preencabezado que no son de categoría Cf ni espacios Unicode
# (U+3164 relleno hangul, U+2800 braille en blanco, U+FFA0 relleno hangul de
# ancho medio, U+115F y U+1160) y que extractor._normalizar no elimina.
@pytest.mark.parametrize("relleno", ["&#12644;", "&#10240;", "&#65440;", "&#4447;", "&#4448;"])
def test_preencabezado_con_relleno_invisible_crea_movimiento(conn, relleno):
    antes = '<span style="display:none">' + relleno * 5 + "</span>"
    assert _sincronizar(conn, html=_plantilla(H1, AVISOS["compraste"], antes)) == ResultadoSincronizacion(nuevos=1)


def test_relleno_invisible_con_texto_sigue_siendo_cita(conn):
    antes = '<span style="display:none">&#12644;&#12644;Reversamos&#12644;</span>'
    resultado = _sincronizar(conn, html=_plantilla(H1, AVISOS["compraste"], antes))
    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
