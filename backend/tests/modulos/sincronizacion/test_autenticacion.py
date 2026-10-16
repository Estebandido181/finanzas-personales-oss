"""Pruebas del control de remitente y autenticación (correos falsificados).

Todos los encabezados son inventados: dominios de ejemplo, selector ficticio e
IP de documentación 192.0.2.x.
"""

from __future__ import annotations
from finanzas.modulos.sincronizacion.adaptadores.avisos import evaluacion

import copy
import json
import logging
from pathlib import Path

import pytest

from finanzas import db, sincronizacion
from finanzas.gmail import (
    MOTIVO_ENCABEZADO_INVALIDO,
    MOTIVO_SIN_PASS_ALINEADO,
    CorreoGmail,
    autenticacion_valida,
    correo_desde_mensaje,
    direccion_remitente,
    dominio_alineado,
    motivo_autenticacion_invalida,
    remitente_valido,
)
from finanzas.sincronizacion import ResultadoSincronizacion, sincronizar
from tests.soporte.gmail_falso import AUTENTICACION_LEGITIMA, REMITENTE_OFICIAL, ClienteFalso
from tests.soporte.ayudas_db import sql

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "gmail" / "compraste_html.json"
DOMINIO = "notificacionesbancolombia.com"
FROM_OFICIAL = f"Bancolombia (ejemplo) <{REMITENTE_OFICIAL}>"


def _autenticacion(*resultados: str, servidor: str = "mx.google.com") -> str:
    return servidor + ";\r\n       " + ";\r\n       ".join(resultados)


def _correo(autenticacion: str | None = AUTENTICACION_LEGITIMA, remitente: str = REMITENTE_OFICIAL) -> CorreoGmail:
    return CorreoGmail("msg-a", None, "", "", remitente=remitente, autenticacion=autenticacion or "")


DKIM_OK = f"dkim=pass header.i=@{DOMINIO} header.s=selector-ejemplo header.b=AbCd"
SPF_OK = (
    f"spf=pass (google.com: domain of {REMITENTE_OFICIAL} designates 192.0.2.10 as permitted sender) "
    f"smtp.mailfrom={REMITENTE_OFICIAL}"
)
DMARC_OK = f"dmarc=pass (p=REJECT sp=REJECT dis=NONE) header.from={DOMINIO}"
DKIM_FAIL = f"dkim=fail header.i=@{DOMINIO} header.s=selector-ejemplo header.b=AbCd"
SPF_FAIL = f"spf=fail (google.com: domain of {REMITENTE_OFICIAL} does not designate 192.0.2.66) smtp.mailfrom={REMITENTE_OFICIAL}"
DMARC_FAIL = f"dmarc=fail (p=REJECT sp=REJECT dis=QUARANTINE) header.from={DOMINIO}"


# --- Remitente ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "valores, esperado",
    [
        ([FROM_OFICIAL], REMITENTE_OFICIAL),
        ([REMITENTE_OFICIAL], REMITENTE_OFICIAL),
        (["Bancolombia <x@evil.com>"], "x@evil.com"),
        ([f'"{REMITENTE_OFICIAL}" <x@evil.com>'], "x@evil.com"),  # nombre visible engañoso
        ([f"{REMITENTE_OFICIAL}, x@evil.com"], ""),  # dos direcciones
        ([FROM_OFICIAL, "x@evil.com"], ""),  # dos encabezados From
        ([""], ""),
        ([], ""),
        (["Bancolombia <>"], ""),
        (["sin-arroba"], ""),
    ],
)
def test_direccion_remitente(valores, esperado):
    assert direccion_remitente(valores) == esperado


def test_remitente_valido_sin_distinguir_mayusculas():
    assert remitente_valido(_correo(remitente=REMITENTE_OFICIAL.upper()), REMITENTE_OFICIAL)
    assert not remitente_valido(_correo(remitente="alertas@bancolombia-falso.com"), REMITENTE_OFICIAL)
    assert not remitente_valido(_correo(remitente=""), REMITENTE_OFICIAL)


# --- Alineación ------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "dominio, alineado",
    [
        (DOMINIO, True),
        ("an." + DOMINIO, True),
        ("otro.an." + DOMINIO, True),
        ("AN.NotificacionesBancolombia.COM", True),
        (DOMINIO + ".evil.co", False),
        ("sendgrid.net", False),
        ("evil" + DOMINIO, False),
        ("com", False),  # un dominio de primer nivel suelto nunca se alinea
        ("", False),
    ],
)
def test_dominio_alineado_con_el_remitente_oficial(dominio, alineado):
    assert dominio_alineado(dominio, "an." + DOMINIO) is alineado


# --- Autenticación: casos que se aceptan ------------------------------------------------------

@pytest.mark.parametrize(
    "autenticacion",
    [
        AUTENTICACION_LEGITIMA,
        _autenticacion(DKIM_FAIL, SPF_FAIL, DMARC_OK),  # solo dmarc=pass
        # D15: los casos que antes probaban "dkim=pass alineado sin dmarc basta"
        # (solo_dkim, header_d_subdominio, header_d_padre, dkim_repetido) pasaron
        # a test_d15_dkim_sin_dmarc_se_rechaza. Aquí queda su equivalente con DMARC.
        _autenticacion(DMARC_OK),  # dmarc=pass sin dkim ni spf
        _autenticacion(f"dmarc=pass header.from=an.{DOMINIO}"),  # header.from subdominio
        _autenticacion("dkim=pass header.i=@sendgrid.net", DMARC_OK),  # dkim ajeno, no decide
        # Mayúsculas, espacios alrededor de "=" y líneas plegadas (con DMARC, D15).
        "MX.Google.com;\n\tDKIM = PASS\n\t header.I=@" + DOMINIO.upper()
        + ";\n\tDMARC = PASS\n\t header.From=" + DOMINIO.upper(),
    ],
    ids=["legitimo", "solo_dmarc", "dmarc_sin_dkim_ni_spf", "header_from_subdominio",
         "dkim_ajeno_con_dmarc", "mayusculas_y_plegado"],
)
def test_autenticacion_valida(autenticacion):
    assert autenticacion_valida(_correo(autenticacion), REMITENTE_OFICIAL)


# --- D15: DMARC obligatorio -------------------------------------------------------------------
#
# Antes (D11) bastaba un dkim=pass alineado si no había dmarc. D15 lo cambia:
# sin dmarc=pass alineado el correo se rechaza con "sin_pass_alineado", aunque
# DKIM o SPF pasen alineados.

@pytest.mark.parametrize(
    "autenticacion",
    [
        _autenticacion(DKIM_OK),
        _autenticacion(DKIM_OK, SPF_FAIL),  # antes: "solo_dkim" (aceptado)
        _autenticacion(DKIM_OK, SPF_OK),  # dkim y spf alineados, sin dmarc
        _autenticacion(f"dkim=pass header.d=an.{DOMINIO} header.s=sel"),  # antes: header_d_subdominio
        _autenticacion(f"dkim=pass header.d={DOMINIO}"),  # antes: header_d_padre
        _autenticacion("dkim=pass header.i=@sendgrid.net", DKIM_OK),  # antes: dkim_repetido
        "MX.Google.com;\n\tDKIM = PASS\n\t header.I=@" + DOMINIO.upper(),  # antes: mayusculas_y_plegado
        _autenticacion(f'dkim=pass (nota "x") header.d={DOMINIO}'),  # antes: comilla en comentario
        _autenticacion(SPF_OK),  # spf=pass solo
        _autenticacion(DKIM_OK, SPF_OK, DMARC_FAIL),
        _autenticacion(DKIM_OK, SPF_OK, f"dmarc=none header.from={DOMINIO}"),
        _autenticacion(DKIM_OK, SPF_OK, f"dmarc=temperror header.from={DOMINIO}"),
        _autenticacion(DKIM_OK, SPF_OK, "dmarc=pass header.from=evil.example"),  # no alineado
        _autenticacion(DKIM_OK, SPF_OK, "dmarc=pass"),  # sin header.from
    ],
    ids=["dkim_solo", "dkim_con_spf_fail", "dkim_y_spf_sin_dmarc", "dkim_header_d_subdominio",
         "dkim_header_d_padre", "dkim_repetido", "dkim_mayusculas_y_plegado", "dkim_comilla_en_comentario",
         "spf_solo", "dmarc_fail", "dmarc_none", "dmarc_temperror", "dmarc_no_alineado",
         "dmarc_sin_header_from"],
)
def test_d15_sin_dmarc_pass_alineado_se_rechaza(autenticacion):
    correo = _correo(autenticacion)
    assert motivo_autenticacion_invalida(correo, REMITENTE_OFICIAL) == MOTIVO_SIN_PASS_ALINEADO
    assert not autenticacion_valida(correo, REMITENTE_OFICIAL)


def test_d15_dmarc_pass_alineado_con_dkim_fail_se_acepta():
    correo = _correo(_autenticacion(DKIM_FAIL, DMARC_OK))
    assert motivo_autenticacion_invalida(correo, REMITENTE_OFICIAL) is None
    assert autenticacion_valida(correo, REMITENTE_OFICIAL)


def test_d15_encabezado_roto_sigue_siendo_encabezado_invalido():
    # El análisis estricto no cambia: lo que se sale de la gramática no llega
    # a la regla de DMARC.
    correo = _correo(_autenticacion(DKIM_OK, DMARC_OK + ";"))
    assert motivo_autenticacion_invalida(correo, REMITENTE_OFICIAL) == MOTIVO_ENCABEZADO_INVALIDO


# --- Autenticación: casos que se rechazan ------------------------------------------------------
#
# D15 (docs/decisiones.md): solo cuenta un dmarc=pass alineado. Los casos que
# fabricaban un dkim=pass se rechazaban ahora solo por faltar el dmarc, sin
# probar el analizador; el pass fabricado es ahora un dmarc=pass
# header.from=<banco>. Cada caso declara su motivo: con MOTIVO_ENCABEZADO_INVALIDO
# se exige además que analizar_authentication_results(...) devuelva None.

I, S = MOTIVO_ENCABEZADO_INVALIDO, MOTIVO_SIN_PASS_ALINEADO


@pytest.mark.parametrize(
    "autenticacion, motivo",
    [
        ("", I),
        (_autenticacion(DKIM_FAIL, SPF_FAIL, DMARC_FAIL), S),
        (_autenticacion("dkim=pass header.i=@sendgrid.net", SPF_FAIL, DMARC_FAIL), S),  # dkim no alineado
        (_autenticacion(DKIM_OK, SPF_OK, DMARC_OK, servidor="mx.evil.com"), I),  # otro servidor
        (_autenticacion(DMARC_OK, servidor="mx.google.com.evil.co"), I),
        (_autenticacion(
            f"dkim=pass header.d={DOMINIO}.evil.co",
            f"spf=pass smtp.mailfrom=alertas@{DOMINIO}.evil.co",
            f"dmarc=pass header.from={DOMINIO}.evil.co",
        ), S),
        *[
            (_autenticacion(f"dkim={r} header.i=@{DOMINIO}", f"spf={r} smtp.mailfrom={REMITENTE_OFICIAL}",
                            f"dmarc={r} header.from={DOMINIO}"), S)
            for r in ("softfail", "neutral", "none", "temperror", "permerror")
        ],
        (_autenticacion(f"dkim=passed header.i=@{DOMINIO}", f"spf=passed smtp.mailfrom={REMITENTE_OFICIAL}",
                        f"dmarc=passed header.from={DOMINIO}"), I),
        # "pass" solo dentro de un comentario.
        (_autenticacion(f"spf=fail (dmarc=pass header.from={DOMINIO}) smtp.mailfrom={REMITENTE_OFICIAL}"), S),
        # Resultado sin propiedad que permita alinearlo.
        (_autenticacion("dmarc=pass", "dkim=pass"), S),
        (_autenticacion("dkim=pass", "dmarc=pass", "spf=pass"), I),  # spf sin smtp.*
        # Sin servidor.
        (f"{DKIM_OK}; {DMARC_OK}", I),
        # Solo SPF en pass, aunque esté alineado: ya NO basta. El dominio de
        # smtp.mailfrom lo elige quien envía; si el banco pasara SPF alineado,
        # Gmail informaría también dmarc=pass.
        (_autenticacion(DKIM_FAIL, SPF_OK, DMARC_FAIL), S),
        (_autenticacion("spf=pass smtp.mailfrom=an." + DOMINIO), S),
        # Comillas en el MAIL FROM (variantes del revisor): la parte local
        # puede traer "@", ";" y espacios para simular otros resultados.
        (_autenticacion(f'spf=pass smtp.mailfrom="x@an.{DOMINIO}"@evil.com',
                        f"dmarc=fail header.from=an.{DOMINIO}"), S),
        (_autenticacion(f'spf=pass smtp.mailfrom="x;dmarc=pass header.from=an.{DOMINIO}"@evil.com',
                        f"dmarc=fail header.from=an.{DOMINIO}"), I),
        # Comillas en header.from (antes en header.i de un dkim).
        (_autenticacion(f'dmarc=pass header.from="x@{DOMINIO}"@evil.com'), S),
        (_autenticacion(f'dmarc=pass header.from="@{DOMINIO}"'), S),
        # Barra invertida fuera de una cadena entre comillas.
        (_autenticacion(f"dmarc=pass header.from=x\\@{DOMINIO}"), I),
    ],
    ids=["vacio", "todo_fail", "dkim_no_alineado", "otro_servidor", "servidor_parecido",
         "dominio_parecido", "softfail", "neutral", "none", "temperror", "permerror", "passed",
         "pass_en_comentario", "sin_propiedades", "sin_propiedades_spf", "sin_servidor", "solo_spf",
         "solo_spf_dominio", "mailfrom_comillas_con_arroba", "mailfrom_comillas_con_punto_y_coma",
         "header_from_comillas", "header_from_comillas_simple", "barra_invertida"],
)
def test_autenticacion_invalida(autenticacion, motivo):
    from finanzas.gmail import analizar_authentication_results

    assert not autenticacion_valida(_correo(autenticacion), REMITENTE_OFICIAL)
    assert motivo_autenticacion_invalida(_correo(autenticacion), REMITENTE_OFICIAL) == motivo
    assert (analizar_authentication_results(autenticacion) is None) == (motivo == I)



# --- Integración: el correo completo pasa por sincronizar ----------------------------------------

def _mensaje(from_: list[str] | None = None, resultados: list[str] | None = None) -> dict:
    """El fixture legítimo con otros encabezados From y Authentication-Results
    (``resultados`` en orden, de arriba abajo)."""
    mensaje = copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
    otros = [
        h for h in mensaje["payload"]["headers"]
        if h["name"].lower() not in ("from", "authentication-results")
    ]
    nuevos = [{"name": "Authentication-Results", "value": v} for v in (resultados or [])]
    nuevos += [{"name": "From", "value": v} for v in (from_ if from_ is not None else [FROM_OFICIAL])]
    mensaje["payload"]["headers"] = nuevos + otros
    return mensaje


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "aut.db"))
    db.inicializar(conexion)
    with db.transaccion(conexion):
        sql(
            conexion,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) VALUES (1, 0, '2026-08-01')"
        )
    yield conexion
    conexion.close()


CASOS_RECHAZO = {
    "from_falsificado": _mensaje(["Bancolombia <alertas@bancolombia-falso.com>"], [AUTENTICACION_LEGITIMA]),
    "nombre_visible_enganoso": _mensaje(["Bancolombia <x@evil.com>"], [AUTENTICACION_LEGITIMA]),
    "dos_direcciones": _mensaje([f"{REMITENTE_OFICIAL}, x@evil.com"], [AUTENTICACION_LEGITIMA]),
    "todo_fail": _mensaje(resultados=[_autenticacion(DKIM_FAIL, SPF_FAIL, DMARC_FAIL)]),
    "dkim_no_alineado": _mensaje(resultados=[_autenticacion(
        "dkim=pass header.i=@sendgrid.net", "spf=pass smtp.mailfrom=rebote@sendgrid.net", DMARC_FAIL)]),
    "sin_authentication_results": _mensaje(resultados=[]),
    "otro_servidor_primero": _mensaje(resultados=[
        _autenticacion(DKIM_OK, SPF_OK, DMARC_OK, servidor="mx.evil.com"), AUTENTICACION_LEGITIMA]),
    # El atacante pone un encabezado con "pass" DEBAJO del auténtico de Gmail.
    "pass_falso_debajo_del_fail": _mensaje(resultados=[
        _autenticacion(DKIM_FAIL, SPF_FAIL, DMARC_FAIL), AUTENTICACION_LEGITIMA]),
    "dominio_parecido": _mensaje(resultados=[_autenticacion(
        f"dkim=pass header.d={DOMINIO}.evil.co", f"spf=pass smtp.mailfrom=x@{DOMINIO}.evil.co",
        f"dmarc=pass header.from={DOMINIO}.evil.co")]),
}


@pytest.mark.parametrize("caso", list(CASOS_RECHAZO))
def test_correo_no_autenticado_no_crea_movimiento(conn, caso, caplog):
    correo = correo_desde_mensaje(CASOS_RECHAZO[caso])
    with caplog.at_level(logging.DEBUG):
        resultado = sincronizar(conn, ClienteFalso({correo.gmail_id: correo}), REMITENTE_OFICIAL)

    assert resultado == ResultadoSincronizacion(rechazados_autenticacion=1)
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 0
    filas = [dict(f) for f in sql(conn, "SELECT * FROM correos_no_reconocidos")]
    assert filas == [{"gmail_id": "msg-0001", "fecha": "2026-08-07T16:42:30", "asunto": "Alerta de compra (ejemplo)"}]
    # Logs: solo el id y el motivo genérico.
    assert "msg-0001" in caplog.text
    assert ("rechazado por remitente" in caplog.text) or ("rechazado por autenticación" in caplog.text)
    for dato in ("evil", "sendgrid", "bancolombia-falso", "dkim", "spf", "dmarc", "MERPAGO", "245.700"):
        assert dato not in caplog.text


def test_d15_sincronizacion_con_dkim_alineado_sin_dmarc_se_rechaza(conn, caplog):
    """D15: un aviso con dkim=pass (y spf=pass) alineados pero sin dmarc ya no
    crea movimiento; queda como no reconocido con motivo sin_pass_alineado."""
    correo = correo_desde_mensaje(_mensaje(resultados=[_autenticacion(DKIM_OK, SPF_OK)]))
    with caplog.at_level(logging.DEBUG):
        resultado = sincronizar(conn, ClienteFalso({correo.gmail_id: correo}), REMITENTE_OFICIAL)
    assert resultado == ResultadoSincronizacion(rechazados_autenticacion=1)
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 0
    assert sql(conn, "SELECT COUNT(*) FROM correos_no_reconocidos").fetchone()[0] == 1
    assert "motivo=sin_pass_alineado" in caplog.text


def test_d15_sincronizacion_con_dmarc_pass_y_dkim_fail_crea_movimiento(conn):
    correo = correo_desde_mensaje(_mensaje(resultados=[_autenticacion(DKIM_FAIL, SPF_FAIL, DMARC_OK)]))
    assert sincronizar(conn, ClienteFalso({correo.gmail_id: correo}), REMITENTE_OFICIAL) == (
        ResultadoSincronizacion(nuevos=1)
    )


def test_correo_rechazado_no_pasa_por_el_extractor(conn, monkeypatch):
    llamadas = []
    monkeypatch.setattr(evaluacion, "clasificar_correo", lambda textos: llamadas.append(textos))
    correo = correo_desde_mensaje(CASOS_RECHAZO["todo_fail"])
    sincronizar(conn, ClienteFalso({correo.gmail_id: correo}), REMITENTE_OFICIAL)
    assert llamadas == []


def test_rechazado_no_se_vuelve_a_descargar(conn):
    correo = correo_desde_mensaje(CASOS_RECHAZO["from_falsificado"])
    sincronizar(conn, ClienteFalso({correo.gmail_id: correo}), REMITENTE_OFICIAL)
    segundo = ClienteFalso({correo.gmail_id: correo})
    assert sincronizar(conn, segundo, REMITENTE_OFICIAL) == ResultadoSincronizacion()
    assert segundo.llamadas_obtener == []


def test_remitente_configurado_distinto_rechaza_el_por_defecto(conn):
    correo = correo_desde_mensaje(_mensaje(resultados=[AUTENTICACION_LEGITIMA]))
    resultado = sincronizar(conn, ClienteFalso({correo.gmail_id: correo}), "alertas@example.com")
    assert resultado == ResultadoSincronizacion(rechazados_autenticacion=1)


def test_correo_legitimo_si_crea_movimiento(conn):
    correo = correo_desde_mensaje(_mensaje(resultados=[AUTENTICACION_LEGITIMA]))
    assert sincronizar(conn, ClienteFalso({correo.gmail_id: correo}), REMITENTE_OFICIAL) == (
        ResultadoSincronizacion(nuevos=1)
    )


def test_remitente_y_autenticacion_no_aparecen_en_el_repr():
    correo = correo_desde_mensaje(_mensaje(resultados=[AUTENTICACION_LEGITIMA]))
    assert correo.remitente == REMITENTE_OFICIAL
    assert correo.autenticacion.startswith("mx.google.com;")
    assert "notificacionesbancolombia" not in repr(correo)


def test_resumen_incluye_los_rechazados():
    texto = ResultadoSincronizacion(rechazados_autenticacion=2).resumen()
    assert "2 rechazados por remitente o autenticación" in texto


def test_dominio_tras_la_ultima_arroba():
    from finanzas.gmail import _dominio

    assert _dominio(f"x@an.{DOMINIO}@evil.com") == "evil.com"
    assert _dominio(f"@{DOMINIO}") == DOMINIO
    assert _dominio(DOMINIO + ".") == DOMINIO


def test_mailfrom_entre_comillas_con_punto_y_coma_caso_del_tester(conn):
    """Caso 2 del tester: el MAIL FROM entre comillas trae ";dkim=pass
    header.d=<banco>" para inyectar un resultado falso. Debe rechazarse."""
    mensaje = _mensaje(resultados=[
        'mx.google.com; spf=pass (google.com: domain of "a;dkim=pass header.d=notificacionesbancolombia.com"'
        "@evil.example designates 198.51.100.66 as permitted sender) "
        'smtp.mailfrom="a;dkim=pass header.d=notificacionesbancolombia.com"@evil.example; '
        "dmarc=fail (p=NONE sp=NONE dis=NONE) header.from=notificacionesbancolombia.com"
    ])
    correo = correo_desde_mensaje(mensaje)
    assert remitente_valido(correo, REMITENTE_OFICIAL)
    assert not autenticacion_valida(correo, REMITENTE_OFICIAL)
    resultado = sincronizar(conn, ClienteFalso({correo.gmail_id: correo}), REMITENTE_OFICIAL)
    assert resultado == ResultadoSincronizacion(rechazados_autenticacion=1)
    assert sql(conn, "SELECT COUNT(*) FROM movimientos").fetchone()[0] == 0


def test_comilla_dentro_de_un_comentario_es_valida():
    """Cambio de premisa (decisión del team leader, analizador estricto RFC 8601):
    antes cualquier comilla invalidaba el encabezado. Según la RFC 8601 una
    comilla dentro de un comentario "( ... )" es legal y el comentario se
    descarta entero, así que el resultado que queda es auténtico.

    Ajuste D15: antes bastaba el dkim=pass alineado; ahora el comentario va en
    un dmarc=pass alineado (el dkim solo se rechaza, ver
    test_d15_sin_dmarc_pass_alineado_se_rechaza[dkim_comilla_en_comentario])."""
    assert autenticacion_valida(
        _correo(_autenticacion(f'dkim=pass (nota "x") header.d={DOMINIO}',
                               f'dmarc=pass (nota "x") header.from={DOMINIO}')),
        REMITENTE_OFICIAL,
    )


def test_riesgo_conocido_reenvio_automatico_con_dkim_intacto():
    """RIESGO DOCUMENTADO: un aviso real reenviado automáticamente conserva su
    firma DKIM y Gmail informa dkim=pass y dmarc=pass alineados, así que pasa
    la verificación. Esta prueba fija el comportamiento actual; el dueño
    decidirá si hay que tratarlo. D15 no lo cierra: el DKIM intacto hace que
    DMARC siga en pass (el encabezado ya traía dmarc=pass, no cambia)."""
    reenvio = (
        f"mx.google.com; dkim=pass header.i=@{DOMINIO} header.s=selector-ejemplo header.b=AbCdEf12; "
        "spf=pass (google.com: domain of persona.ejemplo+caf_=duenio@example.org designates 192.0.2.20 "
        # MAIL FROM con "=" entre comillas, como lo escribe Gmail en el encabezado real.
        'as permitted sender) smtp.mailfrom="persona.ejemplo+caf_=duenio"@example.org; '
        f"dmarc=pass (p=REJECT sp=REJECT dis=NONE) header.from={DOMINIO}"
    )
    assert autenticacion_valida(_correo(reenvio), REMITENTE_OFICIAL)
