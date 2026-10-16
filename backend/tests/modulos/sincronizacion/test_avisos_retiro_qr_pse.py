"""Ítem 27 (D30): avisos "Retiraste", pago por código QR y pago por PSE.

Todo es inventado: cajeros (CAJERO EJEMPLO...), empresas (EMPRESA EJEMPLO
SAS...), titulares (NOMBRE COMPLETO DE EJEMPLO...), llaves (3000000000...),
cuentas, tarjetas y productos (1234) y teléfonos (018000000000).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from finanzas.modulos.sincronizacion.adaptadores.avisos import extractor
from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import (
    CATEGORIA_RETIRO,
    DESCRIPCION_PAGO_QR,
    MovimientoExtraido,
    extraer,
    extraer_pago_pse,
    extraer_pago_qr,
    extraer_retiraste,
)
from finanzas.sincronizacion import extraer_aviso

AVISOS = Path(__file__).resolve().parents[2] / "fixtures" / "avisos"
FIN = " Si tienes dudas, llamanos al 000 000 0000."


def leer(nombre: str) -> str:
    return (AVISOS / nombre).read_text(encoding="utf-8")


def retiro(monto="$50.000,00", cajero="CAJERO EJEMPLO", tarjeta="**1234", fecha="05/09/2026",
           hora="a las 10:15", fin=FIN) -> str:
    return f"Bancolombia: Retiraste {monto} en {cajero} de tu T.Deb {tarjeta} el {fecha} {hora}.{fin}"


def qr(titular="NOMBRE COMPLETO DE EJEMPLO", monto="$12,000.00", cuenta="*1234", llave="3000000000",
       fecha="10/09/2026", hora="a las 11:20", fin=FIN) -> str:
    return (
        f"Bancolombia: {titular} pagaste {monto} por codigo QR desde tu cuenta {cuenta} "
        f"a la llave {llave} el {fecha} {hora}.{fin}"
    )


def pse(monto="$350,000.00", empresa="EMPRESA EJEMPLO SAS", producto="1234", fecha="04/09/2026",
        hora="08:30:15", fin=FIN) -> str:
    return f"Bancolombia: Pagaste {monto} a {empresa} desde tu producto {producto} el {fecha} {hora}.{fin}"


# --- Fixtures --------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("archivo", "esperado"),
    [
        ("retiraste_basico.txt", MovimientoExtraido(
            "compra", 5000000, datetime(2026, 9, 5, 10, 15), "CAJERO EJEMPLO", CATEGORIA_RETIRO)),
        ("retiraste_sin_decimales_12h.txt", MovimientoExtraido(
            "compra", 125000000, datetime(2026, 9, 30, 20, 5, 42), "CAJ. PLAZA-EJEMPLO #2", CATEGORIA_RETIRO)),
        ("retiraste_saltos_linea.txt", MovimientoExtraido(
            "compra", 20000050, datetime(2026, 9, 1, 23, 59, 59), "CAJERO NORTE EJEMPLO", CATEGORIA_RETIRO)),
        ("pago_qr_basico.txt", MovimientoExtraido(
            "transferencia", 1200000, datetime(2026, 9, 10, 11, 20), DESCRIPCION_PAGO_QR)),
        ("pago_qr_titular_largo_sin_decimales.txt", MovimientoExtraido(
            "transferencia", 123456700, datetime(2026, 9, 15, 7, 30, 5), DESCRIPCION_PAGO_QR)),
        ("pago_pse_basico.txt", MovimientoExtraido(
            "compra", 35000000, datetime(2026, 9, 4, 8, 30, 15), "EMPRESA EJEMPLO SAS")),
        ("pago_pse_sin_decimales_sin_segundos.txt", MovimientoExtraido(
            "compra", 8990000, datetime(2026, 9, 21, 17, 45), "TARJETA EJEMPLO S.A.S. & CÍA")),
    ],
)
def test_fixtures_se_leen_exactos(archivo, esperado):
    texto = leer(archivo)
    assert extraer(texto) == esperado
    # Igual a través de la sincronización (inicio de aviso, sin encabezado).
    assert extraer_aviso(texto) == esperado
    assert isinstance(esperado.monto_centavos, int)


@pytest.mark.parametrize(
    "archivo",
    [
        "no_reconocido_retiraste_un_asterisco.txt",
        "no_reconocido_pago_qr_con_coma.txt",
        "no_reconocido_pago_pse_con_asterisco.txt",
    ],
)
def test_fixtures_parecidos_no_se_reconocen(archivo):
    assert extraer(leer(archivo)) is None
    assert extraer_aviso(leer(archivo)) is None


def test_solo_el_retiro_trae_categoria_al_leer():
    assert extraer(retiro()).categoria_al_leer == "Retiro a efectivo"
    assert extraer(qr()).categoria_al_leer is None
    assert extraer(pse()).categoria_al_leer is None


# --- Montos ------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("monto", "centavos"),
    [
        ("$50.000,00", 5000000),
        ("$50.000", 5000000),            # sin decimales
        ("$0,50", 50),
        ("$1,99", 199),
        ("$999", 99900),
        ("$1.000,01", 100001),
        ("$12.345.678,90", 1234567890),
    ],
)
def test_montos_del_retiro(monto, centavos):
    assert extraer_retiraste(retiro(monto=monto)).monto_centavos == centavos


@pytest.mark.parametrize(
    ("monto", "centavos"),
    [
        ("$12,000.00", 1200000),
        ("$12,000", 1200000),            # sin decimales
        ("$0.50", 50),
        ("$999", 99900),
        ("$1,000.01", 100001),
        ("$12,345,678.90", 1234567890),
    ],
)
def test_montos_de_los_pagos(monto, centavos):
    assert extraer_pago_qr(qr(monto=monto)).monto_centavos == centavos
    assert extraer_pago_pse(pse(monto=monto)).monto_centavos == centavos


@pytest.mark.parametrize(
    "monto",
    ["$50,000.00", "$50.000,0", "$50.000,000", "$50.00", "$5.0000", "$050.000", "$0,00", "$0",
     "50.000,00", "$ 50.000,00", "$50 000", "$５0.000"],
)
def test_montos_mal_formados_en_el_retiro(monto):
    assert extraer(retiro(monto=monto)) is None


@pytest.mark.parametrize(
    "monto",
    ["$12.000,00", "$12,000.0", "$12,000.000", "$12,00", "$1,0000", "$012,000", "$0.00", "$0",
     "12,000.00", "$12 000"],
)
def test_montos_mal_formados_en_los_pagos(monto):
    assert extraer(qr(monto=monto)) is None
    assert extraer(pse(monto=monto)) is None


# --- Fechas y horas ----------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("hora", "esperada"),
    [
        ("a las 0:00", (0, 0, 0)),
        ("a las 09:05", (9, 5, 0)),
        ("a las 23:59:59", (23, 59, 59)),
        ("a las 12:30 a. m.", (0, 30, 0)),
        ("a las 12:30 p. m.", (12, 30, 0)),
        ("a las 1:05 pm", (13, 5, 0)),
        ("a las 8:29:07 p.m.", (20, 29, 7)),
    ],
)
def test_horas_24_y_12_con_y_sin_segundos_en_retiro_y_qr(hora, esperada):
    for texto in (retiro(hora=hora), qr(hora=hora)):
        m = extraer(texto)
        assert (m.fecha_hora.hour, m.fecha_hora.minute, m.fecha_hora.second) == esperada


@pytest.mark.parametrize(
    ("hora", "esperada"),
    [("08:30:15", (8, 30, 15)), ("8:30", (8, 30, 0)), ("23:59:59", (23, 59, 59)), ("1:05:09 p. m.", (13, 5, 9))],
)
def test_horas_del_pse_sin_a_las(hora, esperada):
    m = extraer(pse(hora=hora))
    assert (m.fecha_hora.hour, m.fecha_hora.minute, m.fecha_hora.second) == esperada


@pytest.mark.parametrize("hora", ["a las 08:30:15", "a las 8:30"])
def test_pse_con_a_las_no_se_reconoce(hora):
    assert extraer(pse(hora=hora)) is None


@pytest.mark.parametrize("hora", ["10:15", "10:15:00"])
def test_retiro_y_qr_sin_a_las_no_se_reconocen(hora):
    assert extraer(retiro(hora=hora)) is None
    assert extraer(qr(hora=hora)) is None


@pytest.mark.parametrize(
    "hora", ["a las 24:00", "a las 10:60", "a las 10:15:60", "a las 13:00 p. m.", "a las 0:10 am", "a las 10"]
)
def test_horas_imposibles(hora):
    assert extraer(retiro(hora=hora)) is None
    assert extraer(qr(hora=hora)) is None
    assert extraer(pse(hora=hora.removeprefix("a las "))) is None


@pytest.mark.parametrize("fecha", ["31/02/2026", "00/09/2026", "05/13/2026", "05/09/26", "5/9/2026", "05-09-2026",
                                   "05/09/1999", "05/09/2100"])
def test_fechas_no_validas(fecha):
    assert extraer(retiro(fecha=fecha)) is None
    assert extraer(qr(fecha=fecha)) is None
    assert extraer(pse(fecha=fecha)) is None


def test_29_de_febrero_bisiesto():
    assert extraer(retiro(fecha="29/02/2028")).fecha_hora.date().isoformat() == "2028-02-29"


# --- Retiro: cajero y tarjeta -------------------------------------------------------------------

@pytest.mark.parametrize("cajero", ["CAJERO EJEMPLO", "CAJ. PLAZA-EJEMPLO #2", "Cajero Ñandú Éxito", "ATM*CENTRO",
                                    "X", "C" * 100])
def test_cajeros_validos(cajero):
    assert extraer(retiro(cajero=cajero)).descripcion == cajero


@pytest.mark.parametrize(
    "cajero",
    ["C" * 101, "CAJERO *1234", "CAJERO 05/09/26", "CAJERO 10:15", "CAJERO Bancolombia: X",
     "CAJERO Compraste", "CAJERO PAGASTE"],
)
def test_cajeros_que_no_se_aceptan(cajero):
    assert extraer(retiro(cajero=cajero)) is None


@pytest.mark.parametrize("tarjeta", ["*1234", "***1234", "**123", "**12345", "**12a4", "1234"])
def test_tarjeta_del_retiro_es_dos_asteriscos_y_4_digitos(tarjeta):
    assert extraer(retiro(tarjeta=tarjeta)) is None


def test_retiro_deformado_no_salta_a_una_repeticion_del_texto_adicional():
    deformado = (
        "Bancolombia: Retiraste $50.000,00 en CAJERO EJEMPLO con tu T.Deb **1234 el 05/09/2026 a las 10:15. "
        "Recuerda: Retiraste $9.000,00 en OTRO de tu T.Deb **1234 el 06/09/2026 a las 10:15."
    )
    assert extraer(deformado) is None


def test_retiro_con_otra_redaccion():
    assert extraer("Bancolombia: Retiraste $50.000,00 de CAJERO EJEMPLO con tu T.Deb **1234 el 05/09/2026 "
                   "a las 10:15.") is None
    assert extraer("Bancolombia: Retiro $50.000,00 en CAJERO EJEMPLO de tu T.Deb **1234 el 05/09/2026 "
                   "a las 10:15.") is None


# --- Pago QR: titular, cuenta y llave ----------------------------------------------------------

@pytest.mark.parametrize(
    "titular",
    [
        "ANA",
        "NOMBRE COMPLETO DE EJEMPLO",                                       # más de 3 palabras (no es Bre-B)
        "MARÍA JOSÉ ÑUÑEZ GÜELL",
        "UNO DOS TRES CUATRO CINCO SEIS SIETE OCHO NUEVE DIEZ",             # 10 palabras
        "A" * 80,
    ],
)
def test_titulares_validos(titular):
    m = extraer(qr(titular=titular))
    assert m == MovimientoExtraido("transferencia", 1200000, datetime(2026, 9, 10, 11, 20), DESCRIPCION_PAGO_QR)


@pytest.mark.parametrize(
    "titular",
    [
        "NOMBRE COMPLETO,",                     # con coma
        "NOMBRE, COMPLETO",
        "UNO DOS TRES CUATRO CINCO SEIS SIETE OCHO NUEVE DIEZ ONCE",  # 11 palabras
        "A" * 81,
        "NOMBRE 2 EJEMPLO",                     # con dígitos
        "NOMBRE. EJEMPLO",                      # con punto
        "NOMBRE  EJEMPLO X-Y",
        "Reversamos este pago. NOMBRE",
        "NOMBRE PAGASTE",                       # otra palabra de aviso
        "TRANSFERISTE",
        "",
        # Revisión del ítem 27: el titular va en mayúsculas, así una frase del
        # banco antes de "pagaste" no se toma como titular.
        "María José Ñuñez Güell",
        "Nombre Completo",
        "NOMBRE completo",
        "nombre",
        "Te recordamos que",
        "Recuerda que ya",
        "Hola NOMBRE ya",
        "Si no reconoces que",
    ],
)
def test_titulares_que_no_se_aceptan(titular):
    assert extraer(qr(titular=titular)) is None
    # Tampoco a través de la sincronización, ni con el encabezado permitido.
    assert extraer_aviso(qr(titular=titular)) is None
    assert extraer_aviso("¡Listo! Todo salió bien con tus movimientos " + qr(titular=titular)) is None


@pytest.mark.parametrize(
    "frase",
    [
        "Te recordamos que",
        "te recordamos que",
        "Te informamos que ya",
        "Confirmamos que",
        "Ya",
    ],
)
def test_frase_del_banco_antes_de_pagaste_no_es_un_pago(frase):
    texto = (
        f"Bancolombia: {frase} pagaste $12,000.00 por codigo QR desde tu cuenta *1234 a la llave "
        f"3000000000 el 10/09/2026 a las 11:20.{FIN}"
    )
    assert extraer(texto) is None
    assert extraer_aviso(texto) is None


def test_riesgo_aceptado_frase_toda_en_mayusculas():
    # Como en D25: una frase corta TODA en mayúsculas y sin signos no se
    # distingue de un nombre. Se documenta para que un cambio lo haga visible.
    assert extraer(qr(titular="TE RECORDAMOS QUE")) is not None


@pytest.mark.parametrize(
    ("cuenta", "llave"),
    [("1234", "3000000000"), ("**1234", "3000000000"), ("*123", "3000000000"), ("*1234", "300"),
     ("*1234", "1" * 21), ("*1234", "@llaveejemplo"), ("*1234", "ejemplo@example.com"), ("*1234", "*3000000000"),
     ("*1234", "300-000-0000")],
)
def test_cuenta_y_llave_del_qr(cuenta, llave):
    assert extraer(qr(cuenta=cuenta, llave=llave)) is None


def test_llaves_de_4_y_20_digitos():
    assert extraer(qr(llave="1234")) is not None
    assert extraer(qr(llave="1" * 20)) is not None


def test_qr_con_otra_redaccion():
    base = qr()
    assert extraer(base.replace("por codigo QR", "por código QR")) is None  # el aviso real va sin tilde
    assert extraer(base.replace("por codigo QR", "con codigo QR")) is None
    assert extraer(base.replace(" a la llave", " a la cuenta")) is None
    # Sin titular no es un pago QR (y tampoco es PSE).
    assert extraer("Bancolombia: Pagaste $12,000.00 por codigo QR desde tu cuenta *1234 a la llave 3000000000 "
                   "el 10/09/2026 a las 11:20.") is None


def test_el_qr_no_guarda_titular_cuenta_ni_llave():
    m = extraer(qr(titular="NOMBRE COMPLETO DE EJEMPLO", llave="3000005678"))
    textos = repr(m)
    assert "NOMBRE" not in textos and "3000005678" not in textos and "1234" not in textos


# --- Pago PSE: empresa y producto --------------------------------------------------------------

@pytest.mark.parametrize("empresa", ["EMPRESA EJEMPLO SAS", "NU EJEMPLO S.A.", "Servicios Ñandú & Cía. 24",
                                     "E", "E" * 100, "EMPRESA A B"])
def test_empresas_validas(empresa):
    assert extraer(pse(empresa=empresa)).descripcion == empresa


@pytest.mark.parametrize(
    "empresa",
    ["E" * 101, "EMPRESA *1234", "EMPRESA 04/09/2026", "EMPRESA 08:30", "Bancolombia: EMPRESA",
     "EMPRESA RECIBISTE", "EMPRESA RETIRASTE"],
)
def test_empresas_que_no_se_aceptan(empresa):
    assert extraer(pse(empresa=empresa)) is None


@pytest.mark.parametrize("producto", ["*1234", "123", "12345", "12a4", "**1234"])
def test_producto_del_pse_es_4_digitos_sin_asterisco(producto):
    assert extraer(pse(producto=producto)) is None


def test_pse_con_otra_redaccion():
    assert extraer(pse().replace("desde tu producto", "desde tu cuenta")) is None
    assert extraer(pse().replace("Pagaste", "Pagamos")) is None
    assert extraer(pse().replace(" a EMPRESA", " EMPRESA")) is None


# --- Varios avisos y avisos citados (ítem 21) ---------------------------------------------------

def test_solo_se_toma_el_primer_aviso():
    texto = retiro(fin=" " + pse())
    assert extraer(texto).descripcion == "CAJERO EJEMPLO"


@pytest.mark.parametrize("aviso", [retiro(), qr(), pse()])
def test_avisos_citados_quedan_no_reconocidos(aviso):
    assert extraer_aviso(aviso) is not None
    assert extraer_aviso("Reversamos esta transacción. " + aviso) is None
    assert extraer_aviso("Así se ven nuestras alertas: " + aviso) is None
    assert extraer_aviso("Bancolombia: Compraste algo. " + aviso) is None


@pytest.mark.parametrize("aviso", [retiro(), qr(), pse()])
def test_con_el_encabezado_de_la_plantilla_si_se_leen(aviso):
    assert extraer_aviso("¡Listo! Todo salió bien con tus movimientos " + aviso) == extraer(aviso)


def test_sin_prefijo_bancolombia_la_sincronizacion_no_lo_lee():
    assert extraer_aviso(retiro().removeprefix("Bancolombia: ")) is None
    assert extraer_aviso(pse().removeprefix("Bancolombia: ")) is None


@pytest.mark.parametrize("invisible", ["​", "­", "﻿"])
def test_invisibles_dentro_del_aviso(invisible):
    texto = retiro().replace("Retiraste", f"Reti{invisible}raste")
    assert extraer(texto) == extraer(retiro())


def test_los_avisos_anteriores_se_leen_igual():
    for nombre, tipo in [("compraste_merpago.txt", "compra"), ("transferiste_basico.txt", "transferencia"),
                         ("transferiste_llave_basico.txt", "transferencia"), ("recibiste_basico.txt", "ingreso")]:
        m = extraer(leer(nombre))
        assert m is not None and m.tipo == tipo and m.categoria_al_leer is None


def test_extractor_es_puro():
    # Sin Gmail, base de datos ni red: biblioteca estándar y contrato normalizado puro.
    import ast
    from finanzas.modulos.sincronizacion.adaptadores.avisos import extractor as lector
    from finanzas.modulos.sincronizacion import contratos

    arbol = ast.parse(Path(lector.__file__).read_text(encoding="utf-8"))
    modulos = {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
    modulos |= {a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
    assert modulos <= {"__future__", "re", "unicodedata", "datetime", "finanzas.modulos.sincronizacion.contratos"}
    arbol_contrato = ast.parse(Path(contratos.__file__).read_text(encoding="utf-8"))
    imports_contrato = {n.module for n in ast.walk(arbol_contrato) if isinstance(n, ast.ImportFrom)}
    imports_contrato |= {a.name for n in ast.walk(arbol_contrato) if isinstance(n, ast.Import) for a in n.names}
    assert imports_contrato <= {"__future__", "collections.abc", "dataclasses", "datetime", "typing"}
