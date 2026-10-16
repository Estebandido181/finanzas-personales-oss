"""Casos borde del extractor de avisos de Bancolombia.

Complementa ``test_extractor.py``. Todos los datos son inventados:
comercios ficticios, tarjetas y cuentas tipo *1234, *5678, *0000.
"""

from datetime import datetime

import pytest

from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import (
    MovimientoExtraido,
    extraer,
    extraer_compraste,
    extraer_transferiste,
)


def compraste(monto="$68.630,00", comercio="MERPAGO*TIENDA", fecha="15/03/2026", hora="14:32"):
    return (
        f"Bancolombia: Compraste {monto} en {comercio} con tu T.Deb *1234, "
        f"el {fecha} a las {hora}."
    )


def transferiste(monto="$6,000.00", destino="*5678", fecha="15/03/26", hora="09:15"):
    return (
        f"Bancolombia: Transferiste {monto} desde tu cuenta *1234 a la cuenta {destino} "
        f"el {fecha} a las {hora}."
    )


# --- Comercios que contienen palabras fijas del aviso ------------------------

@pytest.mark.parametrize(
    "comercio",
    [
        "CAFE CON LECHE",
        "PAN CON QUESO SAS",
        "TIENDA EN LINEA",
        "EN CASA",
        "CON",
        "EL RINCON DE TU BARRIO",
        "A LAS CUATRO BAR",
        "COMPRASTE YA SAS",
        "TU T.DEB",
        "EL 15/03 SAS",
    ],
)
def test_compraste_comercio_con_palabras_fijas(comercio):
    mov = extraer(compraste(comercio=comercio))
    assert mov == MovimientoExtraido("compra", 6863000, datetime(2026, 3, 15, 14, 32), comercio)


def test_compraste_comercio_con_saltos_de_linea_se_normaliza():
    texto = compraste(comercio="TIENDA\n  EL\tSOL")
    assert extraer_compraste(texto).descripcion == "TIENDA EL SOL"


# --- Texto adicional que repite partes del aviso -----------------------------

def test_compraste_texto_adicional_repite_el_aviso_toma_el_primero():
    texto = compraste() + " " + compraste(monto="$1.000,00", comercio="OTRO SAS", fecha="16/03/2026")
    assert extraer(texto) == MovimientoExtraido(
        "compra", 6863000, datetime(2026, 3, 15, 14, 32), "MERPAGO*TIENDA"
    )


def test_transferiste_texto_adicional_repite_el_aviso_toma_el_primero():
    texto = transferiste() + " " + transferiste(monto="$1,000.00", destino="*0000", fecha="16/03/26")
    assert extraer(texto) == MovimientoExtraido(
        "transferencia", 600000, datetime(2026, 3, 15, 9, 15), "*5678"
    )


def test_compraste_texto_adicional_con_palabras_fijas():
    texto = compraste() + " Recuerda: con tu T.Deb *1234 compraste en linea el 15/03/2026 a las 10:00."
    assert extraer(texto).descripcion == "MERPAGO*TIENDA"


def test_compraste_seguido_de_transferiste_se_lee_como_compra():
    texto = compraste() + " " + transferiste()
    assert extraer(texto).tipo == "compra"


# --- 29 de febrero -----------------------------------------------------------

@pytest.mark.parametrize(
    "fecha, esperada",
    [
        ("29/02/2028", datetime(2028, 2, 29, 14, 32)),  # bisiesto
        ("29/02/2000", datetime(2000, 2, 29, 14, 32)),  # bisiesto (divisible por 400)
    ],
)
def test_compraste_29_febrero_bisiesto(fecha, esperada):
    assert extraer_compraste(compraste(fecha=fecha)).fecha_hora == esperada


@pytest.mark.parametrize("fecha", ["29/02/2027", "29/02/2100"])  # no bisiestos
def test_compraste_29_febrero_no_bisiesto(fecha):
    assert extraer_compraste(compraste(fecha=fecha)) is None
    assert extraer(compraste(fecha=fecha)) is None


def test_transferiste_29_febrero_bisiesto():
    assert extraer_transferiste(transferiste(fecha="29/02/28")).fecha_hora == datetime(2028, 2, 29, 9, 15)


def test_transferiste_29_febrero_no_bisiesto():
    assert extraer_transferiste(transferiste(fecha="29/02/27")) is None
    assert extraer(transferiste(fecha="29/02/27")) is None


# --- Límites de hora ---------------------------------------------------------

@pytest.mark.parametrize(
    "hora, esperada",
    [
        ("00:00", datetime(2026, 3, 15, 0, 0)),
        ("23:59", datetime(2026, 3, 15, 23, 59)),
        ("00:00:00", datetime(2026, 3, 15, 0, 0, 0)),
        ("23:59:59", datetime(2026, 3, 15, 23, 59, 59)),
    ],
)
def test_compraste_horas_limite(hora, esperada):
    assert extraer_compraste(compraste(hora=hora)).fecha_hora == esperada


@pytest.mark.parametrize(
    "hora, esperada",
    [
        ("00:00", datetime(2026, 3, 15, 0, 0)),
        ("23:59", datetime(2026, 3, 15, 23, 59)),
        ("23:59:59", datetime(2026, 3, 15, 23, 59, 59)),
    ],
)
def test_transferiste_horas_limite(hora, esperada):
    assert extraer_transferiste(transferiste(hora=hora)).fecha_hora == esperada


@pytest.mark.parametrize("hora", ["23:59:60", "12:00:5", "12:0", "1200", "13:00 pm"])
def test_horas_invalidas(hora):
    assert extraer(compraste(hora=hora)) is None
    assert extraer(transferiste(hora=hora)) is None


# --- Límites de fecha --------------------------------------------------------

@pytest.mark.parametrize(
    "fecha, esperada",
    [("01/01/2026", datetime(2026, 1, 1, 14, 32)), ("31/12/2026", datetime(2026, 12, 31, 14, 32))],
)
def test_compraste_fechas_limite(fecha, esperada):
    assert extraer_compraste(compraste(fecha=fecha)).fecha_hora == esperada


@pytest.mark.parametrize("fecha", ["00/03/2026", "15/00/2026", "15/13/2026", "31/04/2026", "1/03/2026", "15/3/2026"])
def test_compraste_fechas_invalidas(fecha):
    assert extraer(compraste(fecha=fecha)) is None


@pytest.mark.parametrize("fecha", ["00/03/26", "15/13/26", "31/06/26", "15/03/6", "15/3/26"])
def test_transferiste_fechas_invalidas(fecha):
    assert extraer(transferiste(fecha=fecha)) is None


# --- Espacios alrededor del monto --------------------------------------------

def test_compraste_espacios_repetidos_alrededor_del_monto_se_toleran():
    texto = compraste().replace(" $68.630,00 ", "   $68.630,00\t\n ")
    assert extraer_compraste(texto).monto_centavos == 6863000


def test_transferiste_espacios_repetidos_alrededor_del_monto_se_toleran():
    texto = transferiste().replace(" $6,000.00 ", "  \n$6,000.00   ")
    assert extraer_transferiste(texto).monto_centavos == 600000


@pytest.mark.parametrize(
    "monto",
    ["$ 68.630,00", "$68.630, 00", "$68 .630,00", "$68.630 ,00", "$68.630,0", "$68.630,000", "$68.630"],
)
def test_compraste_espacios_o_formato_dentro_del_monto(monto):
    assert extraer(compraste(monto=monto)) is None


@pytest.mark.parametrize(
    "monto",
    ["$ 6,000.00", "$6,000. 00", "$6 ,000.00", "$6,000.0", "$6,000", "$6,000.000"],
)
def test_transferiste_espacios_o_formato_dentro_del_monto(monto):
    assert extraer(transferiste(monto=monto)) is None


def test_monto_minimo_un_peso():
    assert extraer(compraste(monto="$1,00")).monto_centavos == 100
    assert extraer(transferiste(monto="$1.00")).monto_centavos == 100


def test_monto_muy_grande():
    assert extraer(compraste(monto="$1.000.000.000,00")).monto_centavos == 100_000_000_000
    assert extraer(transferiste(monto="$1,000,000,000.00")).monto_centavos == 100_000_000_000


# --- Cuenta destino ----------------------------------------------------------

@pytest.mark.parametrize("destino", ["*56A8", "*ABCD", "*567", "*567890123456789012345", "* 5678", "**5678", "*56-78"])
def test_transferiste_cuenta_destino_invalida(destino):
    assert extraer_transferiste(transferiste(destino=destino)) is None
    assert extraer(transferiste(destino=destino)) is None


@pytest.mark.parametrize("origen", ["*12A4", "*123", "1234"])
def test_transferiste_cuenta_origen_invalida(origen):
    texto = transferiste().replace("tu cuenta *1234", f"tu cuenta {origen}")
    assert extraer(texto) is None


@pytest.mark.parametrize("tarjeta", ["*12A4", "*123", "*12345", "1234"])
def test_compraste_tarjeta_invalida(tarjeta):
    texto = compraste().replace("T.Deb *1234", f"T.Deb {tarjeta}")
    assert extraer(texto) is None


# --- Prefijo, entrada vacía y texto inesperado -------------------------------

def test_compraste_sin_prefijo():
    assert extraer(compraste().removeprefix("Bancolombia: ")).monto_centavos == 6863000


@pytest.mark.parametrize(
    "texto",
    [
        "Aviso " + compraste(),                       # texto antes del aviso
        compraste().replace("Bancolombia: ", "Bancolombia:"),  # prefijo sin espacio
        compraste().replace("Bancolombia: ", "Banco: "),        # otro prefijo
        compraste().replace("14:32.", "14:32.Gracias"),        # texto pegado al punto final
    ],
)
def test_compraste_variaciones_no_reconocidas(texto):
    assert extraer(texto) is None


@pytest.mark.parametrize("texto", [None, "", "   ", "\n\t"])
def test_entrada_vacia_o_none(texto):
    assert extraer(texto) is None
    assert extraer_compraste(texto) is None
    assert extraer_transferiste(texto) is None


def test_espacio_no_separable_se_normaliza():
    texto = compraste().replace(" ", " ")
    assert extraer(texto) == MovimientoExtraido(
        "compra", 6863000, datetime(2026, 3, 15, 14, 32), "MERPAGO*TIENDA"
    )


def test_resultado_no_tiene_zona_horaria():
    assert extraer(compraste()).fecha_hora.tzinfo is None
    assert extraer(transferiste()).fecha_hora.tzinfo is None


# --- Dígitos no ASCII (regla "nunca adivinar") -------------------------------

@pytest.mark.parametrize(
    "texto",
    [
        compraste(monto="$６８.６３０,００"),        # dígitos de ancho completo
    ],
)
def test_digitos_no_ascii_no_reconocidos(texto):
    assert extraer(texto) is None


# --- Re-verificación tras la corrección del comercio (commit 0a605ce) --------

def test_regresion_hora_invalida_no_se_rescata_con_texto_adicional():
    texto = compraste(hora="9:5") + " Detalle: con tu T.Deb *1234, el 15/03/2026 a las 09:15."
    assert extraer(texto) is None


def test_regresion_fecha_invalida_no_se_rescata_con_texto_adicional():
    texto = compraste(fecha="15/03/26") + " Recuerda: con tu T.Deb *1234, el 15/03/2026 a las 14:32."
    assert extraer(texto) is None


def test_regresion_rescate_con_saltos_de_linea_y_mayusculas():
    texto = compraste(hora="9:5") + "\nDetalle:\n CON\n\tTU  T.DEB\n*1234,\n el 15/03/2026 A LAS 09:15."
    assert extraer(texto) is None


@pytest.mark.parametrize(
    "texto",
    [
        compraste(fecha="١٥/03/2026"),         # dígitos arábigo-índicos
        transferiste(destino="*５６７８"),      # dígitos de ancho completo
        transferiste(fecha="１５/03/26"),
    ],
)
def test_regresion_digitos_no_ascii(texto):
    assert extraer(texto) is None


@pytest.mark.parametrize("comercio", ["PAN CON TU TIA", "CAFE CON TU T", "CON TU TIENDA"])
def test_comercio_con_frases_parecidas_se_acepta(comercio):
    # " con tu t" sin punto no es ambiguo.
    assert extraer(compraste(comercio=comercio)).descripcion == comercio


@pytest.mark.parametrize(
    "comercio",
    [
        "CAFE CON TU T.V.",
        "cafe con tu t.v.",
        "CAFE\ncon\ntu\nt.v",
        # Decisión de diseño (team leader): un comercio que EMPIEZA por
        # "con tu T." no se distingue de un comercio vacío seguido de otro
        # medio de pago, así que por "nunca adivinar" no se reconoce.
        "CON TU T.V SAS",
        "con tu t.v sas",
    ],
)
def test_comercio_que_contiene_con_tu_t_punto_no_se_reconoce(comercio):
    assert extraer(compraste(comercio=comercio)) is None


def test_comercio_con_otro_medio_de_pago_embebido_no_se_reconoce():
    texto = compraste(comercio="X con tu T.Cred *9999, el 01/01/2026 a las 10:00. Y")
    assert extraer(texto) is None


@pytest.mark.parametrize(
    "fecha, reconocida",
    [("15/03/1999", False), ("01/01/2000", True), ("31/12/2099", True), ("15/03/2100", False)],
)
def test_compraste_rango_de_anios(fecha, reconocida):
    assert (extraer(compraste(fecha=fecha)) is not None) is reconocida


# --- Verificación final: comercio vacío (commit 9f2a8df) ---------------------

@pytest.mark.parametrize("hora", ["9:15", "14:32"])
def test_comercio_vacio_no_se_rescata_con_texto_adicional(hora):
    texto = compraste(comercio="", hora=hora) + " x con tu T.Deb *1234, el 15/03/2026 a las 14:32."
    assert extraer(texto) is None


def test_comercio_vacio_con_otro_medio_de_pago_y_texto_adicional():
    texto = (
        "Bancolombia: Compraste $68.630,00 en con tu T.Cred *1234, el 15/03/2026 a las 14:32."
        " x con tu T.Deb *1234, el 15/03/2026 a las 14:32."
    )
    assert extraer(texto) is None


def test_comercio_solo_caracter_invisible_con_texto_adicional():
    texto = compraste(comercio="\u200b", hora="9:15") + " x con tu T.Deb *1234, el 15/03/2026 a las 14:32."
    assert extraer(texto) is None


def test_comercio_llamado_en():
    assert extraer(compraste(comercio="en")).descripcion == "en"


# --- Verificación final: arreglo de raíz (commit a125885) --------------------

_EXTRA_VALIDO = " x con tu T.Deb *1234, el 15/03/2026 a las 14:32."


def _aviso_hora_mala(tras_en: str) -> str:
    """Aviso con hora mal escrita; ``tras_en`` va entre "en " y " tu T.Deb"."""
    return (
        f"Bancolombia: Compraste $68.630,00 en {tras_en} tu T.Deb *1234, "
        f"el 15/03/2026 a las 9:5." + _EXTRA_VALIDO
    )


@pytest.mark.parametrize(
    "tras_en",
    [
        "MERPAGO*con",          # "con" pegado al comercio
        "MERPAGO​con",     # espacio de ancho cero
        "MERPAGO ​con",
        "MERPAGO con​",
        "MERPAGO⁠con",     # word joiner
        "MERPAGO﻿con",     # BOM
        "MERPAGO᠎con",     # separador de vocales mongol
        "MERPAGO　con",     # espacio ideográfico
        "MERPAGO con",     # separador de línea
        "MERPAGO con",     # espacio no separable
        "con",                  # comercio vacío
    ],
)
def test_aviso_mal_formado_no_se_rescata_con_texto_adicional(tras_en):
    assert extraer(_aviso_hora_mala(tras_en)) is None


def test_con_tu_t_partido_por_saltos_de_linea_no_se_rescata():
    texto = (
        "Bancolombia: Compraste $68.630,00 en MERPAGO con\ntu\nT.\nDeb *1234, "
        "el 15/03/2026 a las 9:5." + _EXTRA_VALIDO
    )
    assert extraer(texto) is None


def test_caracter_invisible_dentro_de_t_punto_no_se_rescata():
    texto = (
        "Bancolombia: Compraste $68.630,00 en MERPAGO con tu T‌.Deb *1234, "
        "el 15/03/2026 a las 9:5." + _EXTRA_VALIDO
    )
    assert extraer(texto) is None


def test_comercio_que_contiene_con_tu_t_pegado_no_se_reconoce():
    assert extraer(compraste(comercio="TIENDAcon tu T.")) is None


@pytest.mark.parametrize("invisible", ["​", "‌", "‍", "⁠", "﻿"])
def test_caracteres_invisibles_se_eliminan_del_comercio(invisible):
    assert extraer(compraste(comercio=f"MER{invisible}PAGO")).descripcion == "MERPAGO"


def test_espacio_ideografico_se_normaliza():
    texto = compraste().replace(" con tu", "　con tu")
    assert extraer(texto).descripcion == "MERPAGO*TIENDA"


# --- Verificación final: guarda estructural del comercio (commit fcdd609) ----

@pytest.mark.parametrize(
    "tramo",
    [
        "MERPAGO c­on tu T.Deb *1234",   # guion suave dentro de "con"
        "MERPAGO con t­u T.Deb *1234",   # guion suave dentro de "tu"
        "MERPAGO con tu T .Deb *1234",        # espacio antes del punto
        "MERPAGO cоn tu T.Deb *1234",    # "o" cirílica
        "MERPAGO con tu T．Deb *1234",    # punto de ancho completo
        "MERPAGO con tu T.Deb * 1234",        # tarjeta con espacio
        "MERPAGO con tu T.Deb *１２３４",  # tarjeta con dígitos de ancho completo
    ],
)
def test_tramo_fijo_distorsionado_no_se_rescata(tramo):
    texto = f"Bancolombia: Compraste $68.630,00 en {tramo}, el 15/03/2026 a las 9:5." + _EXTRA_VALIDO
    assert extraer(texto) is None


@pytest.mark.parametrize("comercio", ["TIENDA 24/7", "CAFÉ 1/2", "LOCAL *12", "COCINA 7/24 SAS"])
def test_comercio_con_fracciones_o_asterisco_corto_se_acepta(comercio):
    assert extraer(compraste(comercio=comercio)).descripcion == comercio


@pytest.mark.parametrize("comercio", ["TIENDA *1234", "EXITO 15/03/26", "BAR 12/12/12"])
def test_comercio_con_estructura_de_tarjeta_o_fecha_no_se_reconoce(comercio):
    assert extraer(compraste(comercio=comercio)) is None


@pytest.mark.parametrize("invisible", ["­", "᠎", "͏"])
def test_otros_invisibles_se_eliminan_del_comercio(invisible):
    assert extraer(compraste(comercio=f"MER{invisible}PAGO")).descripcion == "MERPAGO"


# --- Formatos reales (commit 6f76da5): hora 12 h, centavos, cuenta larga -----

@pytest.mark.parametrize(
    "hora, esperada",
    [
        ("8:29 p. m", (20, 29)),    # espacio no separable
        ("8:29 p. m", (20, 29)),    # espacio fino no separable
        ("8:29 p.  m", (20, 29)),             # espacios repetidos
        ("8:29pm", (20, 29)),
        ("8:29 pM", (20, 29)),
        ("12:00 a. m", (0, 0)),
        ("12:59 a.m", (0, 59)),
        ("0:15", (0, 15)),
    ],
)
def test_hora_12h_variantes_aceptadas(hora, esperada):
    # compraste() añade el punto final: "8:29 p. m" + "." = "8:29 p. m."
    mov = extraer(compraste(hora=hora))
    assert (mov.fecha_hora.hour, mov.fecha_hora.minute) == esperada
    assert extraer(transferiste(hora=hora)).fecha_hora == mov.fecha_hora


@pytest.mark.parametrize(
    "hora",
    ["8:29 p m", "8:29 m", "20:29 p. m", "0:15 a. m", "8:29 pm pm", "8:29 p.m.m", "8:29 hrs", "08:5", "123:00"],
)
def test_hora_12h_variantes_rechazadas(hora):
    assert extraer(compraste(hora=hora)) is None
    assert extraer(transferiste(hora=hora)) is None


@pytest.mark.parametrize(
    "monto, centavos",
    [("$0,01", 1), ("$0,50", 50), ("$1.000,99", 100099)],
)
def test_compraste_centavos(monto, centavos):
    assert extraer(compraste(monto=monto)).monto_centavos == centavos


@pytest.mark.parametrize("monto, centavos", [("$0.01", 1), ("$0.99", 99), ("$6,000.99", 600099)])
def test_transferiste_centavos(monto, centavos):
    assert extraer(transferiste(monto=monto)).monto_centavos == centavos


@pytest.mark.parametrize("monto", ["$00,50", "$,50", "$.50", "$1.000", "$1.000,-", "$1.000,5", "$1.000,505"])
def test_compraste_centavos_mal_formados(monto):
    assert extraer(compraste(monto=monto)) is None


@pytest.mark.parametrize("monto", ["$00.50", "$.50", "$6,000.5", "$6,000.9 9"])
def test_transferiste_centavos_mal_formados(monto):
    assert extraer(transferiste(monto=monto)) is None


_EXTRA_TELEFONOS = " Si tienes dudas llamanos al 6040000000 o 018000000000."


@pytest.mark.parametrize("destino", ["*3000000000", "*" + "1" * 20])
def test_cuenta_destino_larga_con_texto_adicional(destino):
    mov = extraer(transferiste(destino=destino) + _EXTRA_TELEFONOS)
    assert mov.descripcion == "*" + destino[-4:]


@pytest.mark.parametrize(
    "destino",
    ["*" + "1" * 21, "*3000 000000", "*3000000000 018000000000", "*3000000000el"],
)
def test_cuenta_destino_larga_mal_formada(destino):
    assert extraer(transferiste(destino=destino) + _EXTRA_TELEFONOS) is None


def test_cuenta_destino_no_se_toma_del_texto_adicional():
    texto = transferiste() + " a la cuenta *30000000000000000000 el 15/03/26 a las 09:15."
    assert extraer(texto).descripcion == "*5678"


def test_transferiste_hora_mala_no_se_rescata_con_texto_adicional():
    texto = transferiste(hora="9:5") + (
        " Desde tu cuenta *1234 a la cuenta *30000000000 el 15/03/26 a las 09:15."
    )
    assert extraer(texto) is None
