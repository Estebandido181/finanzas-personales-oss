"""Pruebas de finanzas.categorizacion: normalización, reglas y asignación.

Todos los comercios y cuentas son inventados.
"""

from __future__ import annotations

import pytest

from finanzas import categorizacion, db
from finanzas.categorizacion import (
    ErrorCategorizacion,
    MovimientoNoEncontrado,
    ReglaNoEncontrada,
    asignar_categoria,
    borrar_regla,
    campo_para_tipo,
    regla_que_coincide,
    listar_reglas,
    normalizar,
    sin_categorizar,
)
from tests.soporte.ayudas_db import sql


def categoria_por_reglas(conn, tipo, descripcion):
    """Categoría de la regla que coincide (``regla_que_coincide``), o ``None``."""
    regla = regla_que_coincide(conn, tipo, descripcion, 100)
    return None if regla is None else regla["categoria_id"]


@pytest.fixture
def conn(tmp_path):
    conexion = db.conectar(str(tmp_path / "cat.db"))
    db.inicializar(conexion)
    yield conexion
    conexion.close()


def _cat(conn, nombre):
    return sql(conn, "SELECT id FROM categorias WHERE nombre = ?", (nombre,)).fetchone()[0]


_contador = iter(range(1, 10_000))


def _mov(conn, tipo="compra", descripcion="TIENDA EJEMPLO", monto=100000, fecha="2026-08-15T10:00:00",
         categoria_id=None):
    """Inserta un movimiento de prueba y devuelve su id."""
    origen, gmail_id = ("gmail", f"msg-{next(_contador)}") if tipo in ("compra", "transferencia") else ("manual", None)
    with db.transaccion(conn):
        cursor = sql(
            conn,
            "INSERT INTO movimientos (fecha_hora, monto_centavos, tipo, descripcion, categoria_id, origen, gmail_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fecha, monto, tipo, descripcion, categoria_id, origen, gmail_id),
        )
    return cursor.lastrowid


def _categoria_de(conn, movimiento_id):
    return sql(conn, "SELECT categoria_id FROM movimientos WHERE id = ?", (movimiento_id,)).fetchone()[0]


def _num_reglas(conn):
    return sql(conn, "SELECT COUNT(*) FROM reglas").fetchone()[0]


# --- Normalización -----------------------------------------------------------------

def test_normalizar_tildes_nfc_y_nfd_son_iguales():
    compuesta = "CAFÉ EJEMPLO"          # É en un solo carácter
    descompuesta = "CAFÉ EJEMPLO"      # E + tilde combinante
    assert compuesta != descompuesta
    assert normalizar(compuesta) == normalizar(descompuesta) == "café ejemplo"


def test_normalizar_mayusculas_y_espacios():
    assert normalizar("  Panadería   LA\tEspiga \n ") == "panadería la espiga"
    assert normalizar("MERPAGO*TIENDA") == normalizar("merpago*tienda")
    assert normalizar("STRASSE") == normalizar("straße")  # casefold, no lower
    assert normalizar("   ") == ""


def test_igualdad_exacta_no_coincide_por_subcadena(conn):
    mercado = _cat(conn, "Mercado")
    asignar_categoria(conn, _mov(conn, descripcion="MERPAGO*TIENDA"), mercado, recordar=True)
    asignar_categoria(conn, _mov(conn, descripcion="D1"), mercado, recordar=True)

    assert categoria_por_reglas(conn, "compra", "MERPAGO*TIENDA") == mercado
    assert categoria_por_reglas(conn, "compra", "  merpago*tienda ") == mercado
    assert categoria_por_reglas(conn, "compra", "MERPAGO*TIENDA2") is None
    assert categoria_por_reglas(conn, "compra", "MERPAGO") is None
    assert categoria_por_reglas(conn, "compra", "D1 SAS") is None
    assert categoria_por_reglas(conn, "compra", "TIENDA D1") is None
    assert categoria_por_reglas(conn, "compra", "D1") == mercado


# --- Campo según el tipo -------------------------------------------------------------

@pytest.mark.parametrize(
    "tipo, campo",
    [("compra", "comercio"), ("transferencia", "cuenta_destino"), ("ingreso", "quien_envia"), ("ajuste", None),
     ("otro", None)],
)
def test_campo_para_tipo(tipo, campo):
    assert campo_para_tipo(tipo) == campo


def test_regla_de_comercio_no_aplica_a_transferencias_ni_al_reves(conn):
    otros = _cat(conn, "Otros")
    asignar_categoria(conn, _mov(conn, "compra", "*5678"), otros, recordar=True)
    assert categoria_por_reglas(conn, "compra", "*5678") == otros
    assert categoria_por_reglas(conn, "transferencia", "*5678") is None

    vivienda = _cat(conn, "Vivienda y servicios")
    asignar_categoria(conn, _mov(conn, "transferencia", "*9999"), vivienda, recordar=True)
    assert categoria_por_reglas(conn, "transferencia", "*9999") == vivienda
    assert categoria_por_reglas(conn, "compra", "*9999") is None
    campos = {(r["campo"], r["texto"]) for r in listar_reglas(conn)}
    assert campos == {("comercio", "*5678"), ("cuenta_destino", "*9999")}


# --- Ingresos y ajustes ---------------------------------------------------------------

def test_ingresos_en_la_bandeja_y_ajustes_fuera(conn):
    # Ítem 15: un ingreso sin categoría es pendiente; un ajuste nunca.
    compra = _mov(conn, "compra", "TIENDA EJEMPLO")
    transferencia = _mov(conn, "transferencia", "*5678")
    ingreso = _mov(conn, "ingreso", "Salario (ejemplo)")
    ajuste = _mov(conn, "ajuste", "Ajuste", monto=-5000)

    assert {f["id"] for f in sin_categorizar(conn)} == {compra, transferencia, ingreso}
    assert categorizacion.contar_sin_categorizar(conn) == 3

    for categoria in (_cat(conn, "Otros"), _cat(conn, "Otros ingresos")):
        with pytest.raises(ErrorCategorizacion):
            asignar_categoria(conn, ajuste, categoria, recordar=True)
    assert _categoria_de(conn, ajuste) is None
    assert _num_reglas(conn) == 0


def test_una_regla_de_comercio_no_categoriza_ingresos_ni_ajustes(conn):
    otros = _cat(conn, "Otros")
    with db.transaccion(conn):
        sql(conn, "INSERT INTO reglas (campo, texto, categoria_id) VALUES ('comercio', 'salario (ejemplo)', ?)", (otros,))
    assert categoria_por_reglas(conn, "ingreso", "Salario (ejemplo)") is None
    assert categoria_por_reglas(conn, "ajuste", "Salario (ejemplo)") is None


def test_bandeja_ordenada_por_fecha_descendente(conn):
    viejo = _mov(conn, fecha="2026-08-01T08:00:00")
    nuevo = _mov(conn, fecha="2026-08-20T08:00:00")
    medio = _mov(conn, fecha="2026-08-10T08:00:00")
    _mov(conn, fecha="2026-08-25T08:00:00", categoria_id=_cat(conn, "Otros"))  # ya categorizado
    assert [f["id"] for f in sin_categorizar(conn)] == [nuevo, medio, viejo]


# --- Asignar ---------------------------------------------------------------------------

def test_asignar_sin_recordar_no_crea_regla(conn):
    mov = _mov(conn, descripcion="TIENDA EJEMPLO")
    otro = _mov(conn, descripcion="TIENDA EJEMPLO")
    salud = _cat(conn, "Salud")

    assert asignar_categoria(conn, mov, salud, recordar=False) == 1

    assert _categoria_de(conn, mov) == salud
    assert _categoria_de(conn, otro) is None
    assert _num_reglas(conn) == 0
    assert categoria_por_reglas(conn, "compra", "TIENDA EJEMPLO") is None


def test_asignar_recordando_crea_regla_y_categoriza_pendientes_sin_pisar(conn):
    restaurantes = _cat(conn, "Restaurantes")
    compras = _cat(conn, "Compras")
    mov = _mov(conn, descripcion="Café  Ejemplo")
    igual_pendiente = _mov(conn, descripcion="CAFÉ EJEMPLO")          # NFD y mayúsculas
    igual_pendiente2 = _mov(conn, descripcion=" café ejemplo ")
    ya_categorizado = _mov(conn, descripcion="CAFÉ EJEMPLO", categoria_id=compras)
    distinto = _mov(conn, descripcion="CAFÉ EJEMPLO 2")
    transferencia_igual = _mov(conn, "transferencia", "Café Ejemplo")

    total = asignar_categoria(conn, mov, restaurantes, recordar=True)

    assert total == 3
    assert _categoria_de(conn, mov) == restaurantes
    assert _categoria_de(conn, igual_pendiente) == restaurantes
    assert _categoria_de(conn, igual_pendiente2) == restaurantes
    assert _categoria_de(conn, ya_categorizado) == compras          # no se pisa
    assert _categoria_de(conn, distinto) is None                    # no es subcadena
    assert _categoria_de(conn, transferencia_igual) is None         # otro campo
    reglas = [dict(r) for r in listar_reglas(conn)]
    assert reglas == [{"id": reglas[0]["id"], "campo": "comercio", "texto": "café ejemplo",
                       "monto_centavos": None, "categoria_id": restaurantes, "categoria": "Restaurantes",
                       "categoria_clase": "gasto", "categoria_color": "cat-restaurantes",
                       "categoria_icono": "utensils", "modo_texto": "exacta", "origen_regla": "todos", "texto_visible": None}]


def test_upsert_reemplaza_la_categoria_de_la_regla(conn):
    mercado, compras = _cat(conn, "Mercado"), _cat(conn, "Compras")
    asignar_categoria(conn, _mov(conn, descripcion="SUPER EJEMPLO"), mercado, recordar=True)
    antes = listar_reglas(conn)[0]
    asignar_categoria(conn, _mov(conn, descripcion="super  ejemplo"), compras, recordar=True)

    reglas = listar_reglas(conn)
    assert len(reglas) == 1
    assert reglas[0]["id"] == antes["id"]
    assert reglas[0]["categoria_id"] == compras
    assert categoria_por_reglas(conn, "compra", "SUPER EJEMPLO") == compras


def test_reasignar_un_movimiento_ya_categorizado_cuenta_uno(conn):
    mov = _mov(conn, categoria_id=_cat(conn, "Otros"))
    assert asignar_categoria(conn, mov, _cat(conn, "Salud"), recordar=False) == 1
    assert _categoria_de(conn, mov) == _cat(conn, "Salud")


def test_borrar_regla_no_descategoriza(conn):
    transporte = _cat(conn, "Transporte")
    a = _mov(conn, descripcion="TAXI EJEMPLO")
    b = _mov(conn, descripcion="TAXI EJEMPLO")
    asignar_categoria(conn, a, transporte, recordar=True)
    regla_id = listar_reglas(conn)[0]["id"]

    borrar_regla(conn, regla_id)

    assert listar_reglas(conn) == []
    assert _categoria_de(conn, a) == transporte
    assert _categoria_de(conn, b) == transporte
    assert categoria_por_reglas(conn, "compra", "TAXI EJEMPLO") is None
    with pytest.raises(ReglaNoEncontrada):
        borrar_regla(conn, regla_id)


# --- Validaciones ------------------------------------------------------------------------

def test_movimiento_inexistente(conn):
    with pytest.raises(MovimientoNoEncontrado):
        asignar_categoria(conn, 999, _cat(conn, "Otros"), recordar=True)
    assert _num_reglas(conn) == 0


@pytest.mark.parametrize("recordar", [False, True])
def test_categoria_inexistente_no_cambia_nada(conn, recordar):
    mov = _mov(conn)
    with pytest.raises(ErrorCategorizacion) as error:
        asignar_categoria(conn, mov, 999, recordar=recordar)
    assert not isinstance(error.value, MovimientoNoEncontrado)
    assert _categoria_de(conn, mov) is None
    assert _num_reglas(conn) == 0


def test_tipo_no_categorizable(conn):
    ajuste = _mov(conn, "ajuste", "Ajuste", monto=-100)
    with pytest.raises(ErrorCategorizacion, match="compras, transferencias e ingresos"):
        asignar_categoria(conn, ajuste, _cat(conn, "Otros"), recordar=False)
    assert _categoria_de(conn, ajuste) is None


def test_recordar_sin_descripcion_falla_sin_cambios(conn):
    mov = _mov(conn, descripcion="   ")
    with pytest.raises(ErrorCategorizacion):
        asignar_categoria(conn, mov, _cat(conn, "Otros"), recordar=True)
    assert _categoria_de(conn, mov) is None
    # Sin recordar sí se puede.
    assert asignar_categoria(conn, mov, _cat(conn, "Otros"), recordar=False) == 1


def test_texto_con_comillas_no_inyecta_sql(conn):
    texto = "TIENDA'); DROP TABLE reglas; --"
    otros = _cat(conn, "Otros")
    asignar_categoria(conn, _mov(conn, descripcion=texto), otros, recordar=True)
    assert categoria_por_reglas(conn, "compra", texto) == otros
    assert _num_reglas(conn) == 1


def test_categorias_en_orden_estable(conn):
    # Primero las de gasto y luego las de ingreso; en cada clase, por id, con
    # «Otros» al final de las de gasto (como en el prototipo).
    assert [c["nombre"] for c in categorizacion.categorias(conn)] == [
        *db.CATEGORIAS_FIJAS[:7], "Antojos", "Retiro a efectivo", "Pago de tarjeta", "Otros",
        "Sueldo", "Préstamos", "Otros ingresos",
    ]
    nueva = categorizacion.crear_categoria(conn, "Mascotas", "gasto", "cat-otros", "bus")
    assert [c["id"] for c in categorizacion.categorias(conn, clase="gasto")][-2:] == [nueva, _cat(conn, "Otros")]


@pytest.mark.parametrize("invisible", ["​", "‍", "﻿", "⁠", "­", "͏", "᠎"])
def test_normalizar_quita_invisibles_de_formato(conn, invisible):
    assert normalizar(f"MERPAGO{invisible}*TIENDA{invisible}") == "merpago*tienda"
    otros = _cat(conn, "Otros")
    asignar_categoria(conn, _mov(conn, descripcion="MERPAGO*TIENDA"), otros, recordar=True)
    assert categoria_por_reglas(conn, "compra", f"{invisible}MERPAGO*{invisible}TIENDA") == otros
