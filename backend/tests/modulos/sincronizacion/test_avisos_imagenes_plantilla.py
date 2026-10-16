"""Ítem 21: imágenes de la plantilla delante del encabezado (versión text/plain).

El diagnóstico ``--mostrar-previo`` en la VM (30/09/2026, 6 avisos reales)
mostró que la versión text/plain de los avisos lista las imágenes de la
plantilla como ``alt [url]`` antes de "¡Listo! Todo salió bien con tus
movimientos". Se quitan solo esas referencias (lista cerrada
``IMAGENES_PLANTILLA``), solo al comienzo del texto previo; cualquier otro
texto sigue siendo una cita.

Todos los datos son inventados (hex, montos, nombres, cuentas).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from finanzas import db
from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import MovimientoExtraido
from finanzas.gmail import CorreoGmail, correo_desde_mensaje
from finanzas.sincronizacion import (
    ARCHIVOS_IMAGEN_PLANTILLA,
    AVISO_CITADO,
    AVISO_VALIDO,
    IMAGENES_PLANTILLA,
    ResultadoSincronizacion,
    _analizar,
    clasificar_correo,
    extraer_aviso,
    sincronizar,
)
from tests.soporte.ayudas_db import sql

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "gmail" / "imagenes_plantilla"

HOST = "bancolombia-email-wsuite.s3.amazonaws.com"
HEX1 = "0123456789abcdef01234567"
HEX2 = "aaaaaaaaaaaaaaaaaaaaaaaa"
URL_LOGO = f"https://{HOST}/templates/{HEX1}/img/header-logo.png"
URL_ICONO = f"https://{HOST}/templates/{HEX2}/img/chulo.png"
LOGO = f"Logo Bancolombia [{URL_LOGO}]"
ICONO = f"yellow-icon [{URL_ICONO}]"
ENCABEZADO = "¡Listo! Todo salió bien con tus movimientos"

AVISO = (
    "Bancolombia: Compraste $87.350,00 en MERPAGO*TIENDA EJEMPLO con tu T.Deb *4321, "
    "el 12/08/2026 a las 19:05. Si tienes dudas, encuentranos aqui: 018000000000."
)
ESPERADO = MovimientoExtraido("compra", 8735000, datetime(2026, 8, 12, 19, 5), "MERPAGO*TIENDA EJEMPLO")
AVISO_LLAVE = (
    "Bancolombia: NOMBRE INVENTADO, transferiste $6,200.00 a la llave 3000000000 desde tu "
    "cuenta *1234 a NOMBRE DESTINO EJEMPLO el 29/08/26 a las 21:28. Con Bre-b es de una y gratis."
)
ESPERADO_LLAVE = MovimientoExtraido(
    "transferencia", 620000, datetime(2026, 8, 29, 21, 28), "NOMBRE DESTINO EJEMPLO"
)


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "imagenes.db"))
    db.inicializar(conexion)
    with db.transaccion(conexion):
        sql(
            conexion,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, ?, ?)",
            (100000000, "2026-08-01"),
        )
    yield conexion
    conexion.close()


class Cliente:
    def __init__(self, correos: list[CorreoGmail]):
        self.correos = {c.gmail_id: c for c in correos}

    def listar_ids(self, desde: date) -> list[str]:
        return list(self.correos)

    def obtener(self, gmail_id: str) -> CorreoGmail:
        return self.correos[gmail_id]


def _cargar(nombre: str) -> CorreoGmail:
    return correo_desde_mensaje(json.loads((FIXTURES / nombre).read_text(encoding="utf-8")))


def _movimientos(conn) -> list[tuple]:
    return sql(
        conn, "SELECT tipo, monto_centavos, fecha_hora, descripcion FROM movimientos"
    ).fetchall()


# --- Fixtures con la forma real (multipart: text/plain con imágenes + HTML) --------------

@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        (
            "valido_compraste.json",
            ("compra", 5432100, "2026-09-15T18:40:00", "MERPAGO*TIENDA INVENTADA"),
        ),
        (
            "valido_transferiste_llave.json",
            ("transferencia", 750000, "2026-09-16T09:15:00", "NOMBRE DESTINO EJEMPLO"),
        ),
    ],
)
def test_fixture_con_imagenes_de_plantilla_crea_su_movimiento(conn, nombre, esperado):
    correo = _cargar(nombre)
    assert len(correo.textos) == 2  # text/plain y HTML
    assert [_analizar(t)[0] for t in correo.textos] == [AVISO_VALIDO, AVISO_VALIDO]
    estado, _ = clasificar_correo(correo.textos)
    assert estado == AVISO_VALIDO
    resultado = sincronizar(conn, Cliente([correo]))
    assert resultado == ResultadoSincronizacion(nuevos=1)
    assert _movimientos(conn) == [esperado]


def test_fixture_de_reverso_con_imagenes_queda_no_reconocido(conn):
    """Reverso que cita el aviso: las imágenes van delante del texto del
    reverso. Quitar las imágenes no basta para que pase."""
    correo = _cargar("reverso_compraste.json")
    assert [_analizar(t)[0] for t in correo.textos] == [AVISO_CITADO, AVISO_CITADO]
    resultado = sincronizar(conn, Cliente([correo]))
    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == []


def test_hay_solo_los_fixtures_esperados():
    assert sorted(p.name for p in FIXTURES.glob("*.json")) == [
        "reverso_compraste.json",
        "valido_compraste.json",
        "valido_transferiste_llave.json",
    ]


# --- Variantes aceptadas -----------------------------------------------------------------

@pytest.mark.parametrize(
    "previo",
    [
        f"{LOGO} {ICONO} {ENCABEZADO} ",
        f"{LOGO}\n{ICONO}\n\n{ENCABEZADO}\n\n",
        f"{LOGO}{ICONO}¡Listo!Todo salió bien con tus movimientos ",  # sin espacios
        f"{LOGO.replace('https://', 'http://')} {ICONO} {ENCABEZADO} ",
        f"{LOGO} {ICONO.replace('https://', 'http://')} {ENCABEZADO} ",
        f"{LOGO} {ENCABEZADO} ",  # una sola imagen
        f"{ICONO} {ENCABEZADO} ",
        f"{ICONO} {LOGO} {ENCABEZADO} ",  # orden invertido
        f"LOGO BANCOLOMBIA [{URL_LOGO}] Yellow-Icon [{URL_ICONO}] {ENCABEZADO} ",
        f"logo bancolombia[{URL_LOGO}]YELLOW-ICON[{URL_ICONO}]{ENCABEZADO}",
        f"{LOGO} {ICONO} ",  # imágenes sin encabezado
        f"{LOGO} {LOGO} {ICONO} {ENCABEZADO} ",  # repetida
    ],
    ids=[
        "real", "saltos", "sin_espacios", "http_logo", "http_icono", "solo_logo", "solo_icono",
        "orden_invertido", "mayusculas", "minusculas_pegado", "sin_encabezado", "repetida",
    ],
)
@pytest.mark.parametrize(("aviso", "esperado"), [(AVISO, ESPERADO), (AVISO_LLAVE, ESPERADO_LLAVE)])
def test_imagenes_de_plantilla_delante_se_aceptan(previo, aviso, esperado):
    assert extraer_aviso(previo + aviso + "\n\nPie de página de ejemplo.") == esperado


# --- Adversarias: siguen citadas ---------------------------------------------------------

_OTRO = f"https://{HOST}/templates/{HEX1}/img/"

ADVERSARIAS = {
    "texto_entre_imagenes": f"{LOGO} Reversamos la transacción {ICONO} {ENCABEZADO} ",
    "texto_antes_de_la_primera": f"Reversamos la transacción {LOGO} {ICONO} {ENCABEZADO} ",
    "texto_tras_imagenes_antes_del_encabezado": f"{LOGO} {ICONO} Reversamos {ENCABEZADO} ",
    "texto_tras_encabezado": f"{LOGO} {ICONO} {ENCABEZADO} Reversamos la transacción: ",
    "host_con_sufijo": f"Logo Bancolombia [https://{HOST}.evil.example/templates/{HEX1}/img/header-logo.png] {ENCABEZADO} ",
    "otro_host": f"Logo Bancolombia [https://evil.example/templates/{HEX1}/img/header-logo.png] {ENCABEZADO} ",
    "host_con_usuario": f"Logo Bancolombia [https://evil.example@{HOST}/templates/{HEX1}/img/header-logo.png] {ENCABEZADO} ",
    "otro_alt": f"Logo Banco [{URL_LOGO}] {ENCABEZADO} ",
    "alt_con_texto_extra": f"Logo Bancolombia reverso [{URL_LOGO}] {ENCABEZADO} ",
    "sin_alt": f"[{URL_LOGO}] {ENCABEZADO} ",
    "ruta_con_puntos": f"Logo Bancolombia [https://{HOST}/templates/x/../img/header-logo.png] {ENCABEZADO} ",
    "ruta_extra": f"Logo Bancolombia [https://{HOST}/templates/{HEX1}/otra/img/header-logo.png] {ENCABEZADO} ",
    "hex_mayusculas": f"Logo Bancolombia [https://{HOST}/templates/0123456789ABCDEF01234567/img/header-logo.png] {ENCABEZADO} ",
    "hex_no_hex": f"Logo Bancolombia [https://{HOST}/templates/0123456789abcdefg1234567/img/header-logo.png] {ENCABEZADO} ",
    "hex_vacio": f"Logo Bancolombia [https://{HOST}/templates//img/header-logo.png] {ENCABEZADO} ",
    "otro_archivo": f"Logo Bancolombia [{_OTRO}reverso.png] {ENCABEZADO} ",
    "archivo_con_sufijo": f"Logo Bancolombia [{_OTRO}header-logo.png.gif] {ENCABEZADO} ",
    "host_mayusculas": f"Logo Bancolombia [https://{HOST.upper()}/templates/{HEX1}/img/header-logo.png] {ENCABEZADO} ",
    "otro_esquema": f"Logo Bancolombia [ftp://{HOST}/templates/{HEX1}/img/header-logo.png] {ENCABEZADO} ",
    "sin_corchete_final": f"Logo Bancolombia [{URL_LOGO} {ENCABEZADO} ",
    "url_con_consulta": f"Logo Bancolombia [{URL_LOGO}?reverso=1] {ENCABEZADO} ",
    "imagen_tras_encabezado_con_texto": f"{ENCABEZADO} {LOGO} Reversamos: ",
    "imagen_tras_encabezado": f"{LOGO} {ENCABEZADO} {ICONO} ",
    "texto_tras_imagenes_sin_encabezado": f"{LOGO} {ICONO} Reversamos la transacción: ",
}


@pytest.mark.parametrize("cita", list(ADVERSARIAS))
@pytest.mark.parametrize("aviso", [AVISO, AVISO_LLAVE], ids=["compraste", "llave"])
def test_otro_texto_con_imagenes_sigue_citado(cita, aviso):
    texto = ADVERSARIAS[cita] + aviso + "\n\nPie de página de ejemplo."
    assert extraer_aviso(texto) is None
    assert _analizar(texto)[0] == AVISO_CITADO


def test_reversamos_en_html_veta_text_plain_limpio_con_imagenes():
    plano = f"{LOGO} {ICONO}\n\n{ENCABEZADO}\n\n{AVISO}\n"
    html = f"{ENCABEZADO} Reversamos la siguiente transacción: {AVISO}"
    assert _analizar(plano)[0] == AVISO_VALIDO
    assert clasificar_correo([plano, html]) == (AVISO_CITADO, None)
    assert clasificar_correo([html, plano]) == (AVISO_CITADO, None)


def test_listas_cerradas():
    """Solo lo visto en los avisos reales (diagnóstico del 30/09/2026)."""
    assert IMAGENES_PLANTILLA == ("Logo Bancolombia", "yellow-icon")
    assert ARCHIVOS_IMAGEN_PLANTILLA == ("header-logo.png", "chulo.png")


def test_diagnostico_muestra_la_clave_sin_imagenes():
    """``--mostrar-previo`` compara (y muestra) la clave tras quitar las imágenes."""
    from finanzas import prueba_en_seco

    estado, _, clave = prueba_en_seco.describir_previo(f"{LOGO}{ICONO} {ENCABEZADO} {AVISO}")
    assert estado == AVISO_VALIDO
    assert clave == "(35 caracteres) «listotodosaliobiencontusmovimientos»"
