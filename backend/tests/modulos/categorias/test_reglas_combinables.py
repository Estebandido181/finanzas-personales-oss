"""Reglas con condiciones combinables (ítem 17): coincidencia, prioridad y aplicación.

Una regla es tipo + texto exacto (opcional) + monto exacto (opcional), con al
menos una condición además del tipo. Gana la más específica: texto + monto >
texto > monto. Todos los datos son inventados.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from finanzas import categorizacion, db
from finanzas.categorizacion import (
    CondicionesRegla,
    asignar_categoria,
    asignar_con_detalle,
    condiciones_de_regla,
    especificidad,
    frase_condiciones,
    frase_regla,
    pesos,
    regla_que_coincide,
    reglas_posibles,
)
from finanzas.gmail import ZONA_COLOMBIA, CorreoGmail
from finanzas.sincronizacion import ResultadoSincronizacion, reprocesar, sincronizar
from tests.soporte.ayudas_db import sql
from tests.soporte.gmail_falso import LEGITIMO, ClienteFalso
from tests.soporte.reproceso import _sincronizar_inicial, corregir_lector  # noqa: F401 (fixture)

BUS = 320000  # $3.200


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "reglas-combinables.db"))
    db.inicializar(conexion)
    with db.transaccion(conexion):
        sql(
            conexion,
            "INSERT INTO configuracion_saldo (id, saldo_inicial_centavos, fecha_inicio) "
            "VALUES (1, 100000000, '2026-08-01')",
        )
    yield conexion
    conexion.close()


def _cat(conn, nombre):
    return sql(conn, "SELECT id FROM categorias WHERE nombre = ?", (nombre,)).fetchone()[0]


def _regla(conn, campo, texto, monto, categoria_id) -> int:
    with db.transaccion(conn):
        return sql(
            conn,
            "INSERT INTO reglas (campo, texto, monto_centavos, categoria_id) VALUES (?, ?, ?, ?)",
            (campo, texto, monto, categoria_id),
        ).lastrowid


def _mov(conn, tipo, descripcion, monto, dia=10, categoria_id=None) -> int:
    with db.transaccion(conn):
        return sql(
            conn,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen) "
            "VALUES (?, ?, ?, ?, ?, 'manual')",
            (f"2026-08-{dia:02d}T10:00:00", monto, tipo, descripcion, categoria_id),
        ).lastrowid


def _estado(conn, movimiento_id):
    return tuple(
        sql(
            conn, "SELECT categoria_id, origen_categoria, regla_id FROM movimientos WHERE id = ?", (movimiento_id,)
        ).fetchone()
    )


def _gana(conn, tipo, descripcion, monto):
    regla = regla_que_coincide(conn, tipo, descripcion, monto)
    return None if regla is None else regla["id"]


# --- Coincidencia -----------------------------------------------------------------------------

def test_transferencia_de_3200_coincide_sin_importar_el_destino(conn):
    regla = _regla(conn, "cuenta_destino", None, BUS, _cat(conn, "Transporte"))
    for destino in ("*3000000001", "*3000000002", "CONDUCTOR EJEMPLO", ""):
        assert _gana(conn, "transferencia", destino, BUS) == regla
    # Otro monto (también uno que solo se le parece) no coincide.
    for monto in (320001, 32000, 3200):
        assert _gana(conn, "transferencia", "*3000000001", monto) is None


def test_una_regla_por_monto_de_transferencia_no_toca_compras_ni_ingresos(conn):
    _regla(conn, "cuenta_destino", None, BUS, _cat(conn, "Transporte"))
    assert _gana(conn, "compra", "PANADERIA EJEMPLO", BUS) is None
    assert _gana(conn, "ingreso", "PERSONA EJEMPLO", BUS) is None
    assert _gana(conn, "ajuste", "Ajuste", BUS) is None


def test_una_regla_por_monto_de_compra_solo_si_se_pide(conn):
    compras = _regla(conn, "comercio", None, BUS, _cat(conn, "Antojos"))
    assert _gana(conn, "compra", "CUALQUIER TIENDA EJEMPLO", BUS) == compras
    assert _gana(conn, "transferencia", "*3000000001", BUS) is None


def test_texto_y_monto_exige_las_dos_cosas(conn):
    regla = _regla(conn, "cuenta_destino", "laura gómez ejemplo", 620000, _cat(conn, "Restaurantes"))
    assert _gana(conn, "transferencia", "  LAURA  GÓMEZ EJEMPLO ", 620000) == regla
    assert _gana(conn, "transferencia", "LAURA GÓMEZ EJEMPLO", 620001) is None
    assert _gana(conn, "transferencia", "OTRA PERSONA EJEMPLO", 620000) is None


def test_una_regla_por_texto_sigue_sin_mirar_el_monto(conn):
    regla = _regla(conn, "comercio", "tienda ejemplo", None, _cat(conn, "Mercado"))
    for monto in (1, BUS, 99999999):
        assert _gana(conn, "compra", "TIENDA EJEMPLO", monto) == regla
    # Sin monto (como llamaban las pruebas de la v1) también.
    assert _gana(conn, "compra", "TIENDA EJEMPLO", None) == regla


def test_sin_monto_no_coinciden_las_reglas_por_monto(conn):
    _regla(conn, "cuenta_destino", None, BUS, _cat(conn, "Transporte"))
    assert regla_que_coincide(conn, "transferencia", "*3000000001", None) is None


# --- Prioridad --------------------------------------------------------------------------------

def test_especificidad():
    assert especificidad("x", 1) == 3
    assert especificidad("x", None) == 2
    assert especificidad(None, 1) == 1


def test_gana_el_texto_sobre_el_monto(conn):
    """El monto del bus coincide con el de una cuenta conocida: gana la regla por texto."""
    por_monto = _regla(conn, "cuenta_destino", None, BUS, _cat(conn, "Transporte"))
    por_texto = _regla(conn, "cuenta_destino", "*5678", None, _cat(conn, "Vivienda y servicios"))
    assert _gana(conn, "transferencia", "*5678", BUS) == por_texto
    assert _gana(conn, "transferencia", "*9999", BUS) == por_monto
    assert _gana(conn, "transferencia", "*5678", 100) == por_texto


def test_gana_texto_y_monto_sobre_texto_y_sobre_monto(conn):
    por_monto = _regla(conn, "quien_envia", None, 40000000, _cat(conn, "Otros ingresos"))
    por_texto = _regla(conn, "quien_envia", "carlos ruiz ejemplo", None, _cat(conn, "Sueldo"))
    las_dos = _regla(conn, "quien_envia", "carlos ruiz ejemplo", 40000000, _cat(conn, "Préstamos"))
    assert _gana(conn, "ingreso", "CARLOS RUIZ EJEMPLO", 40000000) == las_dos
    assert _gana(conn, "ingreso", "CARLOS RUIZ EJEMPLO", 50000000) == por_texto
    assert _gana(conn, "ingreso", "OTRA PERSONA EJEMPLO", 40000000) == por_monto


def test_el_orden_de_creacion_no_cambia_quien_gana(conn):
    # Primero la más específica y después las demás: sigue ganando la más específica.
    las_dos = _regla(conn, "cuenta_destino", "*5678", BUS, _cat(conn, "Transporte"))
    _regla(conn, "cuenta_destino", "*5678", None, _cat(conn, "Vivienda y servicios"))
    _regla(conn, "cuenta_destino", None, BUS, _cat(conn, "Otros"))
    assert _gana(conn, "transferencia", "*5678", BUS) == las_dos


def test_no_puede_haber_dos_reglas_con_las_mismas_condiciones(conn):
    """Por eso nunca empatan dos reglas de la misma especificidad (el desempate por id es solo de respaldo)."""
    _regla(conn, "cuenta_destino", None, BUS, _cat(conn, "Transporte"))
    _regla(conn, "cuenta_destino", "*5678", None, _cat(conn, "Transporte"))
    _regla(conn, "cuenta_destino", "*5678", BUS, _cat(conn, "Transporte"))
    for texto, monto in ((None, BUS), ("*5678", None), ("*5678", BUS)):
        with pytest.raises(sqlite3.IntegrityError):
            _regla(conn, "cuenta_destino", texto, monto, _cat(conn, "Otros"))
    # El mismo monto en otro tipo sí es otra regla.
    _regla(conn, "comercio", None, BUS, _cat(conn, "Otros"))


# --- Ingresos ---------------------------------------------------------------------------------

def test_ingresos_por_monto_y_por_texto(conn):
    sueldo, prestamos = _cat(conn, "Sueldo"), _cat(conn, "Préstamos")
    por_texto = _regla(conn, "quien_envia", "empresa ejemplo s.a.s.", None, sueldo)
    por_monto = _regla(conn, "quien_envia", None, 40000000, prestamos)
    assert _gana(conn, "ingreso", "EMPRESA EJEMPLO S.A.S.", 480000000) == por_texto
    assert _gana(conn, "ingreso", "CARLOS RUIZ EJEMPLO", 40000000) == por_monto
    # Una regla de ingreso por monto nunca categoriza un gasto del mismo monto.
    assert _gana(conn, "transferencia", "*5678", 40000000) is None


# --- Al sincronizar y al reprocesar ---------------------------------------------------------

def _correo(gmail_id: str, texto: str, dia: int = 16) -> CorreoGmail:
    return CorreoGmail(
        gmail_id, datetime(2026, 8, dia, 9, 20, tzinfo=ZONA_COLOMBIA), "Aviso (ejemplo)", texto, **LEGITIMO
    )


def _transferencia(destino: str, monto: str = "$3,200.00") -> str:
    return f"Bancolombia: Transferiste {monto} desde tu cuenta *1234 a la cuenta {destino} el 16/08/26 a las 09:15."


def _compra(comercio: str, monto: str = "$3.200,00") -> str:
    return f"Bancolombia: Compraste {monto} en {comercio} con tu T.Deb *1234, el 16/08/2026 a las 14:32."


def _por_gmail(conn, gmail_id):
    return tuple(
        sql(
            conn, "SELECT categoria_id, origen_categoria, regla_id FROM movimientos WHERE gmail_id = ?", (gmail_id,)
        ).fetchone()
    )


def test_al_sincronizar_la_regla_del_bus_categoriza_sola(conn):
    """Criterio de terminado: "transferencia + $3.200" categoriza sola, sin importar el destino."""
    transporte, vivienda = _cat(conn, "Transporte"), _cat(conn, "Vivienda y servicios")
    bus = _regla(conn, "cuenta_destino", None, BUS, transporte)
    arriendo = _regla(conn, "cuenta_destino", "*5678", None, vivienda)
    cliente = ClienteFalso({
        "t-1": _correo("t-1", _transferencia("*3000000001")),
        "t-2": _correo("t-2", _transferencia("*3000000002")),
        "t-3": _correo("t-3", _transferencia("*3000000003", "$3,200.50")),
        "t-4": _correo("t-4", _transferencia("*5678")),
        "c-1": _correo("c-1", _compra("PANADERIA EJEMPLO")),
    })
    assert sincronizar(conn, cliente) == ResultadoSincronizacion(nuevos=5)
    assert _por_gmail(conn, "t-1") == (transporte, "regla", bus)
    assert _por_gmail(conn, "t-2") == (transporte, "regla", bus)
    assert _por_gmail(conn, "t-3") == (None, None, None)  # $3.200,50 no es $3.200
    assert _por_gmail(conn, "t-4") == (vivienda, "regla", arriendo)  # gana el texto
    assert _por_gmail(conn, "c-1") == (None, None, None)  # una compra de $3.200 no


def test_los_pagos_qr_son_transferencias_y_les_aplica_la_regla_por_monto(conn):
    """Ítem 27: un pago por QR se lee como transferencia; la regla del bus lo alcanza."""
    transporte = _cat(conn, "Transporte")
    bus = _regla(conn, "cuenta_destino", None, BUS, transporte)
    qr = (
        "Bancolombia: NOMBRE COMPLETO DE EJEMPLO pagaste $3,200.00 por codigo QR desde tu cuenta *1234 "
        "a la llave 3000000000 el 16/08/2026 a las 11:20."
    )
    assert sincronizar(conn, ClienteFalso({"q-1": _correo("q-1", qr)})) == ResultadoSincronizacion(nuevos=1)
    assert sql(conn, "SELECT tipo FROM movimientos WHERE gmail_id = 'q-1'").fetchone()[0] == "transferencia"
    assert _por_gmail(conn, "q-1") == (transporte, "regla", bus)


def test_el_retiro_se_categoriza_al_leerlo_y_no_por_reglas(conn):
    """Ítem 27 (D30): "Retiro a efectivo" se asigna al leer el aviso, antes que cualquier regla."""
    _regla(conn, "comercio", None, 5000000, _cat(conn, "Antojos"))  # compra + $50.000
    _regla(conn, "comercio", "cajero ejemplo", None, _cat(conn, "Otros"))
    retiro = (
        "Bancolombia: Retiraste $50.000,00 en CAJERO EJEMPLO de tu T.Deb **1234 el 16/08/2026 a las 10:15."
    )
    assert sincronizar(conn, ClienteFalso({"r-1": _correo("r-1", retiro)})) == ResultadoSincronizacion(nuevos=1)
    assert _por_gmail(conn, "r-1") == (_cat(conn, "Retiro a efectivo"), None, None)


def test_al_reprocesar_tambien_se_aplican_las_reglas_por_monto(conn, corregir_lector):
    """Ítem 19: el reproceso guarda por el mismo camino que la sincronización."""
    cliente = _sincronizar_inicial(conn)
    # El aviso que se recupera es una compra de $12.345 (fixture inventado).
    antojos = _cat(conn, "Antojos")
    regla = _regla(conn, "comercio", None, 1234500, antojos)
    corregir_lector()
    assert reprocesar(conn, cliente).movimientos_creados == 1
    assert _por_gmail(conn, "msg-r001") == (antojos, "regla", regla)


def test_la_sincronizacion_usa_la_funcion_unica(conn, monkeypatch):
    from finanzas.modulos.categorias.asignacion import AsignarCategorias

    llamadas = []
    original = AsignarCategorias.regla_que_coincide

    def espia(caso, tipo, descripcion, monto_centavos):
        llamadas.append((tipo, monto_centavos))
        return original(caso, tipo, descripcion, monto_centavos)

    monkeypatch.setattr(AsignarCategorias, "regla_que_coincide", espia)
    sincronizar(conn, ClienteFalso({"t-1": _correo("t-1", _transferencia("*3000000001"))}))
    assert llamadas == [("transferencia", BUS)]


# --- Recordar ---------------------------------------------------------------------------------

def test_recordar_por_monto_alcanza_a_los_pendientes_del_mismo_tipo_y_monto(conn):
    transporte = _cat(conn, "Transporte")
    pedido = _mov(conn, "transferencia", "*3000000001", BUS, 1)
    otro_destino = _mov(conn, "transferencia", "*3000000002", BUS, 2)
    otro_monto = _mov(conn, "transferencia", "*3000000003", 330000, 3)
    compra = _mov(conn, "compra", "PANADERIA EJEMPLO", BUS, 4)
    ingreso = _mov(conn, "ingreso", "PERSONA EJEMPLO", BUS, 5)
    ya = _mov(conn, "transferencia", "*3000000004", BUS, 6, categoria_id=_cat(conn, "Otros"))

    asignacion = asignar_con_detalle(conn, pedido, transporte, recordar=True, condiciones="monto")

    assert asignacion.total == 2
    regla = asignacion.regla_id
    assert sql(conn, "SELECT campo, texto, monto_centavos, categoria_id FROM reglas").fetchall() == [
        ("cuenta_destino", None, BUS, transporte)
    ]
    assert _estado(conn, pedido) == (transporte, "manual", None)
    assert _estado(conn, otro_destino) == (transporte, "regla", regla)
    assert _estado(conn, otro_monto) == (None, None, None)
    assert _estado(conn, compra) == (None, None, None)
    assert _estado(conn, ingreso) == (None, None, None)
    assert _estado(conn, ya) == (_cat(conn, "Otros"), None, None)  # no se pisa


def test_recordar_texto_y_monto(conn):
    restaurantes = _cat(conn, "Restaurantes")
    pedido = _mov(conn, "transferencia", "LAURA GÓMEZ EJEMPLO", 620000, 1)
    igual = _mov(conn, "transferencia", "laura  gómez ejemplo", 620000, 2)
    otro_monto = _mov(conn, "transferencia", "LAURA GÓMEZ EJEMPLO", 1500000, 3)
    asignacion = asignar_con_detalle(conn, pedido, restaurantes, recordar=True, condiciones="texto_y_monto")
    assert asignacion.total == 2
    assert _estado(conn, igual) == (restaurantes, "regla", asignacion.regla_id)
    assert _estado(conn, otro_monto) == (None, None, None)
    assert sql(conn, "SELECT campo, texto, monto_centavos FROM reglas").fetchall() == [
        ("cuenta_destino", "laura gómez ejemplo", 620000)
    ]


def test_recordar_no_aplica_donde_gana_otra_regla_mas_especifica(conn):
    transporte, vivienda = _cat(conn, "Transporte"), _cat(conn, "Vivienda y servicios")
    # Un pendiente que ya cumple una regla por texto más específica (la regla se
    # guardó sin aplicarse): la regla por monto nueva no es la que gana para él,
    # así que no lo toca.
    _regla(conn, "cuenta_destino", "*5678", None, vivienda)
    conocido = _mov(conn, "transferencia", "*5678", BUS, 1)
    pedido = _mov(conn, "transferencia", "*3000000001", BUS, 2)
    asignacion = asignar_con_detalle(conn, pedido, transporte, recordar=True, condiciones="monto")
    assert asignacion.total == 1
    assert _estado(conn, conocido) == (None, None, None)


def test_recordar_otra_vez_las_mismas_condiciones_cambia_la_categoria(conn):
    transporte, otros = _cat(conn, "Transporte"), _cat(conn, "Otros")
    uno = _mov(conn, "transferencia", "*3000000001", BUS, 1)
    dos = _mov(conn, "transferencia", "*3000000002", BUS, 2)
    primera = asignar_con_detalle(conn, uno, transporte, recordar=True, condiciones="monto").regla_id
    segunda = asignar_con_detalle(conn, dos, otros, recordar=True, condiciones="monto").regla_id
    assert primera == segunda
    assert sql(conn, "SELECT id, categoria_id FROM reglas").fetchall() == [(primera, otros)]


def test_recordar_por_texto_sin_descripcion_no_se_puede_pero_por_monto_si(conn):
    transporte = _cat(conn, "Transporte")
    sin_texto = _mov(conn, "transferencia", "  ", BUS, 1)
    for condiciones in ("texto", "texto_y_monto"):
        with pytest.raises(categorizacion.ErrorCategorizacion):
            asignar_con_detalle(conn, sin_texto, transporte, recordar=True, condiciones=condiciones)
    assert _estado(conn, sin_texto) == (None, None, None)  # no cambió nada
    assert asignar_con_detalle(conn, sin_texto, transporte, recordar=True, condiciones="monto").total == 1


def test_el_mensaje_dice_la_causa(conn):
    sin_texto = _mov(conn, "transferencia", "  ", BUS, 1)
    with pytest.raises(categorizacion.ErrorCategorizacion) as error:
        asignar_con_detalle(conn, sin_texto, _cat(conn, "Transporte"), recordar=True, condiciones="texto")
    assert str(error.value) == categorizacion.MENSAJE_SIN_DESCRIPCION
    assert "descripción" in str(error.value)
    # El monto inválido no se puede guardar en la base (CHECK): se prueba la causa directamente.
    motivo = categorizacion.motivo_sin_regla
    assert motivo("*3000000001", 0, "monto") == categorizacion.MENSAJE_MONTO_INVALIDO
    assert motivo("*3000000001", -5, "texto_y_monto") == categorizacion.MENSAJE_MONTO_INVALIDO
    assert "descripción" not in categorizacion.MENSAJE_MONTO_INVALIDO
    assert motivo(" ", BUS, "texto") == categorizacion.MENSAJE_SIN_DESCRIPCION
    assert motivo(" ", 0, "texto_y_monto") == categorizacion.MENSAJE_SIN_DESCRIPCION


def test_condiciones_desconocidas_se_rechazan(conn):
    pedido = _mov(conn, "transferencia", "*3000000001", BUS, 1)
    with pytest.raises(categorizacion.ErrorCategorizacion):
        asignar_con_detalle(conn, pedido, _cat(conn, "Transporte"), recordar=True, condiciones="contiene")
    assert _estado(conn, pedido) == (None, None, None)


def test_recordar_de_la_v1_sigue_creando_reglas_por_texto(conn):
    mercado = _cat(conn, "Mercado")
    uno = _mov(conn, "compra", "TIENDA EJEMPLO", 100, 1)
    dos = _mov(conn, "compra", "TIENDA EJEMPLO", 999, 2)
    assert asignar_categoria(conn, uno, mercado, recordar=True) == 2
    assert sql(conn, "SELECT campo, texto, monto_centavos FROM reglas").fetchall() == [
        ("comercio", "tienda ejemplo", None)
    ]
    assert _estado(conn, dos)[:2] == (mercado, "regla")


# --- Lo que se ofrece y cómo se lee ----------------------------------------------------------

def test_reglas_posibles_segun_el_tipo():
    assert reglas_posibles("transferencia", "LAURA GÓMEZ EJEMPLO", 620000) == [
        CondicionesRegla("cuenta_destino", "laura gómez ejemplo", None),
        CondicionesRegla("cuenta_destino", None, 620000),
        CondicionesRegla("cuenta_destino", "laura gómez ejemplo", 620000),
    ]
    assert reglas_posibles("compra", "PANADERIA EJEMPLO", 850000) == [
        CondicionesRegla("comercio", "panaderia ejemplo", None)
    ]
    assert reglas_posibles("ingreso", "EMPRESA EJEMPLO", 100) == [
        CondicionesRegla("quien_envia", "empresa ejemplo", None),
        CondicionesRegla("quien_envia", None, 100),
        CondicionesRegla("quien_envia", "empresa ejemplo", 100),
    ]
    assert reglas_posibles("ingreso", " ", 100) == [CondicionesRegla("quien_envia", None, 100)]
    assert reglas_posibles("ajuste", "Ajuste", 100) == []
    # Sin descripción, una transferencia solo puede recordar el monto.
    assert reglas_posibles("transferencia", " ", BUS) == [CondicionesRegla("cuenta_destino", None, BUS)]
    assert reglas_posibles("compra", " ", BUS) == []


def test_condiciones_de_regla_se_pueden_pedir_para_cualquier_tipo():
    assert condiciones_de_regla("compra", "X", BUS, "monto") == CondicionesRegla("comercio", None, BUS)
    assert condiciones_de_regla("compra", "X", BUS, "monto").condiciones == "monto"
    assert condiciones_de_regla("ingreso", "X", BUS, "texto_y_monto").condiciones == "texto_y_monto"
    assert condiciones_de_regla("ajuste", "X", BUS, "monto") is None
    assert condiciones_de_regla("compra", "X", 0, "monto") is None
    assert condiciones_de_regla("compra", "X", BUS, "otra") is None


@pytest.mark.parametrize(
    ("centavos", "texto"),
    [(320000, "$3.200"), (620000, "$6.200"), (13244950, "$132.449,50"), (5, "$0,05"), (480000000, "$4.800.000")],
)
def test_pesos_como_en_el_prototipo(centavos, texto):
    assert pesos(centavos) == texto


def test_frases_como_en_el_prototipo():
    assert frase_regla("cuenta_destino", None, "Transporte", BUS) == "Si es una transferencia de $3.200, va a Transporte"
    assert frase_regla("quien_envia", "carlos ruiz ejemplo", "Préstamos", 40000000) == (
        "Si es un ingreso de «carlos ruiz ejemplo» por $400.000, va a Préstamos"
    )
    assert frase_regla("comercio", "supermercado la espiga", "Mercado") == (
        "Si es una compra en «supermercado la espiga», va a Mercado"
    )
    assert frase_regla("comercio", None, "Antojos", 850000) == "Si es una compra de $8.500, va a Antojos"
    assert frase_condiciones("cuenta_destino", None, BUS) == "transferencia de $3.200"
    assert frase_condiciones("cuenta_destino", "*5678", BUS) == "transferencia a «*5678» por $3.200"
    assert frase_condiciones("comercio", "tienda", None) == "compra en «tienda»"


def test_la_lista_de_reglas_va_por_tipo_y_en_el_orden_en_que_ganan(conn):
    transporte = _cat(conn, "Transporte")
    por_monto = _regla(conn, "cuenta_destino", None, BUS, transporte)
    por_texto = _regla(conn, "cuenta_destino", "*5678", None, transporte)
    las_dos = _regla(conn, "cuenta_destino", "*5678", BUS, transporte)
    compra = _regla(conn, "comercio", "tienda", None, _cat(conn, "Mercado"))
    assert [r["id"] for r in categorizacion.listar_reglas(conn)] == [compra, las_dos, por_texto, por_monto]
