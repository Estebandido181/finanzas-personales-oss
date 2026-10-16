"""Pruebas del análisis estricto de ``Authentication-Results`` (RFC 8601) y
del aviso REAL de Bancolombia (estructura exacta de Gmail, datos anonimizados).

Todo es inventado: el aviso, el correo del dueño (``dueno.ejemplo``), el número
del rebote, la IP de documentación 192.0.2.x y las firmas ``header.b``.
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path

import pytest

from finanzas import db
from finanzas.gmail import (
    CorreoGmail,
    analizar_authentication_results,
    autenticacion_valida,
    correo_desde_mensaje,
    motivo_autenticacion_invalida,
)
from finanzas.sincronizacion import ResultadoSincronizacion, sincronizar
from tests.soporte.gmail_falso import REMITENTE_OFICIAL, ClienteFalso
from tests.soporte.ayudas_db import sql

FIXTURE_REAL = (
    Path(__file__).resolve().parents[2] / "fixtures" / "gmail" / "autenticacion" / "legitimo_aviso_real_anonimizado.json"
)
MENSAJE_REAL = json.loads(FIXTURE_REAL.read_text(encoding="utf-8"))
AR_REAL = next(h["value"] for h in MENSAJE_REAL["payload"]["headers"] if h["name"] == "Authentication-Results")
B = "notificacionesbancolombia.com"

# Piezas del encabezado real, para armar variantes.
DKIM_BANCO = f"dkim=pass header.i=@an.{B} header.s=sctrans header.b=AbCdEf12"
DKIM_SENDCLEAN = "dkim=pass header.i=@sendclean.co.in header.s=s1 header.b=GhIjKl34"
SPF_REAL = (
    f"spf=pass (google.com: domain of b-000000001-dueno.ejemplo=gmail.com@trans.an.{B} designates "
    f'192.0.2.85 as permitted sender) smtp.mailfrom="b-000000001-dueno.ejemplo=gmail.com@trans.an.{B}"'
)
DMARC_REAL = f"dmarc=pass (p=REJECT sp=REJECT dis=NONE) header.from={B}"


def _ar(*resultados: str, servidor: str = "mx.google.com") -> str:
    return servidor + ";\r\n       " + ";\r\n       ".join(resultados)


def _correo(autenticacion: str) -> CorreoGmail:
    return CorreoGmail("x", None, "", "", remitente=REMITENTE_OFICIAL, autenticacion=autenticacion)


def _analizar(valor: str):
    return analizar_authentication_results(valor)


# --- El aviso real -------------------------------------------------------------------------

def test_el_encabezado_real_se_reconstruye_igual_en_las_pruebas():
    assert AR_REAL == _ar(DKIM_BANCO, DKIM_SENDCLEAN, SPF_REAL, DMARC_REAL)


def test_autenticacion_real_es_valida():
    assert autenticacion_valida(_correo(AR_REAL), REMITENTE_OFICIAL) is True
    assert motivo_autenticacion_invalida(_correo(AR_REAL), REMITENTE_OFICIAL) is None


def test_analisis_del_encabezado_real():
    analisis = _analizar(AR_REAL)
    assert analisis is not None and analisis.servidor == "mx.google.com"
    assert [(r.metodo, r.resultado) for r in analisis.resultados] == [
        ("dkim", "pass"), ("dkim", "pass"), ("spf", "pass"), ("dmarc", "pass")
    ]
    dkim = analisis.resultados[0].propiedades
    assert [(p.tipo, p.nombre, p.dominio) for p in dkim] == [
        ("header", "i", f"an.{B}"), ("header", "s", None), ("header", "b", None)
    ]
    # El MAIL FROM va entre comillas COMPLETO (su parte local lleva "="):
    # es una cadena y no aporta dominio (SPF no cuenta de todos modos).
    mailfrom = analisis.resultados[2].propiedades[0]
    assert (mailfrom.tipo, mailfrom.nombre) == ("smtp", "mailfrom")
    assert mailfrom.valor == f"b-000000001-dueno.ejemplo=gmail.com@trans.an.{B}"
    assert mailfrom.dominio is None
    assert analisis.resultados[3].propiedades[0].dominio == B


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "estricta.db"))
    db.inicializar(conexion)
    with db.transaccion(conexion):
        sql(
            conexion,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, 0, '2026-08-01')"
        )
    yield conexion
    conexion.close()


def _sincronizar(conn, mensaje: dict) -> ResultadoSincronizacion:
    correo = correo_desde_mensaje(mensaje)
    return sincronizar(conn, ClienteFalso({correo.gmail_id: correo}), REMITENTE_OFICIAL)


# --- D15: DMARC obligatorio con los avisos reales anonimizados ------------------------------

_AUTENTICACION = Path(__file__).resolve().parents[2] / "fixtures" / "gmail" / "autenticacion"


@pytest.mark.parametrize(
    "fixture", ["legitimo_aviso_real_anonimizado.json", "legitimo_recibiste_real_anonimizado.json"]
)
def test_d15_avisos_reales_con_dmarc_pass_crean_su_movimiento(conn, fixture):
    mensaje = json.loads((_AUTENTICACION / fixture).read_text(encoding="utf-8"))
    assert _sincronizar(conn, mensaje) == ResultadoSincronizacion(nuevos=1)
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 1


@pytest.mark.parametrize(
    "fixture", ["legitimo_aviso_real_anonimizado.json", "legitimo_recibiste_real_anonimizado.json"]
)
def test_d15_avisos_reales_sin_su_dmarc_se_rechazan(conn, fixture, caplog):
    """El mismo aviso real con sus dkim=pass y spf=pass alineados, pero sin el
    resultado dmarc, ya no crea movimiento (D15)."""
    mensaje = json.loads((_AUTENTICACION / fixture).read_text(encoding="utf-8"))
    for encabezado in mensaje["payload"]["headers"]:
        if encabezado["name"] == "Authentication-Results":
            assert encabezado["value"].endswith(";\r\n       " + DMARC_REAL)
            encabezado["value"] = encabezado["value"].removesuffix(";\r\n       " + DMARC_REAL)
    with caplog.at_level(logging.DEBUG):
        assert _sincronizar(conn, mensaje) == ResultadoSincronizacion(rechazados_autenticacion=1)
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 0
    assert "motivo=sin_pass_alineado" in caplog.text


def test_aviso_real_crea_exactamente_un_movimiento(conn):
    assert _sincronizar(conn, MENSAJE_REAL) == ResultadoSincronizacion(nuevos=1)
    filas = [dict(f) for f in sql(conn, "SELECT * FROM movimientos")]
    assert len(filas) == 1
    movimiento = filas[0]
    assert movimiento["gmail_id"] == "real-0001"
    assert movimiento["origen"] == "gmail"
    assert movimiento["tipo"] == "compra"
    assert movimiento["monto_centavos"] == 8735000
    assert movimiento["descripcion"] == "SUPERMERCADO EJEMPLO"
    assert movimiento["fecha_hora"] == "2026-08-12T19:05:00"
    assert sql(conn, "SELECT COUNT(*) FROM correos_no_reconocidos").fetchone()[0] == 0


# --- Variantes del real que NO deben crear movimiento --------------------------------------

def _variante(from_: str | None = None, resultados: list[str] | None = None) -> dict:
    """El mensaje real con otro From y/o otros ``Authentication-Results``
    (``resultados`` en orden, en la posición del original; ``[]`` = ninguno).
    El ``ARC-Authentication-Results`` real se conserva siempre."""
    mensaje = copy.deepcopy(MENSAJE_REAL)
    encabezados = []
    for h in mensaje["payload"]["headers"]:
        if h["name"] == "Authentication-Results" and resultados is not None:
            encabezados += [{"name": "Authentication-Results", "value": v} for v in resultados]
        elif h["name"] == "From" and from_ is not None:
            encabezados.append({"name": "From", "value": from_})
        else:
            encabezados.append(h)
    mensaje["payload"]["headers"] = encabezados
    return mensaje


# Inyecciones del tester (valores que controla el atacante).
INYECCIONES = {
    "helo_dkim": (
        "mx.google.com; spf=pass (google.com: domain of postmaster@x designates 198.51.100.66 as permitted sender) "
        f"smtp.helo=x;dkim=pass,header.d={B}; dmarc=fail (p=NONE) header.from={B}"
    ),
    "helo_dmarc": f"mx.google.com; spf=pass smtp.helo=x;dmarc=pass,header.from={B}; dmarc=fail header.from={B}",
    "selector_header_d": f"mx.google.com; dkim=pass header.i=@evil.example header.s=header.d={B} header.b=AbCd",
    "selector_punto_header_d": f"mx.google.com; dkim=pass header.i=@evil.example header.s=s1.header.d={B} header.b=AbCd",
    "comentario_sin_cerrar": f"mx.google.com; dkim=fail (x; dkim=pass header.d={B} header.i=@{B}",
    "parentesis_cierre_extra": f"mx.google.com; dkim=fail (a) b) ; dkim=pass header.d={B}",
    "propiedad_con_prefijo": f"mx.google.com; dkim=pass policy.header.d={B} header.d=evil.example",
}

VARIANTES = {
    "from_otra_direccion": (
        _variante(from_="Alertas y Notificaciones <alertasynotificaciones@notificaciones-bancolombia.example>"),
        "remitente",
    ),
    "from_nombre_visible_enganoso": (
        _variante(from_=f'"alertasynotificaciones@an.{B}" <alertas@evil.example>'),
        "remitente",
    ),
    "dmarc_y_dkim_fail": (
        _variante(resultados=[_ar(
            DKIM_BANCO.replace("pass", "fail"), DKIM_SENDCLEAN.replace("pass", "fail"), SPF_REAL,
            DMARC_REAL.replace("pass", "fail"),
        )]),
        "sin_pass_alineado",
    ),
    "solo_dkim_no_alineado_sin_dmarc": (
        _variante(resultados=[_ar(DKIM_SENDCLEAN, SPF_REAL)]),
        "sin_pass_alineado",
    ),
    "solo_spf": (_variante(resultados=[_ar(SPF_REAL)]), "sin_pass_alineado"),
    # Sin Authentication-Results: el ARC-Authentication-Results (con "pass") no cuenta.
    "sin_encabezado": (_variante(resultados=[]), "encabezado_invalido"),
    "otro_servidor_primero": (
        _variante(resultados=[_ar(DKIM_BANCO, DMARC_REAL, servidor="mx.evil.example"), AR_REAL]),
        "encabezado_invalido",
    ),
    **{
        f"inyeccion_{nombre}": (_variante(resultados=[valor]), "encabezado_invalido")
        for nombre, valor in INYECCIONES.items()
    },
}


@pytest.mark.parametrize("caso", list(VARIANTES))
def test_variante_del_real_queda_no_reconocida(conn, caso, caplog):
    mensaje, motivo = VARIANTES[caso]
    with caplog.at_level(logging.DEBUG):
        resultado = _sincronizar(conn, mensaje)

    assert resultado == ResultadoSincronizacion(rechazados_autenticacion=1)
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 0
    filas = [dict(f) for f in sql(conn, "SELECT * FROM correos_no_reconocidos")]
    assert filas == [{"gmail_id": "real-0001", "fecha": "2026-08-12T19:05:40", "asunto": "Alertas y Notificaciones"}]
    # El log trae la categoría genérica, nunca valores del encabezado ni del correo.
    assert f"(motivo={motivo})" in caplog.text
    for dato in ("evil", "sendclean", "dueno", "notificacionesbancolombia", "dkim", "spf", "dmarc",
                 "SUPERMERCADO", "87.350", "192.0.2"):
        assert dato not in caplog.text, dato


@pytest.mark.parametrize("valor", list(INYECCIONES.values()), ids=list(INYECCIONES))
def test_inyecciones_del_tester_invalidan_todo_el_encabezado(valor):
    assert _analizar(valor) is None
    assert autenticacion_valida(_correo(valor), REMITENTE_OFICIAL) is False


def test_policy_d_no_cuenta_como_header_d():
    """Bien formada, ``policy.d`` se analiza, pero su ptype es ``policy``."""
    valor = f"mx.google.com; dkim=pass policy.d={B} header.d=evil.example"
    analisis = _analizar(valor)
    assert analisis is not None
    assert [(p.tipo, p.nombre) for p in analisis.resultados[0].propiedades] == [("policy", "d"), ("header", "d")]
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) == "sin_pass_alineado"
    # D15: con dkim el rechazo ya no prueba nada (falta el dmarc). Lo mismo en
    # un dmarc=pass: policy.from del banco no es header.from.
    valor = f"mx.google.com; dmarc=pass policy.from={B} header.from=evil.example"
    assert [(p.tipo, p.nombre) for p in _analizar(valor).resultados[0].propiedades] == [
        ("policy", "from"), ("header", "from")]
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) == "sin_pass_alineado"


# --- Analizador: gramática -----------------------------------------------------------------

def test_comentarios_anidados_y_con_escape_se_descartan():
    valor = f"mx.google.com; dkim=pass (a (b; dkim=fail header.d=evil.example) c \\) d) header.d={B}"
    analisis = _analizar(valor)
    assert analisis is not None and len(analisis.resultados) == 1
    assert [(p.nombre, p.dominio) for p in analisis.resultados[0].propiedades] == [("d", B)]


def test_comentarios_reales_con_arroba_igual_y_dos_puntos():
    valor = f"mx.google.com; spf=pass (google.com: domain of a=b@{B} designates 192.0.2.1) smtp.mailfrom={B}"
    assert _analizar(valor) is not None


def test_comillas_con_escapes():
    valor = r'mx.google.com; dkim=pass header.i="a\"b\\c;dkim=pass header.d=x"@evil.example'
    propiedad = _analizar(valor).resultados[0].propiedades[0]
    assert propiedad.dominio == "evil.example"
    # El valor queda sin comillas ni escapes.
    assert propiedad.valor == 'a"b\\c;dkim=pass header.d=x@evil.example'


def test_dominio_tras_la_arroba_que_cierra_la_parte_local_entre_comillas():
    valor = f'mx.google.com; dkim=pass header.i="x@{B}"@evil.com'
    assert _analizar(valor).resultados[0].propiedades[0].dominio == "evil.com"
    assert autenticacion_valida(_correo(valor), REMITENTE_OFICIAL) is False
    # D15: el mismo truco en el header.from de un dmarc=pass (el que decide).
    valor = f'mx.google.com; dmarc=pass header.from="x@{B}"@evil.com'
    assert _analizar(valor).resultados[0].propiedades[0].dominio == "evil.com"
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) == "sin_pass_alineado"


def test_cadena_suelta_no_aporta_dominio():
    valor = f'mx.google.com; dkim=pass header.d="{B}"'
    assert _analizar(valor).resultados[0].propiedades[0].dominio is None
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) == "sin_pass_alineado"
    # D15: el mismo caso en el header.from de un dmarc=pass (el que decide).
    valor = f'mx.google.com; dmarc=pass header.from="{B}"'
    assert _analizar(valor).resultados[0].propiedades[0].dominio is None
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) == "sin_pass_alineado"


def test_reason():
    valor = f'mx.google.com; dkim=fail reason="firma invalida" header.d={B}; dmarc=pass reason=ok header.from={B}'
    analisis = _analizar(valor)
    assert [r.razon for r in analisis.resultados] == ["firma invalida", "ok"]
    assert autenticacion_valida(_correo(valor), REMITENTE_OFICIAL)


def test_metodo_con_version_y_servidor_con_version():
    analisis = _analizar(f"mx.google.com 1; dkim/1=pass header.d={B}")
    assert analisis.version == "1"
    assert (analisis.resultados[0].metodo, analisis.resultados[0].version) == ("dkim", "1")
    # D15: dkim solo ya no basta; la versión se prueba ahora también en dmarc.
    assert not autenticacion_valida(_correo(f"mx.google.com; dkim/1=pass header.d={B}"), REMITENTE_OFICIAL)
    assert autenticacion_valida(
        _correo(f"mx.google.com 1; dkim/1=pass header.d={B}; dmarc/1=pass header.from={B}"), REMITENTE_OFICIAL
    )


def test_none_sin_resultados():
    analisis = _analizar("mx.google.com; none")
    assert analisis is not None and analisis.resultados == ()
    assert motivo_autenticacion_invalida(_correo("mx.google.com; none"), REMITENTE_OFICIAL) == "sin_pass_alineado"


def test_mayusculas():
    valor = f"MX.Google.COM; DKIM=PASS HEADER.D={B.upper()}; DMARC=Pass Header.From={B}"
    analisis = _analizar(valor)
    assert [(r.metodo, r.resultado) for r in analisis.resultados] == [("dkim", "pass"), ("dmarc", "pass")]
    assert analisis.resultados[0].propiedades[0].dominio == B
    assert autenticacion_valida(_correo(valor), REMITENTE_OFICIAL)


@pytest.mark.parametrize("salto", ["\r\n ", "\r\n\t", "\n  ", "\n\t"])
def test_saltos_de_linea_plegados(salto):
    valor = f"mx.google.com;{salto}dkim=pass{salto}header.d={B};{salto}dmarc=pass header.from={B}"
    assert autenticacion_valida(_correo(valor), REMITENTE_OFICIAL)


def test_base64_en_header_b():
    analisis = _analizar(f"mx.google.com; dkim=pass header.d={B} header.b=Ab+/Cd==")
    assert analisis.resultados[0].propiedades[1].valor == "Ab+/Cd=="


@pytest.mark.parametrize(
    "valor",
    [
        # Comillas y paréntesis sin cerrar.
        f'mx.google.com; dkim=pass header.d={B}; spf=pass smtp.mailfrom="x@evil.example',
        f"mx.google.com; dkim=pass header.d={B} (comentario",
        f"mx.google.com; dkim=pass header.d={B})",
        f"mx.google.com; dkim=pass header.d={B} (a \\",
        # Caracteres de control, también dentro de comentarios y comillas.
        f"mx.google.com; dkim=pass header.d={B}\x00",
        f"mx.google.com; dkim=pass\x0bheader.d={B}",
        f"mx.google.com; dkim=pass (a\x07) header.d={B}",
        f'mx.google.com; dkim=pass header.d={B} header.s="a\x1bb"',
        f"mx.google.com; dkim=pass header.d={B}\x7f",
        # Saltos de línea sin plegar.
        f"mx.google.com;\r\ndkim=pass header.d={B}",
        f"mx.google.com;\ndkim=pass header.d={B}",
        f"mx.google.com;\rdkim=pass header.d={B}",
        f"mx.google.com; dkim=pass header.d={B}\r\n",
        # Estructura.
        "",
        "mx.google.com",
        f"mx.google.com; dkim=pass header.d={B};",
        f"mx.google.com;; dkim=pass header.d={B}",
        f"mx.google.com; none; dkim=pass header.d={B}",
        f"dkim=pass header.d={B}",
        f"mx.google.com.evil.example; dkim=pass header.d={B}",
        f'"mx.google.com"; dkim=pass header.d={B}',
        f"mx . google . com; dkim=pass header.d={B}",
        f"mx.google.com x; dkim=pass header.d={B}",
        # Resultado fuera de la lista cerrada.
        f"mx.google.com; dkim=passed header.d={B}",
        f"mx.google.com; dkim=ok header.d={B}",
        f"mx.google.com; dkim= header.d={B}",
        f"mx.google.com; dkim header.d={B}",
        # Método o versión inválidos.
        f"mx.google.com; dkim/x=pass header.d={B}",
        f"mx.google.com; _dkim=pass header.d={B}",
        # Propiedades inválidas.
        f"mx.google.com; dkim=pass foo.d={B}",
        f"mx.google.com; dkim=pass header.d",
        f"mx.google.com; dkim=pass header.d=",
        f"mx.google.com; dkim=pass header={B}",
        f"mx.google.com; dkim=pass,header.d={B}",
        f"mx.google.com; dkim=pass header.d={B},evil.example",
        f"mx.google.com; dkim=pass header.s=a=b header.d={B}",
        f"mx.google.com; dkim=pass header.d={B}@",
        f"mx.google.com; dkim=pass header.i=@{B}@evil.example",
        f"mx.google.com; dkim=pass header.i= @ {B}",
        f"mx.google.com; dkim=pass header.i=@com",
        f"mx.google.com; dkim=pass header.i=@-{B}",
        f'mx.google.com; dkim=pass header.d={B}"x"',
        f"mx.google.com; dkim=pass header.i=x\\@{B}",
        f"mx.google.com; dkim=pass header.b=Ab.Cd header.d={B}",
        f"mx.google.com; spf=pass smtp.mailfrom=a=b@{B}",
        # Caracteres fuera de la gramática (fuera de comentarios y comillas).
        f"mx.google.com; dkim=pass header.d=notificacionesbancolombiа.com",
        f"mx.google.com; dkim=pass header.d={B} header.s=<x>",
        f"mx.google.com; dkim=pass header.d={B}: x",
    ],
)
def test_fuera_de_la_gramatica_da_none(valor):
    assert _analizar(valor) is None
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) == "encabezado_invalido"


def test_no_ascii_permitido_dentro_de_comentarios():
    assert _analizar(f"mx.google.com; dkim=pass (firma válida ✓) header.d={B}") is not None


# --- Reglas semánticas (ronda 1 del revisor) ------------------------------------------------
#
# Gmail copia el MAIL FROM dentro del comentario del SPF y ahí las comillas no
# protegen: un ")" en la parte local cierra el comentario antes de tiempo y lo
# que sigue se lee como resultados.

_LOCAL_DMARC = f'"a) ; dmarc=pass header.from=an.{B} ; spf=pass (b"'
_LOCAL_DKIM = f'"a) ; dkim=pass header.d={B}; x=none (z"'


def _mailfrom_en_comentario(local: str, dominio: str, entre_comillas: bool, dmarc: str) -> str:
    """Como lo escribe Gmail: el MAIL FROM tal cual en el comentario y, en
    ``smtp.mailfrom``, tal cual o con todo el valor entre comillas (con escapes)."""
    direccion = f"{local}@{dominio}"
    valor = '"' + direccion.replace("\\", "\\\\").replace('"', '\\"') + '"' if entre_comillas else direccion
    return (
        f"mx.google.com; spf=pass (google.com: domain of {direccion} designates 198.51.100.66 as "
        f"permitted sender) smtp.mailfrom={valor}; {dmarc}"
    )


PAYLOADS_REVISOR = {
    f"{nombre}_{forma}": _mailfrom_en_comentario(
        local.strip('"') if forma == "local_sin_comillas" else local, dominio, forma != "local_entre_comillas", dmarc
    )
    for nombre, local, dominio, dmarc in (
        ("dmarc_fabricado", _LOCAL_DMARC, "evil.com", "dmarc=fail (p=NONE sp=NONE dis=NONE) header.from=evil.com"),
        ("dkim_fabricado", _LOCAL_DKIM, "evil.example", f"dmarc=fail (p=NONE sp=NONE dis=NONE) header.from={B}"),
    )
    for forma in ("local_entre_comillas", "valor_entre_comillas", "local_sin_comillas")
}
# Los mismos sin el dmarc final (así el dmarc/dkim fabricado sería el decisivo).
PAYLOADS_REVISOR.update({
    f"{nombre}_sin_dmarc": valor.rsplit("; dmarc=", 1)[0]
    for nombre, valor in list(PAYLOADS_REVISOR.items())
})

_LOCAL_TESTER = f'"a) ; dkim=pass header.d={B}; x=none (z"'
_ESC_TESTER = _LOCAL_TESTER.replace('"', '\\"')
CASOS_TESTER = {
    "parentesis_en_local_tal_cual": (
        f"mx.google.com; spf=pass (google.com: domain of {_LOCAL_TESTER}@evil.example designates 198.51.100.66 "
        f"as permitted sender) smtp.mailfrom={_LOCAL_TESTER}@evil.example; "
        f"dmarc=fail (p=NONE sp=NONE dis=NONE) header.from={B}"
    ),
    "parentesis_en_local_escapado": (
        f"mx.google.com; spf=pass (google.com: domain of {_LOCAL_TESTER}@evil.example designates 198.51.100.66 "
        f'as permitted sender) smtp.mailfrom="{_ESC_TESTER}@evil.example"; '
        f"dmarc=fail (p=NONE sp=NONE dis=NONE) header.from={B}"
    ),
    "parentesis_en_local_p_reject": (
        f"mx.google.com; spf=pass (google.com: domain of {_LOCAL_TESTER}@evil.example designates 198.51.100.66 "
        f"as permitted sender) smtp.mailfrom={_LOCAL_TESTER}@evil.example; "
        f"dmarc=fail (p=REJECT sp=REJECT dis=NONE) header.from={B}"
    ),
    "barra_doble_cola_valida": (
        f'mx.google.com; spf=pass smtp.mailfrom="a\\\\";dkim=pass header.d={B}; '
        f'dmarc=none header.from=""@evil.example; dmarc=fail header.from={B}'
    ),
    "dmarc_dos_header_from": f"mx.google.com; dmarc=pass header.from=evil.example header.from={B}",
}


@pytest.mark.parametrize("valor", list(PAYLOADS_REVISOR.values()), ids=list(PAYLOADS_REVISOR))
def test_parentesis_en_el_mailfrom_no_fabrica_un_pass(valor):
    assert autenticacion_valida(_correo(valor), REMITENTE_OFICIAL) is False
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) == "encabezado_invalido"


@pytest.mark.parametrize("valor", list(CASOS_TESTER.values()), ids=list(CASOS_TESTER))
def test_casos_del_tester_contra_el_analizador_estricto(valor):
    assert autenticacion_valida(_correo(valor), REMITENTE_OFICIAL) is False


@pytest.mark.parametrize("caso", ["dmarc_fabricado_local_entre_comillas", "dkim_fabricado_valor_entre_comillas",
                                  "dmarc_fabricado_local_sin_comillas_sin_dmarc"])
def test_parentesis_en_el_mailfrom_en_sincronizacion_completa(conn, caso):
    assert _sincronizar(conn, _variante(resultados=[PAYLOADS_REVISOR[caso]])) == (
        ResultadoSincronizacion(rechazados_autenticacion=1)
    )
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 0


@pytest.mark.parametrize(
    "valor",
    [
        # Dos dmarc: ambiguo.
        f"mx.google.com; dkim=pass header.d={B}; dmarc=pass header.from={B}; dmarc=pass header.from={B}",
        f"mx.google.com; dmarc=fail header.from={B}; dmarc=pass header.from={B}",
        # header.from repetido en el dmarc.
        f"mx.google.com; dmarc=pass header.from={B} header.from={B}",
        # Método desconocido.
        f"mx.google.com; dkim=pass header.d={B}; x=none",
        f"mx.google.com; dkim=pass header.d={B}; foo=pass header.d={B}",
        # spf sin smtp.*
        f"mx.google.com; spf=pass; dkim=pass header.d={B}",
        f"mx.google.com; spf=pass header.from={B}; dkim=pass header.d={B}",
        # smtp.* con caracteres fuera de [A-Za-z0-9.=_+@-].
        f'mx.google.com; spf=pass smtp.mailfrom="a b@evil.example"; dkim=pass header.d={B}',
        f'mx.google.com; spf=pass smtp.mailfrom="a)b"@evil.example; dkim=pass header.d={B}',
        f'mx.google.com; spf=pass smtp.mailfrom="a(b@evil.example"; dkim=pass header.d={B}',
        f'mx.google.com; spf=pass smtp.mailfrom="a;b"@evil.example; dkim=pass header.d={B}',
        f'mx.google.com; spf=pass smtp.mailfrom="a\\"b"@evil.example; dkim=pass header.d={B}',
        f'mx.google.com; spf=pass smtp.mailfrom="a\\\\b"@evil.example; dkim=pass header.d={B}',
        f'mx.google.com; spf=pass smtp.mailfrom=""; dkim=pass header.d={B}',
        f'mx.google.com; spf=pass smtp.helo="mx (x)"; dkim=pass header.d={B}',
    ],
    ids=["dos_dmarc", "dmarc_fail_y_pass", "header_from_repetido", "metodo_x", "metodo_foo",
         "spf_sin_propiedades", "spf_sin_smtp", "mailfrom_espacio", "mailfrom_parentesis_cierre",
         "mailfrom_parentesis_apertura", "mailfrom_punto_y_coma", "mailfrom_comilla", "mailfrom_barra",
         "mailfrom_vacio", "helo_con_parentesis"],
)
def test_reglas_semanticas_invalidan_el_encabezado(valor):
    assert _analizar(valor) is None
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) == "encabezado_invalido"


def test_dmarc_fail_es_decisivo_aunque_haya_dkim_alineado():
    valor = f"mx.google.com; dkim=pass header.d={B}; spf=pass smtp.mailfrom=x@{B}; dmarc=fail header.from={B}"
    assert _analizar(valor) is not None
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) == "sin_pass_alineado"


def test_dmarc_pass_no_alineado_se_rechaza_aunque_haya_dkim_alineado():
    valor = f"mx.google.com; dkim=pass header.d={B}; dmarc=pass header.from=evil.example"
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) == "sin_pass_alineado"


def test_sin_dmarc_no_basta_dkim_alineado():
    # D15 (antes test_sin_dmarc_basta_dkim_alineado): DMARC es obligatorio; un
    # dkim=pass alineado sin dmarc ya no basta.
    valor = f"mx.google.com; dkim=pass header.d={B}"
    assert _analizar(valor) is not None
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) == "sin_pass_alineado"


def test_spf_pass_alineado_solo_no_basta():
    # D15: SPF por sí solo nunca basta.
    valor = f"mx.google.com; spf=pass smtp.mailfrom=x@{B}"
    assert _analizar(valor) is not None
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) == "sin_pass_alineado"


def test_dmarc_pass_alineado_con_dkim_fail_se_acepta():
    valor = f"mx.google.com; dkim=fail header.d={B}; dmarc=pass header.from={B}"
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) is None


@pytest.mark.parametrize("metodo", sorted(
    {"dkim", "spf", "dmarc", "arc", "bimi", "iprev", "auth", "dkim-atps", "dkim-adsp",
     "sender-id", "rrvs", "vbr", "smime", "dnswl"} - {"spf", "dmarc"}
))
def test_metodos_conocidos_se_aceptan(metodo):
    assert _analizar(f"mx.google.com; {metodo}=none; dkim=pass header.d={B}") is not None


def test_mailfrom_real_cumple_el_juego_de_caracteres():
    valor = _analizar(AR_REAL).resultados[2].propiedades[0].valor
    assert valor == f"b-000000001-dueno.ejemplo=gmail.com@trans.an.{B}"
    assert _analizar(f"mx.google.com; spf=pass smtp.helo=mail-x.{B}; dkim=pass header.d={B}") is not None


# --- Ataques a D15: fabricar o colar un dmarc=pass alineado ---------------------------------
#
# Cada caso declara el motivo esperado. Con "encabezado_invalido" se exige además
# que el análisis devuelva None (el ataque es sintáctico o semántico y debe
# invalidar TODO el encabezado, no solo quedarse sin pass).

_DMARC_FAIL = f"dmarc=fail (p=REJECT sp=REJECT dis=NONE) header.from={B}"
_DMARC_PASS = f"dmarc=pass (p=REJECT sp=REJECT dis=NONE) header.from={B}"

ATAQUES_D15 = {
    # Dos dmarc, uno pass y otro fail, en ambos órdenes y con variantes.
    "dos_dmarc_pass_fail": (f"mx.google.com; {DKIM_BANCO}; {_DMARC_PASS}; {_DMARC_FAIL}", "encabezado_invalido"),
    "dos_dmarc_fail_pass": (f"mx.google.com; {DKIM_BANCO}; {_DMARC_FAIL}; {_DMARC_PASS}", "encabezado_invalido"),
    "dos_dmarc_pass_pass": (f"mx.google.com; {_DMARC_PASS}; {_DMARC_PASS}", "encabezado_invalido"),
    "dos_dmarc_con_version": (f"mx.google.com; dmarc/1=pass header.from={B}; {_DMARC_FAIL}", "encabezado_invalido"),
    "dmarc_dos_header_from": (f"mx.google.com; dmarc=pass header.from=evil.example header.from={B}",
                              "encabezado_invalido"),
    # header.from de un dominio parecido.
    "from_sufijo_evil": (f"mx.google.com; dmarc=pass header.from={B}.evil.example", "sin_pass_alineado"),
    "from_prefijo_pegado": (f"mx.google.com; dmarc=pass header.from=x{B}", "sin_pass_alineado"),
    "from_con_guion": (f"mx.google.com; dmarc=pass header.from=evil-{B}", "sin_pass_alineado"),
    "from_otro_tld": ("mx.google.com; dmarc=pass header.from=notificacionesbancolombia.co", "sin_pass_alineado"),
    "from_sin_una_letra": ("mx.google.com; dmarc=pass header.from=notificacionesbancolombi.com",
                           "sin_pass_alineado"),
    "from_solo_tld": ("mx.google.com; dmarc=pass header.from=com", "sin_pass_alineado"),
    "from_cirilica": ("mx.google.com; dmarc=pass header.from=notificacionesbancolombi\u0430.com",
                      "encabezado_invalido"),
    "from_punycode": ("mx.google.com; dmarc=pass header.from=xn--notificacionesbancolombi-abc.com",
                      "sin_pass_alineado"),
    # dmarc=pass sin header.from (o con el dominio del banco en otra propiedad).
    "sin_header_from": ("mx.google.com; dmarc=pass (p=REJECT sp=REJECT dis=NONE)", "sin_pass_alineado"),
    "sin_header_from_con_dkim": (f"mx.google.com; {DKIM_BANCO}; dmarc=pass", "sin_pass_alineado"),
    "banco_en_header_d": (f"mx.google.com; dmarc=pass header.d={B}", "sin_pass_alineado"),
    "banco_en_smtp_mailfrom": (f"mx.google.com; dmarc=pass smtp.mailfrom=x@{B}", "sin_pass_alineado"),
    "banco_en_policy_from": (f"mx.google.com; dmarc=pass policy.from={B}", "sin_pass_alineado"),
    "banco_en_reason": (f'mx.google.com; dmarc=pass reason="header.from={B}" header.from=evil.example',
                        "sin_pass_alineado"),
    # dmarc=pass inyectado desde un comentario (bien cerrado: se descarta).
    "comentario_spf": (f"mx.google.com; spf=pass (dmarc=pass header.from={B}) smtp.mailfrom=x@evil.example; "
                       "dmarc=fail header.from=evil.example", "sin_pass_alineado"),
    "comentario_dkim": (f"mx.google.com; dkim=pass (x; dmarc=pass header.from={B}) header.d=evil.example",
                        "sin_pass_alineado"),
    "comentario_iprev": (f"mx.google.com; iprev=pass (dmarc=pass header.from={B}) policy.iprev=198.51.100.66",
                         "sin_pass_alineado"),
    "comentario_dmarc_fail": (f"mx.google.com; dmarc=fail (dmarc=pass header.from={B}) header.from={B}",
                              "sin_pass_alineado"),
    # dmarc=pass inyectado rompiendo un comentario (MAIL FROM con ")"), sin dmarc real detrás.
    # Solo el comentario del SPF lleva texto del remitente (su MAIL FROM); un ")"
    # en un comentario de dkim o iprev no lo controla el atacante.
    "comentario_spf_roto": (
        f"mx.google.com; spf=pass (google.com: domain of a) ; dmarc=pass header.from={B}; iprev=pass (z@evil.example "
        f'designates 198.51.100.66 as permitted sender) smtp.mailfrom="a) ; dmarc=pass header.from={B}; '
        f'iprev=pass (z@evil.example"', "encabezado_invalido"),
    "comentario_iprev_sin_cerrar": (f"mx.google.com; iprev=pass (x; dmarc=pass header.from={B}",
                                    "encabezado_invalido"),
    # Capitalización: duplicar con otra forma no cuela.
    "dmarc_mayusculas_mas_fail": (f"mx.google.com; DMARC=Pass header.from={B}; {_DMARC_FAIL}",
                                  "encabezado_invalido"),
    "dmarc_pass_mayusculas_no_alineado": ("mx.google.com; DMARC=PASS HEADER.FROM=EVIL.EXAMPLE", "sin_pass_alineado"),
    # Resultados que parecen pass y no lo son.
    "bestguesspass": (f"mx.google.com; dmarc=bestguesspass header.from={B}", "encabezado_invalido"),
    "best_guess_pass": (f"mx.google.com; dmarc=best-guess-pass header.from={B}", "encabezado_invalido"),
    "pass_con_sufijo": (f"mx.google.com; dmarc=pass1 header.from={B}", "encabezado_invalido"),
    "pass_entre_comillas": (f'mx.google.com; dmarc="pass" header.from={B}', "encabezado_invalido"),
    "pass_vacio": (f"mx.google.com; dmarc= header.from={B}", "encabezado_invalido"),
    "metodo_parecido": (f"mx.google.com; dmarc2=pass header.from={B}", "encabezado_invalido"),
    "metodo_arc_dmarc": (f"mx.google.com; arc=pass header.from={B}", "sin_pass_alineado"),
}


@pytest.mark.parametrize("valor, motivo", list(ATAQUES_D15.values()), ids=list(ATAQUES_D15))
def test_d15_ataques_no_fabrican_un_dmarc_pass(valor, motivo):
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) == motivo
    assert (_analizar(valor) is None) == (motivo == "encabezado_invalido")


@pytest.mark.parametrize(
    "valor",
    [
        f"mx.google.com; DMARC=Pass header.from={B}",
        f"mx.google.com; Dmarc=PASS Header.From={B.upper()}",
        f"MX.GOOGLE.COM; dMaRc=pAsS hEaDeR.fRoM=An.{B.title()}",
    ],
    ids=["DMARC_Pass", "Dmarc_PASS_dominio_mayusculas", "mezcla"],
)
def test_d15_dmarc_pass_con_otra_capitalizacion_se_acepta(valor):
    """RFC 8601: método, resultado, ptype y dominio no distinguen mayúsculas.
    Un solo dmarc=pass alineado con otra capitalización es legítimo."""
    assert motivo_autenticacion_invalida(_correo(valor), REMITENTE_OFICIAL) is None
