"""Pruebas del aviso "transferiste ... a la llave" (Bre-B, formato nuevo).

Todo es inventado: nombres (PERSONA EJEMPLO, NOMBRE DESTINO EJEMPLO, MARÍA
JOSÉ ÑUÑEZ MUÑOZ...), llaves (3000000000...), cuentas (*1234, *5678) y
teléfonos (018000000000).
"""

from __future__ import annotations
from finanzas.bootstrap.saldo import componer_saldo

import json
import logging
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from finanzas import categorizacion, db
from finanzas.modulos.sincronizacion.adaptadores.avisos import extractor
from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import (
    MovimientoExtraido,
    extraer,
    extraer_compraste,
    extraer_recibiste,
    extraer_transferiste,
    extraer_transferiste_llave,
)
from finanzas.gmail import ZONA_COLOMBIA, CorreoGmail, correo_desde_mensaje
from finanzas.sincronizacion import ResultadoSincronizacion, extraer_aviso, sincronizar
from tests.soporte.ayudas_db import sql
from tests.soporte.gmail_falso import LEGITIMO

AVISOS = Path(__file__).resolve().parents[2] / "fixtures" / "avisos"
GMAIL = Path(__file__).resolve().parents[2] / "fixtures" / "gmail"


def leer(nombre: str) -> str:
    return (AVISOS / nombre).read_text(encoding="utf-8")


def llave(
    titular="PERSONA EJEMPLO",
    separador=", ",
    monto="$6,200.00",
    clave="3000000000",
    cuenta="*1234",
    destino="NOMBRE DESTINO EJEMPLO",
    fecha="29/09/26",
    hora="21:28",
    final=". Con Bre-b es de una y gratis. Dudas al 018000000000.",
    prefijo="Bancolombia: ",
):
    return (
        f"{prefijo}{titular}{separador}transferiste {monto} a la llave {clave} "
        f"desde tu cuenta {cuenta} a {destino} el {fecha} a las {hora}{final}"
    )


BASICO = MovimientoExtraido(
    "transferencia", 620000, datetime(2026, 9, 29, 21, 28), "NOMBRE DESTINO EJEMPLO"
)


# --- Extractor: fixtures -----------------------------------------------------------

@pytest.mark.parametrize(
    "archivo, esperado",
    [
        ("transferiste_llave_basico.txt", BASICO),
        (
            "transferiste_llave_monto_grande.txt",
            MovimientoExtraido(
                "transferencia", 1234567890, datetime(2025, 12, 31, 23, 59, 58), "EMPRESA EJEMPLO S.A.S."
            ),
        ),
        (
            "transferiste_llave_hora_12h.txt",
            MovimientoExtraido(
                "transferencia", 4500000, datetime(2026, 10, 1, 20, 5), "OTRA PERSONA EJEMPLO"
            ),
        ),
        (
            "transferiste_llave_nombres_tilde_y_enie.txt",
            MovimientoExtraido(
                "transferencia", 15000, datetime(2027, 1, 5, 7, 30), "MARÍA JOSÉ ÑUÑEZ MUÑOZ"
            ),
        ),
        ("transferiste_llave_texto_final_distinto.txt", BASICO),
    ],
)
def test_avisos_llave_reconocidos(archivo, esperado):
    assert extraer_transferiste_llave(leer(archivo)) == esperado
    assert extraer(leer(archivo)) == esperado


def test_fixture_llave_no_numerica_no_se_reconoce():
    texto = leer("no_reconocido_transferiste_llave_correo.txt")
    assert extraer_transferiste_llave(texto) is None
    assert extraer(texto) is None
    assert extraer_aviso(texto) is None


def test_llave_titular_y_cuenta_no_se_devuelven():
    mov = extraer_transferiste_llave(llave(titular="TITULAR UNICO", clave="3000000007", cuenta="*9876"))
    assert mov is not None
    for dato in ("TITULAR", "3000000007", "9876"):
        assert dato not in repr(mov)


def test_extractores_no_se_cruzan():
    texto = leer("transferiste_llave_basico.txt")
    assert extraer_compraste(texto) is None
    assert extraer_transferiste(texto) is None
    assert extraer_recibiste(texto) is None
    for otro in ("transferiste_basico.txt", "compraste_merpago.txt", "recibiste_basico.txt"):
        assert extraer_transferiste_llave(leer(otro)) is None


# --- Extractor: variantes válidas --------------------------------------------------

@pytest.mark.parametrize(
    "monto, esperado",
    [
        ("$6,200.00", 620000),
        ("$0.50", 50),
        ("$1.00", 100),
        ("$999.99", 99999),
        ("$1,000.00", 100000),
        ("$12,345,678.90", 1234567890),
        ("$1,000,000,000.01", 100000000001),
    ],
)
def test_montos_validos_en_centavos(monto, esperado):
    mov = extraer_transferiste_llave(llave(monto=monto))
    assert mov.monto_centavos == esperado
    assert isinstance(mov.monto_centavos, int)


@pytest.mark.parametrize(
    "hora, esperado",
    [
        ("21:28", (21, 28, 0)),
        ("7:05", (7, 5, 0)),
        ("00:00", (0, 0, 0)),
        ("23:59:59", (23, 59, 59)),
        ("9:28 p. m.", (21, 28, 0)),
        ("12:10 a. m.", (0, 10, 0)),
        ("12:10 p.m.", (12, 10, 0)),
        ("9:15 am", (9, 15, 0)),
        ("9:15PM", (21, 15, 0)),
    ],
)
def test_horas_24_y_12(hora, esperado):
    mov = extraer_transferiste_llave(llave(hora=hora))
    assert (mov.fecha_hora.hour, mov.fecha_hora.minute, mov.fecha_hora.second) == esperado


def test_hora_12h_con_punto_doble_y_sin_texto_adicional():
    for final in (".", ". Con Bre-b es de una y gratis.", " Con Bre-b es de una y gratis."):
        assert extraer_transferiste_llave(llave(hora="9:28 p. m.", final=final)) is not None


@pytest.mark.parametrize(
    "final",
    [".", ". Otro texto cualquiera.", ". Con Bre-B es de una y gratis. 29/09/26 a las 10:00."],
)
def test_texto_final_libre(final):
    assert extraer_transferiste_llave(llave(final=final)) == BASICO


@pytest.mark.parametrize(
    "destino",
    [
        "NOMBRE DESTINO EJEMPLO",
        "MARÍA JOSÉ ÑUÑEZ MUÑOZ",
        "Ángela Úrsula Güiza Íñiguez",
        "O'NEIL-EJEMPLO & CÍA. S.A.S.",
        "PAGOS*EJEMPLO",
        "EMPRESA, EJEMPLO",
        "X",
        "A" * 100,
        "JUAN EL GRANDE",                 # " el " sin fecha detrás
        "PERSONA A LA LLAVE",
    ],
)
def test_nombres_de_quien_recibe_se_devuelven_tal_cual(destino):
    assert extraer_transferiste_llave(llave(destino=destino)).descripcion == destino


@pytest.mark.parametrize(
    "titular",
    # Titular: de 1 a 3 palabras de solo letras, máximo 40 caracteres (ronda 1).
    ["PERSONA EJEMPLO", "JOSÉ ÁLVAREZ PEÑA", "persona ejemplo", "X", "A" * 40],
)
def test_nombres_de_titular_validos(titular):
    assert extraer_transferiste_llave(llave(titular=titular)) == BASICO


def test_tolerancias_inocuas():
    texto = (
        "  bancolombia:   PERSONA\nEJEMPLO,  TRANSFERISTE $6,200.00\tA LA LLAVE 3000000000\n"
        "DESDE TU CUENTA *1234 A NOMBRE   DESTINO EJEMPLO EL 29/09/26 A LAS 21:28.  "
    )
    assert extraer_transferiste_llave(texto) == BASICO


def test_sin_prefijo_y_con_invisibles():
    assert extraer_transferiste_llave(llave(prefijo="")) == BASICO
    texto = llave().replace("transferiste", "transfe​riste").replace("$6", "$­6")
    assert extraer_transferiste_llave(texto) == BASICO


@pytest.mark.parametrize("clave", ["1234", "3" * 20, "3000000000"])
def test_llaves_numericas_de_4_a_20_digitos(clave):
    assert extraer_transferiste_llave(llave(clave=clave)) == BASICO


# --- Llaves alias (@ + 3 a 30 caracteres [A-Za-z0-9._-] ASCII) ---------------------

@pytest.mark.parametrize(
    "clave",
    [
        "@ejemplo12",
        "@ALIASEJEMPLO",
        "@abc",                      # mínimo: 3 caracteres tras la @
        "@" + "a" * 30,              # máximo: 30 caracteres tras la @
        "@persona.ejemplo",
        "@persona-ejemplo",
        "@persona_ejemplo",
        "@a.b_c-9",
        "@123",                      # solo dígitos tras la @
        "@...",                      # solo signos permitidos
        "@ejemplo.",                 # termina en punto
    ],
)
def test_llaves_alias_validas(clave):
    assert extraer_transferiste_llave(llave(clave=clave)) == BASICO
    assert extraer(llave(clave=clave)) == BASICO
    assert extraer_aviso(llave(clave=clave)) == BASICO


def test_fixture_llave_alias():
    texto = leer("transferiste_llave_alias.txt")
    assert extraer_transferiste_llave(texto) == BASICO
    assert extraer(texto) == BASICO
    assert extraer_aviso(texto) == BASICO


def test_fixture_alias_sin_arroba_no_se_reconoce():
    texto = leer("no_reconocido_transferiste_llave_alias_sin_arroba.txt")
    assert extraer_transferiste_llave(texto) is None
    assert extraer(texto) is None
    assert extraer_aviso(texto) is None


@pytest.mark.parametrize(
    "clave",
    [
        "ejemplo12",                 # sin @
        "@",                         # @ sola
        "@ab",                       # menos de 3 caracteres
        "@" + "a" * 31,              # más de 30 caracteres
        "@ejemplo 12",               # con espacio
        "@ ejemplo12",               # espacio tras la @
        "@josé",                     # no ASCII
        "@ñandú",
        "@ｅｊｅｍｐｌｏ",              # letras de ancho completo
        "@ejemplo１２",              # dígitos de ancho completo
        "@@ejemplo12",               # dos @
        "@ejemplo@12",
        "persona@example.com",       # correo
        "@persona.ejemplo@example.com",
        "@ejemplo+12",               # signos fuera de la lista
        "@ejemplo/12",
        "@ejemplo:12",
        "@ejemplo$12",
        "@ejemplo*12",
        "@ejemplo,12",
        "@3000000000 desde tu cuenta *1234",  # llave que intenta repetir la cuenta
    ],
)
def test_llaves_alias_invalidas(clave):
    texto = llave(clave=clave)
    assert extraer_transferiste_llave(texto) is None
    assert extraer(texto) is None
    assert extraer_aviso(texto) is None


def test_alias_no_se_come_cuenta_fecha_ni_hora():
    # La llave no admite espacio: no puede absorber "desde tu cuenta *dddd" ni
    # cruzar a la fecha y la hora del texto adicional.
    sin_cuenta = (
        "Bancolombia: PERSONA EJEMPLO, transferiste $6,200.00 a la llave @ejemplo12 "
        "a NOMBRE DESTINO EJEMPLO el 29/09/26 a las 21:28. Desde tu cuenta *1234."
    )
    assert extraer_transferiste_llave(sin_cuenta) is None
    sin_fecha = llave(clave="@ejemplo12", fecha="29-09-26",
                      final=". Recuerda a NOMBRE el 30/09/26 a las 10:00.")
    assert extraer_transferiste_llave(sin_fecha) is None


def test_alias_no_se_devuelve():
    mov = extraer_transferiste_llave(llave(clave="@aliasinventado9"))
    assert mov == BASICO
    assert "aliasinventado9" not in repr(mov)


def test_el_pago_qr_sigue_sin_aceptar_alias():
    texto = ("Bancolombia: NOMBRE COMPLETO DE EJEMPLO pagaste $12,000.00 por codigo QR desde tu "
             "cuenta *1234 a la llave @ejemplo12 el 10/09/2026 a las 11:20.")
    assert extraer(texto) is None
    assert extraer(texto.replace("@ejemplo12", "3000000000")) is not None


def test_solo_se_toma_el_primer_aviso():
    texto = llave(final=". " + llave(monto="$999,999.00", destino="OTRA PERSONA"))
    assert extraer_transferiste_llave(texto) == BASICO


# --- Extractor: rechazos -------------------------------------------------------------

@pytest.mark.parametrize(
    "texto",
    [
        # Llave no numérica o fuera de rango
        llave(clave="persona.ejemplo@example.com"),
        llave(clave="ALIASEJEMPLO"),
        llave(clave="300-000-0000"),
        llave(clave="300 000 0000"),
        llave(clave="+573000000000"),
        llave(clave="3000000000A"),
        llave(clave="123"),
        llave(clave="3" * 21),
        llave(clave="３０００００００００"),        # dígitos de ancho completo
        llave(clave=""),
        # Titular
        llave(separador=" "),                  # sin coma tras el titular
        llave(separador=" , "),
        llave(separador=","),                  # coma pegada a "transferiste"
        llave(titular=""),                     # vacío
        llave(titular="A" * 41),               # más de 40 caracteres
        llave(titular="O'NEIL-EJEMPLO"),       # signos en el titular
        llave(titular="PERSONA EJEMPLO."),     # punto en el titular
        llave(titular="ANA MARIA PEREZ GOMEZ"),  # más de 3 palabras
        llave(titular="PERSONA 2"),            # dígito
        llave(titular="PERSONA, OTRA"),        # coma dentro del titular
        llave(titular="PERSONA COMPRASTE"),
        llave(titular="PERSONA: EJEMPLO"),
        llave(titular="-PERSONA"),             # no empieza por letra
        # Monto
        llave(monto="$6.200,00"),              # formato de "Compraste"
        llave(monto="$6,200"),                 # sin decimales
        llave(monto="$6,200.0"),               # 1 decimal
        llave(monto="$6,200.000"),             # 3 decimales
        llave(monto="$62,00.00"),              # miles mal agrupados
        llave(monto="$6200.00"),               # sin separador de miles
        llave(monto="$06,200.00"),             # cero a la izquierda
        llave(monto="$0.00"),                  # cero
        llave(monto="$-6,200.00"),
        llave(monto="6,200.00"),               # sin $
        llave(monto="$ 6,200.00"),
        llave(monto="$６,２００.００"),
        # Cuenta origen
        llave(cuenta="*123"),
        llave(cuenta="*12345"),
        llave(cuenta="**1234"),
        llave(cuenta="1234"),
        # Quien recibe
        llave(destino=""),
        llave(destino="A" * 101),
        llave(destino="PERSONA 3000000000"),   # dígitos
        llave(destino="PERSONA *1234"),
        llave(destino="PERSONA: EJEMPLO"),
        llave(destino="PERSONA TRANSFERISTE"),
        llave(destino="RECIBISTE PERSONA"),
        llave(destino=".PERSONA"),             # no empieza por letra
        # Fecha y hora
        llave(fecha="29/09/2026"),             # dd/mm/aaaa
        llave(fecha="31/02/26"),               # fecha imposible
        llave(fecha="29/13/26"),
        llave(fecha="29-09-26"),
        llave(fecha="9/9/26"),
        llave(hora="25:00"),
        llave(hora="21:60"),
        llave(hora="13:00 p. m."),
        llave(hora="0:30 a. m."),
        llave(hora="21"),
        # Estructura
        llave(final=""),                       # sin punto final
        llave(final=" Con Bre-b."),            # texto pegado a la hora sin punto
    ],
)
def test_variantes_invalidas_no_se_reconocen(texto):
    assert extraer_transferiste_llave(texto) is None
    assert extraer(texto) is None
    assert extraer_aviso(texto) is None


@pytest.mark.parametrize(
    "texto",
    [
        # Falta "desde tu cuenta *dddd".
        "Bancolombia: PERSONA EJEMPLO, transferiste $6,200.00 a la llave 3000000000 "
        "a NOMBRE DESTINO EJEMPLO el 29/09/26 a las 21:28. Con Bre-b es de una y gratis.",
        # "desde tu cuenta" sin la cuenta.
        "Bancolombia: PERSONA EJEMPLO, transferiste $6,200.00 a la llave 3000000000 desde tu cuenta "
        "a NOMBRE DESTINO EJEMPLO el 29/09/26 a las 21:28.",
        # Otro orden: el caso de test_sincronizacion_bordes.py ("llave") sigue sin reconocerse.
        "Bancolombia: Transferiste $6,000.00 desde tu cuenta *1234 a la llave 3000000000 el 15/08/26 a las 09:15.",
        "Bancolombia: PERSONA EJEMPLO, transferiste $6,200.00 desde tu cuenta *1234 a la llave 3000000000 "
        "a NOMBRE DESTINO EJEMPLO el 29/09/26 a las 21:28.",
        # Sin quien recibe.
        "Bancolombia: PERSONA EJEMPLO, transferiste $6,200.00 a la llave 3000000000 desde tu cuenta *1234 "
        "el 29/09/26 a las 21:28.",
        # Sin "a la" antes de "llave".
        "Bancolombia: PERSONA EJEMPLO, transferiste $6,200.00 llave 3000000000 desde tu cuenta *1234 "
        "a NOMBRE DESTINO EJEMPLO el 29/09/26 a las 21:28.",
        # Sin hora.
        "Bancolombia: PERSONA EJEMPLO, transferiste $6,200.00 a la llave 3000000000 desde tu cuenta *1234 "
        "a NOMBRE DESTINO EJEMPLO el 29/09/26.",
        # Sin titular.
        "Bancolombia: transferiste $6,200.00 a la llave 3000000000 desde tu cuenta *1234 "
        "a NOMBRE DESTINO EJEMPLO el 29/09/26 a las 21:28.",
        # No está al inicio.
        "¡Hola PERSONA EJEMPLO, transferiste $6,200.00 a la llave 3000000000 desde tu cuenta *1234 "
        "a NOMBRE DESTINO EJEMPLO el 29/09/26 a las 21:28.",
    ],
    ids=["sin_desde_tu_cuenta", "cuenta_vacia", "orden_de_bordes", "orden_cambiado", "sin_destino",
         "sin_a_la", "sin_hora", "sin_titular", "no_al_inicio"],
)
def test_otras_redacciones_no_se_reconocen(texto):
    assert extraer(texto) is None
    assert extraer_aviso(texto) is None


def test_quien_recibe_no_cruza_la_fecha_deformada():
    """Si la fecha propia viene deformada, el nombre no puede extenderse hasta
    una fecha válida del texto adicional (no admite dígitos)."""
    texto = llave(fecha="29-09-26", final=". Recuerda a NOMBRE el 30/09/26 a las 10:00.")
    assert extraer_transferiste_llave(texto) is None


# --- extraer_aviso (búsqueda dentro del correo) ------------------------------------------

def test_extraer_aviso_con_encabezado_y_texto_final():
    texto = "¡Listo! Todo salió bien con tus movimientos\n\n" + llave() + "\n\nOtro texto."
    assert extraer_aviso(texto) == BASICO


def test_extraer_aviso_exige_el_prefijo():
    """Como con los demás avisos (decisión del dueño, ronda 3)."""
    assert extraer_aviso(llave(prefijo="")) is None
    assert extraer_aviso("Encabezado. " + llave(prefijo="")) is None


def test_extraer_aviso_span_pegado_y_sin_espacio_tras_los_dos_puntos():
    # ítem 21: antes se reconocía; ahora queda no reconocido porque "Alertas"
    # no es un encabezado de plantilla conocido (el aviso estaría citado).
    assert extraer_aviso("Alertas" + llave()) is None
    # Igual que en los demás avisos, el extractor exige el espacio tras "Bancolombia:".
    assert extraer_aviso("Alertas" + llave(prefijo="Bancolombia:")) is None


def test_extraer_aviso_no_cruza_a_otro_aviso():
    texto = llave(clave="ALIAS", monto="$999,999.00", destino="FALSO") + " " + llave()
    # ítem 21: antes se reconocía el segundo aviso; ahora queda no reconocido
    # porque el segundo tiene delante otro texto (el primero): está citado.
    assert extraer_aviso(texto) is None


# --- Sincronización de extremo a extremo --------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "llave.db"))
    db.inicializar(conexion)
    componer_saldo(conexion).configurar(100000000, date(2026, 9, 1))
    yield conexion
    conexion.close()


class Cliente:
    def __init__(self, correos):
        self.correos = {c.gmail_id: c for c in correos}
        self.llamadas_obtener = []

    def listar_ids(self, desde):
        return list(self.correos)

    def obtener(self, gmail_id):
        self.llamadas_obtener.append(gmail_id)
        return self.correos[gmail_id]


def _correo_fixture() -> CorreoGmail:
    return correo_desde_mensaje(
        json.loads((GMAIL / "transferiste_llave_html.json").read_text(encoding="utf-8"))
    )


def _correo(gmail_id, texto, **encabezados) -> CorreoGmail:
    return CorreoGmail(
        gmail_id,
        datetime(2026, 9, 29, 21, 29, tzinfo=ZONA_COLOMBIA),
        "Alerta (ejemplo)",
        texto,
        **{**LEGITIMO, **encabezados},
    )


def _movimientos(conn):
    return [dict(f) for f in sql(
        conn,
        "SELECT fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, gmail_id "
        "FROM movimientos ORDER BY id",
    )]


def _contar(conn, tabla):
    return sql(conn, f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]


def _primera_categoria(conn) -> int:
    return sql(conn, "SELECT id FROM categorias ORDER BY id LIMIT 1").fetchone()[0]


def test_fixture_gmail_html_con_span_resaltado():
    correo = _correo_fixture()
    assert "<span" not in correo.textos[0]
    assert "Bancolombia: PERSONA EJEMPLO, transferiste" in correo.textos[0]
    assert extraer_aviso(correo.textos[0]) == BASICO


def test_sincronizar_crea_transferencia_sin_categorizar_y_no_duplica(conn):
    primero = sincronizar(conn, Cliente([_correo_fixture()]))

    assert primero == ResultadoSincronizacion(nuevos=1)
    assert _movimientos(conn) == [{
        "fecha_hora": "2026-09-29T21:28:00",
        "monto_centavos": 620000,
        "tipo": "transferencia",
        "descripcion": "NOMBRE DESTINO EJEMPLO",
        "categoria_id": None,
        "origen": "gmail",
        "gmail_id": "msg-llave-0001",
    }]
    # Sin regla queda en la bandeja "Sin categorizar" y cuenta como gasto.
    assert [f["descripcion"] for f in categorizacion.sin_categorizar(conn)] == ["NOMBRE DESTINO EJEMPLO"]
    assert componer_saldo(conn).saldo_actual() == 100000000 - 620000
    assert componer_saldo(conn).gasto_entre(datetime(2026, 9, 1), datetime(2026, 10, 1)) == 620000

    segundo_cliente = Cliente([_correo_fixture()])
    assert sincronizar(conn, segundo_cliente) == ResultadoSincronizacion()
    assert segundo_cliente.llamadas_obtener == []
    assert _contar(conn, "movimientos") == 1


def test_regla_de_cuenta_destino_con_el_nombre_la_categoriza(conn):
    """Las transferencias usan reglas de campo ``cuenta_destino`` comparadas por
    igualdad con la descripción normalizada; en las de llave la descripción es
    el nombre de quien recibe, así que la regla guarda ese nombre."""
    categoria_id = _primera_categoria(conn)
    with db.transaccion(conn):
        sql(
            conn,
            "INSERT INTO reglas (campo, texto, categoria_id) VALUES (?, ?, ?)",
            ("cuenta_destino", categorizacion.normalizar("Nombre Destino Ejemplo"), categoria_id),
        )
    sincronizar(conn, Cliente([_correo_fixture()]))

    assert _movimientos(conn)[0]["categoria_id"] == categoria_id
    assert categorizacion.contar_sin_categorizar(conn) == 0


def test_regla_de_comercio_no_aplica_a_transferencias(conn):
    with db.transaccion(conn):
        sql(
            conn,
            "INSERT INTO reglas (campo, texto, categoria_id) VALUES (?, ?, ?)",
            ("comercio", categorizacion.normalizar("NOMBRE DESTINO EJEMPLO"), _primera_categoria(conn)),
        )
    sincronizar(conn, Cliente([_correo_fixture()]))

    assert _movimientos(conn)[0]["categoria_id"] is None


def test_recordar_desde_la_bandeja_categoriza_la_siguiente_transferencia(conn):
    sincronizar(conn, Cliente([_correo_fixture()]))
    movimiento_id = sql(conn, "SELECT id FROM movimientos").fetchone()[0]
    categoria_id = _primera_categoria(conn)
    categorizacion.asignar_categoria(conn, movimiento_id, categoria_id, recordar=True)

    reglas = [(r["campo"], r["texto"]) for r in categorizacion.listar_reglas(conn)]
    assert reglas == [("cuenta_destino", "nombre destino ejemplo")]

    otro = _correo("llave-2", llave(monto="$10,000.00", hora="22:00"))
    sincronizar(conn, Cliente([otro]))
    fila = sql(conn, "SELECT categoria_id FROM movimientos WHERE gmail_id = 'llave-2'").fetchone()
    assert fila[0] == categoria_id


def test_llave_no_numerica_por_gmail_queda_no_reconocida(conn):
    correo = _correo("llave-correo", leer("no_reconocido_transferiste_llave_correo.txt"))
    assert sincronizar(conn, Cliente([correo])) == ResultadoSincronizacion(no_reconocidos=1)
    assert _contar(conn, "movimientos") == 0


def test_correo_no_autenticado_no_crea_transferencia(conn):
    correo = _correo("llave-falso", llave(), remitente="alertas@ejemplo-falso.com")
    assert sincronizar(conn, Cliente([correo])) == ResultadoSincronizacion(rechazados_autenticacion=1)
    assert _contar(conn, "movimientos") == 0


def test_reprocesar_un_no_reconocido_con_este_formato(conn, monkeypatch):
    """Procedimiento del README: el correo quedó como "no reconocido" antes de
    este arreglo; se borra su fila de ``correos_no_reconocidos`` y se vuelve a
    sincronizar."""
    # 1. Antes del arreglo: sin el extractor nuevo, el correo queda no reconocido.
    with monkeypatch.context() as m:
        m.setattr(
            extractor,
            "_EXTRACTORES",
            (extractor.extraer_compraste, extractor.extraer_transferiste, extractor.extraer_recibiste),
        )
        assert sincronizar(conn, Cliente([_correo_fixture()])) == ResultadoSincronizacion(no_reconocidos=1)
    assert _contar(conn, "movimientos") == 0
    assert _contar(conn, "correos_no_reconocidos") == 1

    # 2. Mientras siga en correos_no_reconocidos no se vuelve a descargar.
    cliente = Cliente([_correo_fixture()])
    assert sincronizar(conn, cliente) == ResultadoSincronizacion()
    assert cliente.llamadas_obtener == []

    # 3. DELETE FROM correos_no_reconocidos WHERE gmail_id = '...' y sincronizar.
    with db.transaccion(conn):
        sql(conn, "DELETE FROM correos_no_reconocidos WHERE gmail_id = ?", ("msg-llave-0001",))
    assert sincronizar(conn, Cliente([_correo_fixture()])) == ResultadoSincronizacion(nuevos=1)
    assert _movimientos(conn)[0]["descripcion"] == "NOMBRE DESTINO EJEMPLO"
    assert _contar(conn, "correos_no_reconocidos") == 0

    # 4. Otra sincronización no duplica.
    assert sincronizar(conn, Cliente([_correo_fixture()])) == ResultadoSincronizacion()
    assert _contar(conn, "movimientos") == 1


def test_logs_no_incluyen_nombres_monto_llave_ni_cuenta(conn, caplog):
    correos = [
        _correo_fixture(),
        _correo("llave-2", llave(titular="JOSÉ ÁLVAREZ PEÑA", destino="MARÍA ÑUÑEZ", monto="$777,777.77")),
        _correo("llave-3", llave(clave="ALIASEJEMPLO")),
    ]
    with caplog.at_level(logging.DEBUG):
        resultado = sincronizar(conn, Cliente(correos))

    assert resultado == ResultadoSincronizacion(nuevos=2, no_reconocidos=1)
    for prohibido in (
        "PERSONA EJEMPLO", "NOMBRE DESTINO", "JOSÉ", "MARÍA", "ÑUÑEZ", "ALIASEJEMPLO",
        "3000000000", "6,200", "620000", "777,777", "*1234", "transferiste", "Bancolombia:",
    ):
        assert prohibido not in caplog.text, prohibido


def test_transferencia_anterior_a_la_fecha_de_inicio_se_descarta(conn):
    correo = replace(_correo_fixture(), fecha=datetime(2026, 8, 31, 23, 59, tzinfo=ZONA_COLOMBIA))
    assert sincronizar(conn, Cliente([correo])) == ResultadoSincronizacion()
    assert _contar(conn, "movimientos") == 0


def test_titular_con_espacio_antes_de_la_coma_no_se_reconoce():
    assert extraer_transferiste_llave(llave(separador=" , ")) is None


def test_sin_prefijo_el_extractor_lo_lee_pero_la_sincronizacion_no():
    """El extractor tolera la falta de "Bancolombia:" (como en los demás
    avisos), así que un saludo delante queda como parte del titular, que no se
    guarda. En la sincronización el prefijo es obligatorio: sin él, no
    reconocido."""
    texto = "Hola " + llave(prefijo="")
    assert extraer(texto) == BASICO
    assert extraer_aviso(texto) is None
