"""Ítem 21: avisos citados dentro de otro correo.

Un aviso solo se lee si está al comienzo del mensaje: antes de
"Bancolombia: Compraste/Transferiste/..." solo puede haber nada o un
encabezado de plantilla conocido (``ENCABEZADOS_PERMITIDOS``). Si hay otro
texto ("Reversamos...", un reenvío, un correo educativo...), el aviso está
citado y el correo queda como no reconocido.

Todos los datos son inventados.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import date, datetime
from pathlib import Path

import pytest

from finanzas import db
from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import MovimientoExtraido
from finanzas.gmail import CorreoGmail, correo_desde_mensaje, html_a_texto
from finanzas.compartido.hora import ZONA_COLOMBIA
from finanzas.sincronizacion import (
    ENCABEZADOS_PERMITIDOS,
    ResultadoSincronizacion,
    extraer_aviso,
    sincronizar,
)
from tests.soporte.ayudas_db import sql
from tests.soporte.gmail_falso import LEGITIMO

GMAIL = Path(__file__).resolve().parents[2] / "fixtures" / "gmail"
CITADOS = GMAIL / "citados"
ENCABEZADO = "¡Listo! Todo salió bien con tus movimientos"

# Los cuatro avisos, con su prefijo, y lo que debe extraerse de cada uno.
AVISOS = {
    "compraste": (
        "Bancolombia: Compraste $87.350,00 en MERPAGO*TIENDA EJEMPLO con tu T.Deb *4321, "
        "el 12/08/2026 a las 19:05. Si tienes dudas, encuentranos aqui: 018000000000.",
        MovimientoExtraido("compra", 8735000, datetime(2026, 8, 12, 19, 5), "MERPAGO*TIENDA EJEMPLO"),
    ),
    "transferiste": (
        "Bancolombia: Transferiste $6,000.00 desde tu cuenta *1234 a la cuenta *3000000000 "
        "el 14/08/26 a las 7:05 p. m. ¿Dudas? Llamanos al 018000000000.",
        MovimientoExtraido("transferencia", 600000, datetime(2026, 8, 14, 19, 5), "*0000"),
    ),
    "recibiste": (
        "Bancolombia: Recibiste una transferencia por $160,000 de PERSONA EJEMPLO en tu cuenta "
        "**1234, el 29/08/2026 a las 10:00. Si tienes dudas, hablemos: 018000000000.",
        MovimientoExtraido("ingreso", 16000000, datetime(2026, 8, 29, 10, 0), "PERSONA EJEMPLO"),
    ),
    "transferiste_llave": (
        "Bancolombia: PERSONA EJEMPLO, transferiste $6,200.00 a la llave 3000000000 desde tu "
        "cuenta *1234 a NOMBRE DESTINO EJEMPLO el 29/08/26 a las 21:28. Con Bre-b es de una y "
        "gratis. Dudas al 018000000000.",
        MovimientoExtraido("transferencia", 620000, datetime(2026, 8, 29, 21, 28), "NOMBRE DESTINO EJEMPLO"),
    ),
}
FORMATOS = list(AVISOS)

# Textos inventados que citan un aviso delante de él.
CITAS = {
    "reversamos": "Reversamos la siguiente transacción: ",
    "encabezado_y_reversamos": ENCABEZADO + "\n\nReversamos la siguiente transacción y devolvimos el dinero:\n",
    "educativo": "Así se ven nuestras alertas: ",
    "reenviado": "---------- Forwarded message ---------\nDe: Bancolombia <alertas@example.com>\nAsunto: Aviso\n\n",
    "respuesta_citada": "Hola, no reconozco este movimiento.\n\nEl 29/08/2026, Bancolombia escribió:\n> ",
    "reconoces": "¿Reconoces este movimiento? ",
    "anulacion": "Anulamos esta transacción: ",
    "promocion": "Gana puntos con cada compra. ",
    "encabezado_con_texto_extra": ENCABEZADO + ". Reversamos: ",
    "encabezado_incompleto": "¡Listo!\n\n",
    "encabezado_dos_veces": ENCABEZADO + " " + ENCABEZADO + " ",
    "texto_antes_del_encabezado": "Reverso. " + ENCABEZADO + " ",
}


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "citados.db"))
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


def _correo(gmail_id: str, texto: str) -> CorreoGmail:
    return CorreoGmail(
        gmail_id, datetime(2026, 8, 30, 10, 0, tzinfo=ZONA_COLOMBIA), "Novedad (ejemplo)", texto, **LEGITIMO
    )


def _cargar(ruta: Path) -> CorreoGmail:
    return correo_desde_mensaje(json.loads(ruta.read_text(encoding="utf-8")))


def _movimientos(conn) -> int:
    return sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0]


# --- Avisos citados: no reconocidos ------------------------------------------------------

@pytest.mark.parametrize("cita", list(CITAS))
@pytest.mark.parametrize("formato", FORMATOS)
def test_aviso_citado_queda_no_reconocido(conn, formato, cita):
    aviso, _ = AVISOS[formato]
    texto = CITAS[cita] + aviso + "\n\nGracias por usar nuestros canales."
    assert extraer_aviso(texto) is None
    resultado = sincronizar(conn, Cliente([_correo("citado", texto)]))
    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == 0


@pytest.mark.parametrize("formato", FORMATOS)
def test_fixture_de_reverso_autentico_queda_no_reconocido(conn, formato):
    """Correo HTML con encabezados auténticos: pasa la autenticación y llega al
    extractor, pero el aviso va citado tras "Reversamos ...": no crea movimiento."""
    correo = _cargar(CITADOS / f"reverso_{formato}.json")
    assert all(extraer_aviso(t) is None for t in correo.textos)
    resultado = sincronizar(conn, Cliente([correo]))
    assert resultado == ResultadoSincronizacion(no_reconocidos=1)
    assert _movimientos(conn) == 0


def test_hay_un_fixture_de_reverso_por_formato():
    assert sorted(p.stem for p in CITADOS.glob("*.json")) == sorted(f"reverso_{f}" for f in FORMATOS)


@pytest.mark.parametrize("formato", FORMATOS)
def test_segundo_aviso_tras_uno_valido_no_se_toma(formato):
    """Dos avisos seguidos: se toma solo el primero, nunca el segundo."""
    aviso, esperado = AVISOS[formato]
    otro, _ = AVISOS["compraste" if formato != "compraste" else "recibiste"]
    assert extraer_aviso(ENCABEZADO + " " + aviso + " " + otro) == esperado


@pytest.mark.parametrize("formato", FORMATOS)
def test_aviso_citado_en_html_partido_queda_no_reconocido(formato):
    aviso, _ = AVISOS[formato]
    cuerpo = aviso.removeprefix("Bancolombia: ")
    html = (
        "<table><tr><td>Reversamos esta transacción</td></tr>"
        f"<tr><td><b>Bancolombia:</b></td><td>{cuerpo}</td></tr></table>"
    )
    assert extraer_aviso(html_a_texto(html)) is None


# --- Avisos normales: se siguen leyendo igual --------------------------------------------

@pytest.mark.parametrize(
    "previo",
    [
        "",
        ENCABEZADO + "\n\n",
        ENCABEZADO,  # "Bancolombia:" pegado al encabezado (HTML sin espacio)
        "  " + ENCABEZADO.upper() + "\n",
        ENCABEZADO.replace(" ", "\n  "),
        "​" + ENCABEZADO + "​ ",
        unicodedata.normalize("NFD", ENCABEZADO) + " ",  # tildes descompuestas
    ],
    ids=["nada", "encabezado", "pegado", "mayusculas", "saltos", "invisibles", "nfd"],
)
@pytest.mark.parametrize("formato", FORMATOS)
def test_aviso_al_comienzo_se_lee_igual(formato, previo):
    aviso, esperado = AVISOS[formato]
    assert extraer_aviso(previo + aviso + "\n\nPie de página de ejemplo.") == esperado


@pytest.mark.parametrize("formato", FORMATOS)
def test_aviso_en_html_con_encabezado_en_su_propio_bloque(formato):
    aviso, esperado = AVISOS[formato]
    cuerpo = aviso.removeprefix("Bancolombia: ")
    html = (
        "<table><tr><td><h1>&iexcl;Listo! Todo sali&oacute; bien con tus movimientos</h1></td></tr>"
        f"<tr><td><b>Bancolombia:</b></td><td>{cuerpo}</td></tr></table>"
    )
    assert extraer_aviso(html_a_texto(html)) == esperado


_LEGITIMOS = sorted(
    [p.relative_to(GMAIL).as_posix() for p in (GMAIL / "autenticacion").glob("legitimo_*.json")]
    + [
        "compraste_html.json",
        "compraste_html_anidado.json",
        "transferiste_multipart.json",
        "transferiste_llave_html.json",
        "recibiste_html.json",
        "recibiste_html_celdas.json",
    ]
)


def test_lista_de_legitimos_incluye_los_reales_anonimizados():
    assert "autenticacion/legitimo_aviso_real_anonimizado.json" in _LEGITIMOS
    assert "autenticacion/legitimo_recibiste_real_anonimizado.json" in _LEGITIMOS
    assert len([n for n in _LEGITIMOS if n.startswith("autenticacion/legitimo_")]) >= 4


@pytest.mark.parametrize("nombre", _LEGITIMOS)
def test_fixtures_legitimos_siguen_creando_su_movimiento(conn, nombre):
    resultado = sincronizar(conn, Cliente([_cargar(GMAIL / nombre)]))
    assert resultado == ResultadoSincronizacion(nuevos=1)
    assert _movimientos(conn) == 1


def test_lista_de_encabezados_es_cerrada():
    """Solo el encabezado visto en los correos reales anonimizados. Agregar
    otro exige un fixture que lo reproduzca (ver el comentario de la constante)."""
    assert ENCABEZADOS_PERMITIDOS == (ENCABEZADO,)
