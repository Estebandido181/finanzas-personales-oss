"""Diagnóstico ``--mostrar-previo`` de la prueba en seco (ítem 21).

Muestra, enmascarado, lo que hay delante del aviso; nunca el aviso ni lo que
va después. Todos los datos son inventados.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from finanzas import db, prueba_en_seco
from finanzas.gmail import CorreoGmail, correo_desde_mensaje
from finanzas.compartido.hora import ZONA_COLOMBIA
from finanzas.sincronizacion import ResultadoSincronizacion, sincronizar
from tests.soporte.ayudas_db import sql
from tests.soporte.gmail_falso import LEGITIMO, ClienteFalso

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "gmail" / "diagnostico" / "preencabezado_oculto.json"
ENCABEZADO = "¡Listo! Todo salió bien con tus movimientos"
COMPRA = (
    "Bancolombia: Compraste $87.350,00 en SUPERMERCADO INVENTADO con tu T.Deb *4321, "
    "el 12/08/2026 a las 19:05. Si tienes dudas, encuentranos aqui."
)
DESPUES = " Texto final inventado MARCA-FINAL-INVENTADA."
# Nada de esto (del aviso o de después) puede aparecer en la salida.
DEL_AVISO = [
    "87", "350", "SUPERMERCADO", "INVENTADO con", "4321", "12/08", "19:05", "Compraste", "Bancolombia",
    "encuentranos", "MARCA-FINAL", "FERRETERIA", "64.215", "CIERRE-POSTERIOR", "$",
]


def _correo(gmail_id: str, *textos: str, dia: int = 12) -> CorreoGmail:
    return CorreoGmail(
        gmail_id, datetime(2026, 8, dia, 9, 30, tzinfo=ZONA_COLOMBIA), "Asunto inventado",
        textos[0], alternativos=tuple(textos[1:]), **LEGITIMO,
    )


def _fixture() -> CorreoGmail:
    return correo_desde_mensaje(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _sin_aviso(salida: str) -> None:
    for dato in DEL_AVISO:
        assert dato not in salida, dato


# --- describir_previo / lineas_previo -----------------------------------------


def test_previo_enmascara_digitos_y_correos():
    texto = "Hola persona.ejemplo@example.com, ref 2026-77 " + ENCABEZADO + " " + COMPRA + DESPUES
    estado, previo, clave = prueba_en_seco.describir_previo(texto)
    assert estado == "citado"
    assert previo == "(71 caracteres) «Hola [correo], ref ####-## ¡Listo! Todo salió bien con tus movimientos »"
    assert clave == "(48 caracteres) «holaref######listotodosaliobiencontusmovimientos»"
    _sin_aviso(previo + clave)
    assert "persona.ejemplo" not in previo + clave and "example" not in previo + clave


def test_previo_escapa_invisibles_que_quedan_tras_normalizar():
    # ㅤ y ⠀ sobreviven a la normalización (el lector los ignora solo
    # al comparar); ‌, ͏ y \xa0 ya los quita o colapsa el lector.
    texto = "ㅤ⠀‌͏\xa0" + ENCABEZADO + "ㅤ " + COMPRA
    estado, previo, clave = prueba_en_seco.describir_previo(texto)
    assert estado == "valido"
    assert previo == "(48 caracteres) «\\u3164\\u2800 ¡Listo! Todo salió bien con tus movimientos\\u3164 »"
    assert clave == "(35 caracteres) «listotodosaliobiencontusmovimientos»"


def test_escapar_invisibles_por_categoria_y_barra():
    assert prueba_en_seco._escapar_invisibles("a​b c͏d e\\f ñ") == (
        "a\\u200bb\\xa0c\\u034fd\\u2028e\\\\f ñ"
    )


def test_previo_recortado_con_longitud_original():
    relleno = "Relleno inventado " * 30  # 540 caracteres
    estado, previo, _ = prueba_en_seco.describir_previo(relleno + COMPRA)
    assert estado == "citado"
    assert previo.startswith("(540 caracteres, recortado a 300: los primeros y los últimos 150) «Relleno")
    cuerpo = previo.split("«", 1)[1].rstrip("»")
    assert len(cuerpo) == 300 + len(" [...] ")
    _sin_aviso(previo)


def test_sin_inicio_muestra_el_comienzo_cortado_antes_de_un_aviso_sin_prefijo():
    estado, previo, clave = prueba_en_seco.describir_previo(
        "Saludo inventado 12. Compraste $87.350,00 en SUPERMERCADO INVENTADO" + DESPUES
    )
    assert estado == "sin_aviso"
    assert previo == "(21 caracteres) «Saludo inventado ##. »"
    assert clave == "(17 caracteres) «saludoinventado##»"
    _sin_aviso(previo + clave)


def test_sin_inicio_texto_largo_toma_solo_el_comienzo():
    _, previo, _ = prueba_en_seco.describir_previo("x" * 250 + " MARCA-FINAL-INVENTADA")
    assert previo == f"({prueba_en_seco.LARGO_SIN_INICIO} caracteres) «{'x' * 200}»"


def test_lineas_previo_por_version_en_orden():
    lineas = prueba_en_seco.lineas_previo(["Nota inventada " + COMPRA, ENCABEZADO + " " + COMPRA])
    assert lineas == [
        "    versión 1 de 2 (text/plain): estado citado",
        "      previo (15 caracteres) «Nota inventada »",
        "      clave  (13 caracteres) «notainventada»",
        "    versión 2 de 2 (HTML): estado valido",
        "      previo (44 caracteres) «¡Listo! Todo salió bien con tus movimientos »",
        "      clave  (35 caracteres) «listotodosaliobiencontusmovimientos»",
    ]
    lineas_una = prueba_en_seco.lineas_previo(["Nota inventada " + COMPRA])
    assert lineas_una[0] == "    versión 1 de 1 (text/plain o HTML: el correo trae una sola): estado citado"


def test_fixture_preencabezado_oculto():
    """Correo multipart inventado con un preencabezado oculto en el HTML."""
    correo = _fixture()
    lineas = prueba_en_seco.lineas_previo(correo.textos)
    salida = "\n".join(lineas)
    assert lineas[0] == "    versión 1 de 2 (text/plain): estado citado"
    assert lineas[1] == (
        "      previo (89 caracteres) «Resumen inventado para [correo], codigo ####\\u3164 "
        "Listo! Todo salio bien con tus movimientos »"
    )
    assert lineas[3] == "    versión 2 de 2 (HTML): estado citado"
    assert lineas[4].startswith("      previo (344 caracteres, recortado a 300: los primeros y los últimos 150) "
                                "«Tu resumen inventado [correo] \\u2800\\u3164 ")
    assert lineas[4].endswith("¡Listo! Todo salió bien con tus movimientos »")
    assert lineas[5] == "      clave  (53 caracteres) «turesumeninventadolistotodosaliobiencontusmovimientos»"
    assert "Titulo inventado" not in salida  # <title> y <style> no llegan al texto
    _sin_aviso(salida)
    assert "persona.ejemplo" not in salida


# --- Comando completo -----------------------------------------------------------


@pytest.fixture
def ruta_db(tmp_path):
    return str(tmp_path / "seco.db")


@pytest.fixture
def entorno(monkeypatch, ruta_db):
    from finanzas.seguridad import generar_hash

    monkeypatch.setenv("APP_PASSWORD_HASH", generar_hash("clave-de-prueba-inventada"))
    monkeypatch.setenv("SESSION_SECRET", "secreto-de-prueba-inventado-de-mas-de-32-caracteres")
    monkeypatch.setenv("DB_PATH", ruta_db)
    monkeypatch.setenv("GMAIL_TOKEN", "/ruta/inventada/token.json")
    monkeypatch.delenv("GMAIL_REMITENTE", raising=False)


@pytest.fixture
def base(ruta_db):
    """Base con dos movimientos de Gmail leídos con el lector de entonces."""
    conn = db.conectar(ruta_db)
    db.inicializar(conn)
    with db.transaccion(conn):
        sql(conn, "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, ?, ?)",
            (100000000, "2026-08-01"))
    correos = {
        "m-uno": _correo("m-uno", ENCABEZADO + " " + COMPRA + DESPUES),
        "m-dos": _correo("m-dos", COMPRA + DESPUES, dia=14),
    }
    assert sincronizar(conn, ClienteFalso(correos)) == ResultadoSincronizacion(nuevos=2)
    conn.close()
    return correos


def _gmail_de_hoy():
    """Hoy Gmail "devuelve" el primero con un preencabezado oculto delante (el
    fixture) y el segundo igual que antes."""
    return {"m-uno": _fixture(), "m-dos": _correo("m-dos", COMPRA + DESPUES, dia=14)}


def test_comando_con_mostrar_previo(base, ruta_db, entorno, capsys):
    codigo = prueba_en_seco.main(["--mostrar-previo"], fabrica_cliente=lambda config: ClienteFalso(_gmail_de_hoy()))
    assert codigo == 0
    captura = capsys.readouterr()
    salida = captura.out + captura.err
    assert "movimiento guardado (2): aviso válido 1, citado 1," in salida
    assert "Con --mostrar-previo: texto delante del aviso" in salida
    lineas = captura.out.splitlines()
    i = lineas.index("  2026-08-29 02:53  movimiento guardado -> citado")
    assert lineas[i + 1] == "    versión 1 de 2 (text/plain): estado citado"
    assert lineas[i + 4] == "    versión 2 de 2 (HTML): estado citado"
    assert len(lineas) == i + 7  # solo el correo citado lleva diagnóstico
    _sin_aviso(salida)
    assert "persona.ejemplo" not in salida


def test_sin_la_opcion_la_salida_no_cambia(base, ruta_db, entorno, capsys):
    prueba_en_seco.main([], fabrica_cliente=lambda config: ClienteFalso(_gmail_de_hoy()))
    salida = capsys.readouterr().out
    assert salida.splitlines() == [
        "Prueba en seco del lector (no se escribió nada). Correos revisados: 2.",
        "- movimiento guardado (2): aviso válido 1, citado 1, no reconocido 0, "
        "rechazado por remitente o autenticación 0, error al descargar 0",
        "Correos que no quedarían como aviso válido (fecha del correo, de dónde venía -> resultado):",
        "  2026-08-29 02:53  movimiento guardado -> citado",
    ]


def test_revisar_sin_opcion_no_guarda_previos(base, ruta_db):
    ids = prueba_en_seco.ids_a_revisar(ruta_db, False)
    assert prueba_en_seco.revisar(ids, ClienteFalso(_gmail_de_hoy())).previos == {}
    con = prueba_en_seco.revisar(ids, ClienteFalso(_gmail_de_hoy()), mostrar_previo=True)
    assert list(con.previos) == [0] and len(con.detalle) == 1


def test_rechazados_no_muestran_previo(base, ruta_db):
    falso = CorreoGmail(
        "m-uno", datetime(2026, 8, 12, 9, 30, tzinfo=ZONA_COLOMBIA), "Asunto inventado",
        "Nota inventada " + COMPRA, remitente="alertas@banco-inventado.example", autenticacion="",
    )
    ids = [("m-uno", prueba_en_seco.GRUPO_MOVIMIENTOS)]
    resultado = prueba_en_seco.revisar(ids, ClienteFalso({"m-uno": falso}), mostrar_previo=True)
    assert resultado.detalle[0][2] == prueba_en_seco.RESULTADO_RECHAZADO
    assert resultado.previos == {}


def test_guia_documenta_la_receta_sin_escritura():
    guia = (Path(__file__).resolve().parents[3] / "deploy" / "GUIA.md").read_text(encoding="utf-8")
    inicio = guia.index("**Ver qué hay delante del aviso (`--mostrar-previo`")
    seccion = guia[inicio: guia.index("**Qué hace `finanzas-migrar`**", inicio)]
    assert "tápalo" in seccion.lower() or "tapa lo" in seccion.lower()
    receta = seccion[seccion.index("```bash"): seccion.index("```", seccion.index("```bash") + 3)]
    for parte in (
        "worktree add --detach /opt/finanzas-prueba", "-p User=finanzas", "-p ReadOnlyPaths=/var/lib/finanzas",
        "-p ProtectSystem=strict", "-p NoNewPrivileges=true", "-p WorkingDirectory=/opt/finanzas-prueba",
        "--incluir-no-reconocidos --mostrar-previo", "worktree remove --force /opt/finanzas-prueba",
    ):
        assert parte in receta, parte
    assert "ReadWritePaths" not in receta and "systemctl stop" not in receta
