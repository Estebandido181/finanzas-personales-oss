"""Pruebas del extractor de avisos de Bancolombia.

Todos los avisos son inventados: tarjetas y cuentas tipo *1234, *5678, *0000.
"""

from datetime import datetime
from pathlib import Path

import pytest

from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import (
    MovimientoExtraido,
    extraer,
    extraer_compraste,
    extraer_transferiste,
)
from tests.soporte.extractor import transferiste  # ayudas compartidas

AVISOS = Path(__file__).resolve().parents[2] / "fixtures" / "avisos"


def leer(nombre: str) -> str:
    return (AVISOS / nombre).read_text(encoding="utf-8")


def compraste(monto="$68.630,00", comercio="MERPAGO*TIENDA", fecha="15/03/2026", hora="14:32"):
    return (
        f"Bancolombia: Compraste {monto} en {comercio} con tu T.Deb *1234, "
        f"el {fecha} a las {hora}."
    )




# --- Avisos completos (fixtures) ---------------------------------------------

@pytest.mark.parametrize(
    "archivo, esperado",
    [
        (
            "compraste_merpago.txt",
            MovimientoExtraido("compra", 6863000, datetime(2026, 3, 15, 14, 32), "MERPAGO*TIENDA"),
        ),
        (
            "compraste_monto_grande.txt",
            MovimientoExtraido("compra", 123456700, datetime(2025, 12, 1, 8, 5, 9), "D1 SAS"),
        ),
        (
            "compraste_saltos_linea.txt",
            MovimientoExtraido("compra", 4590000, datetime(2028, 2, 29, 23, 59), "PANADERÍA LA ESPIGA"),
        ),
        (
            "transferiste_basico.txt",
            MovimientoExtraido("transferencia", 600000, datetime(2026, 3, 15, 9, 15), "*5678"),
        ),
        (
            "transferiste_monto_grande.txt",
            MovimientoExtraido("transferencia", 123456700, datetime(2025, 12, 31, 18, 40, 22), "*0000"),
        ),
        (
            "compraste_formato_real.txt",
            MovimientoExtraido(
                "compra", 24570000, datetime(2026, 8, 7, 16, 42), "MERPAGO*TIENDAEJEMPLO"
            ),
        ),
        (
            "transferiste_formato_real.txt",
            MovimientoExtraido(
                "transferencia", 450000, datetime(2026, 8, 14, 19, 5), "*0000"
            ),
        ),
    ],
)
def test_avisos_reconocidos(archivo, esperado):
    assert extraer(leer(archivo)) == esperado


# D12 / ítem 09: "Recibiste una transferencia por $... de ... en tu cuenta **dddd,
# el dd/mm/aaaa ..." ya se reconoce (ver test_recibiste.py). Este fixture es OTRA
# redacción ("Recibiste un pago de ...", cuenta con un asterisco, fecha dd/mm/aa,
# sin quien envía), así que sigue siendo "no reconocido" a propósito.
@pytest.mark.parametrize(
    "archivo",
    ["no_reconocido_recibiste.txt", "no_reconocido_compraste_monto_transferencia.txt"],
)
def test_avisos_no_reconocidos(archivo):
    assert extraer(leer(archivo)) is None


def test_extractores_especificos_no_se_cruzan():
    assert extraer_transferiste(leer("compraste_merpago.txt")) is None
    assert extraer_compraste(leer("transferiste_basico.txt")) is None


# --- Compraste: variantes ----------------------------------------------------

@pytest.mark.parametrize(
    "monto, esperado",
    [
        ("$68.630,00", 6863000),
        ("$500,00", 50000),
        ("$1.000,00", 100000),
        ("$1.234.567,00", 123456700),
        ("$68.630,50", 6863050),     # centavos distintos de 00
        ("$1.000,50", 100050),
        ("$0,50", 50),
        ("$0,01", 1),
        ("$1.234.567,89", 123456789),
    ],
)
def test_compraste_montos(monto, esperado):
    assert extraer_compraste(compraste(monto=monto)).monto_centavos == esperado


@pytest.mark.parametrize(
    "comercio",
    ["MERPAGO*TIENDA", "D1 SAS", "PAYU*NETFLIX", "DROGUERÍA SAN JOSÉ", "A&B CAFÉ-BAR 2/3", "RAPPI.COM"],
)
def test_compraste_comercios_especiales(comercio):
    assert extraer_compraste(compraste(comercio=comercio)).descripcion == comercio


def test_compraste_hora_con_segundos():
    mov = extraer_compraste(compraste(hora="07:08:09"))
    assert mov.fecha_hora == datetime(2026, 3, 15, 7, 8, 9)


def test_compraste_tolerancias_inocuas():
    texto = "  COMPRASTE   $68.630,00\ten MERPAGO*TIENDA\n\ncon tu t.deb *1234,  el 15/03/2026 A LAS 14:32.  "
    assert extraer_compraste(texto) == MovimientoExtraido(
        "compra", 6863000, datetime(2026, 3, 15, 14, 32), "MERPAGO*TIENDA"
    )


@pytest.mark.parametrize(
    "texto",
    [
        compraste(monto="$6,000.00"),        # formato de transferencia
        compraste(monto="$68.630,5"),        # un solo decimal
        compraste(monto="$68.630,500"),      # tres decimales
        compraste(monto="$68.63,00"),        # miles mal agrupados
        compraste(monto="$68630,00"),        # sin separador de miles
        compraste(monto="$068.630,00"),      # cero a la izquierda
        compraste(monto="$0,00"),            # monto 0
        compraste(monto="68.630,00"),        # sin signo $
        compraste(fecha="31/02/2026"),       # fecha imposible
        compraste(fecha="15/03/26"),         # año de 2 dígitos
        compraste(fecha="15-03-2026"),       # separador distinto
        compraste(hora="25:00"),             # hora imposible
        compraste(hora="9:5"),               # minutos sin dos dígitos
        compraste(comercio=" "),             # comercio vacío (lo rechaza el patrón)
        compraste().replace("*1234", "*12"),  # tarjeta incompleta
        compraste().replace("T.Deb", "T.Cred"),  # otro medio de pago
        compraste().rstrip("."),             # sin punto final
        "",
        "Hola, este es un correo cualquiera.",
    ],
)
def test_compraste_no_reconocido(texto):
    assert extraer_compraste(texto) is None
    assert extraer(texto) is None


# --- Transferiste: variantes -------------------------------------------------

@pytest.mark.parametrize(
    "monto, esperado",
    [
        ("$6,000.00", 600000),
        ("$4,500.00", 450000),
        ("$500.00", 50000),
        ("$1,234,567.00", 123456700),
        ("$6,000.50", 600050),       # centavos distintos de 00
        ("$0.50", 50),
        ("$1,234,567.89", 123456789),
    ],
)
def test_transferiste_montos(monto, esperado):
    assert extraer_transferiste(transferiste(monto=monto)).monto_centavos == esperado


@pytest.mark.parametrize(
    "fecha, esperada",
    [("15/03/26", datetime(2026, 3, 15, 9, 15)), ("01/01/00", datetime(2000, 1, 1, 9, 15))],
)
def test_transferiste_fecha_dos_digitos(fecha, esperada):
    assert extraer_transferiste(transferiste(fecha=fecha)).fecha_hora == esperada


def test_transferiste_sin_prefijo_y_con_texto_adicional():
    texto = transferiste().removeprefix("Bancolombia: ") + " Si tienes dudas, llamanos."
    assert extraer(texto) == MovimientoExtraido(
        "transferencia", 600000, datetime(2026, 3, 15, 9, 15), "*5678"
    )


@pytest.mark.parametrize(
    "texto",
    [
        transferiste(monto="$6.000,00"),     # formato de compra
        transferiste(monto="$6,000.5"),      # un solo decimal
        transferiste(monto="$6,000.500"),    # tres decimales
        transferiste(monto="$0.00"),         # monto 0,00
        transferiste(monto="$6,00.00"),      # miles mal agrupados
        transferiste(monto="$6000.00"),      # sin separador de miles
        transferiste(monto="$0.00"),         # monto 0
        transferiste(fecha="15/03/2026"),    # año de 4 dígitos
        transferiste(fecha="30/02/26"),      # fecha imposible
        transferiste(hora="24:00"),          # hora imposible
        transferiste(hora="09:60"),          # minuto imposible
        transferiste().replace("*5678", "5678"),  # cuenta destino sin *
    ],
)
def test_transferiste_no_reconocido(texto):
    assert extraer_transferiste(texto) is None
    assert extraer(texto) is None


def test_movimiento_es_inmutable():
    mov = extraer(transferiste())
    with pytest.raises(AttributeError):
        mov.monto_centavos = 1


# --- Correcciones tras revisión ----------------------------------------------

def _compraste_desde(texto_inicial: str) -> str:
    """Añade un texto adicional que repite el final de un aviso válido."""
    return texto_inicial + " Otro con tu T.Deb *1234, el 02/01/2026 a las 11:00."


@pytest.mark.parametrize(
    "texto",
    [
        # El final del aviso no encaja; no debe "rescatarse" con una
        # repetición del final que aparezca en el texto adicional.
        _compraste_desde(
            "Compraste $1.000,00 en TIENDA con tu T.Deb *12345, el 01/01/2026 a las 10:00."
        ),
        _compraste_desde(
            "Compraste $1.000,00 en TIENDA con tu T.Cred *1234, el 01/01/2026 a las 10:00."
        ),
        compraste(hora="9:5") + " Detalle: con tu T.Deb *1234, el 15/03/2026 a las 09:15.",
        compraste(fecha="15/03/26") + " Recuerda: con tu T.Deb *1234, el 15/03/2026 a las 14:32.",
    ],
)
def test_compraste_comercio_no_se_come_el_texto_adicional(texto):
    assert extraer(texto) is None


@pytest.mark.parametrize("hora", ["9:15", "14:32"])
def test_compraste_comercio_vacio_no_se_rescata_con_texto_adicional(hora):
    # Con comercio vacío queda "en con tu T.Deb ..."; el comercio no puede
    # empezar por "con tu T." y alargarse hasta la repetición del final.
    texto = compraste(comercio=" ", hora=hora) + " x con tu T.Deb *1234, el 15/03/2026 a las 09:15."
    assert extraer(texto) is None


@pytest.mark.parametrize(
    "texto",
    [
        compraste(fecha="١٥/03/2026"),                       # dígitos arábigo-índicos
        compraste(fecha="15/03/２０２６"),                     # dígitos de ancho completo
        transferiste().replace("*5678", "*５６７８"),          # cuenta destino no ASCII
        transferiste(fecha="١٥/03/26"),                       # fecha no ASCII
    ],
)
def test_digitos_no_ascii_no_reconocidos(texto):
    assert extraer(texto) is None


@pytest.mark.parametrize("fecha", ["15/03/0001", "15/03/1999", "15/03/2100", "15/03/9999"])
def test_compraste_anio_fuera_de_2000_2099(fecha):
    assert extraer_compraste(compraste(fecha=fecha)) is None


@pytest.mark.parametrize("fecha, anio", [("15/03/2000", 2000), ("15/03/2099", 2099)])
def test_compraste_anio_en_limites(fecha, anio):
    assert extraer_compraste(compraste(fecha=fecha)).fecha_hora.year == anio


_EXTRA = " x con tu T.Deb *1234, el 15/03/2026 a las 14:32."


@pytest.mark.parametrize(
    "antes",
    [
        "MERPAGO*con",           # sin espacio antes de "con"
        "MERPAGO\u200bcon",      # espacio de ancho cero en lugar de espacio
        "MERPAGO \u200bcon",     # espacio de ancho cero tras el espacio
        "MERPAGO con\u200b",     # espacio de ancho cero dentro de "con tu"
    ],
)
def test_compraste_con_tu_t_sin_espacio_normal_no_se_rescata(antes):
    texto = (
        f"Bancolombia: Compraste $68.630,00 en {antes} tu T.Deb *1234, "
        "el 15/03/2026 a las 9:5." + _EXTRA
    )
    assert extraer(texto) is None


def test_compraste_comercio_con_ancho_cero_se_limpia():
    mov = extraer_compraste(compraste(comercio="TIENDA\u200b"))
    assert mov.descripcion == "TIENDA"


@pytest.mark.parametrize(
    "tramo",
    [
        "MERPAGO c\u00adon tu T.Deb",      # guion suave dentro de "con"
        "MERPAGO con t\u00adu T.Deb",      # guion suave dentro de "tu"
        "MERPAGO con\u200e tu T.Deb",      # marca de dirección izquierda-derecha
        "MERPAGO con\u2062 tu T.Deb",      # multiplicación invisible
        "MERPAGO con\u180e tu T.Deb",      # separador de vocal mongol
        "MERPAGO con\u034f tu T.Deb",      # combining grapheme joiner
        "MERPAGO con tu T .Deb",            # espacio antes del punto
        "MERPAGO c\u043en tu T.Deb",       # "o" cirílica
        "MERPAGO con tu T\uff0eDeb",       # punto de ancho completo
    ],
)
def test_compraste_tramo_fijo_distorsionado_no_se_rescata(tramo):
    texto = (
        f"Bancolombia: Compraste $68.630,00 en {tramo} *1234, "
        "el 15/03/2026 a las 9:5." + _EXTRA
    )
    assert extraer(texto) is None


def test_compraste_guion_suave_caso_revisor():
    texto = (
        "Compraste $1.000,00 en X con\u00ad tu T.Deb *1234, el 01/01/2026 a las 9:0. "
        "Otro con tu T.Deb *1234, el 02/01/2026 a las 11:00."
    )
    assert extraer(texto) is None


@pytest.mark.parametrize(
    "comercio",
    ["MERPAGO*TIENDA", "PAYU*NETFLIX", "A&B CAFÉ-BAR 2/3", "D1 SAS", "PAYU*123", "TIENDA 15/03"],
)
def test_compraste_guarda_estructural_no_rechaza_comercios_legitimos(comercio):
    assert extraer_compraste(compraste(comercio=comercio)).descripcion == comercio


@pytest.mark.parametrize("comercio", ["PAYU*1234", "TIENDA*00001", "TIENDA 15/03/26", "TIENDA 15/03/2026"])
def test_compraste_comercio_con_tarjeta_o_fecha_no_se_reconoce(comercio):
    # Consecuencia aceptada de la guarda estructural.
    assert extraer_compraste(compraste(comercio=comercio)) is None


def test_normalizar_quita_invisibles_de_formato():
    mov = extraer_compraste(compraste(comercio="TIEN\u00adDA\u200e\u034f"))
    assert mov.descripcion == "TIENDA"



# --- Formatos reales: cuenta destino y hora ---------------------------------

@pytest.mark.parametrize("destino", ["*5678", "*3000000000", "*" + "1" * 20])
def test_transferiste_cuenta_destino_4_a_20_digitos(destino):
    texto = transferiste().replace("*5678", destino)
    assert extraer_transferiste(texto).descripcion == "*" + destino[-4:]


@pytest.mark.parametrize("destino", ["*" + "1" * 21, "*123"])
def test_transferiste_cuenta_destino_fuera_de_rango(destino):
    assert extraer(transferiste().replace("*5678", destino)) is None


def test_transferiste_cuenta_origen_sigue_siendo_4_digitos():
    texto = transferiste().replace("desde tu cuenta *1234", "desde tu cuenta *12345")
    assert extraer(texto) is None


_HORAS_VALIDAS = [
    ("9:15", (9, 15, 0)),
    ("09:15", (9, 15, 0)),
    ("0:05", (0, 5, 0)),
    ("23:59:59", (23, 59, 59)),
    ("8:29 p. m.", (20, 29, 0)),
    ("8:29 a. m.", (8, 29, 0)),
    ("08:29 p.m.", (20, 29, 0)),
    ("8:29 a.m.", (8, 29, 0)),
    ("8:29 pm", (20, 29, 0)),
    ("8:29am", (8, 29, 0)),
    ("8:29 AM", (8, 29, 0)),
    ("8:29 PM", (20, 29, 0)),
    ("8:29 P. M.", (20, 29, 0)),
    ("8:29p.m.", (20, 29, 0)),
    ("8:29:07 p. m.", (20, 29, 7)),
    ("12:00 a. m.", (0, 0, 0)),
    ("12:45 a. m.", (0, 45, 0)),
    ("12:00 p. m.", (12, 0, 0)),
    ("12:45 pm", (12, 45, 0)),
    ("1:05 p. m.", (13, 5, 0)),
    ("11:59 p. m.", (23, 59, 0)),
]


def _con_hora(aviso: str, hora: str) -> str:
    """Pone la hora y el punto final; si el indicador acaba en punto, ese punto
    cierra la oración."""
    final = "" if hora.endswith(".") else "."
    return aviso.rsplit(" a las ", 1)[0] + f" a las {hora}{final} Si tienes dudas, llamanos."


@pytest.mark.parametrize("hora, esperada", _HORAS_VALIDAS)
@pytest.mark.parametrize("aviso", [compraste(), transferiste()], ids=["compraste", "transferiste"])
def test_horas_validas_ambos_avisos(aviso, hora, esperada):
    mov = extraer(_con_hora(aviso, hora))
    assert (mov.fecha_hora.hour, mov.fecha_hora.minute, mov.fecha_hora.second) == esperada


@pytest.mark.parametrize("aviso", [compraste(), transferiste()], ids=["compraste", "transferiste"])
def test_indicador_con_punto_seguido_de_otro_punto(aviso):
    texto = aviso.rsplit(" a las ", 1)[0] + " a las 8:29 p. m.. Si tienes dudas."
    assert extraer(texto).fecha_hora.hour == 20


@pytest.mark.parametrize(
    "hora",
    [
        "0:15 a. m.",      # hora 0 con indicador
        "13:00 p. m.",     # hora 13+ con indicador
        "00:30 pm",
        "24:00",
        "9:5",
        "123:00",
        "8:29 p m.",
        "8:29 pm.m.",
        "8:29 x. m.",
    ],
)
@pytest.mark.parametrize("aviso", [compraste(), transferiste()], ids=["compraste", "transferiste"])
def test_horas_invalidas_ambos_avisos(aviso, hora):
    assert extraer(aviso.rsplit(" a las ", 1)[0] + f" a las {hora}.") is None


@pytest.mark.parametrize("aviso", [compraste(), transferiste()], ids=["compraste", "transferiste"])
def test_indicador_con_punto_pegado_a_texto_no_se_reconoce(aviso):
    # "p. m.Si": falta el espacio tras el punto que cierra la oración.
    assert extraer(aviso.rsplit(" a las ", 1)[0] + " a las 8:29 p. m.Si tienes dudas.") is None


@pytest.mark.parametrize("aviso", [compraste(), transferiste()], ids=["compraste", "transferiste"])
def test_indicador_incompleto_sin_punto_final_no_se_reconoce(aviso):
    # "p. m" sin el punto de "m." ni punto final.
    assert extraer(aviso.rsplit(" a las ", 1)[0] + " a las 8:29 p. m Si tienes dudas.") is None
