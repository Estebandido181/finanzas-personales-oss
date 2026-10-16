"""Ayudas compartidas extraídas de test_migracion_0005; datos inventados."""

from __future__ import annotations


import sqlite3


import pytest


from alembic import command


from alembic.util import CommandError


from finanzas import db, migrar


from finanzas.migraciones import esquema_v1


from tests.soporte.migraciones import crear_base_v1, revision


INICIALES = {
    1: ("Mercado", "gasto", "cat-mercado", "shopping-basket"),
    2: ("Restaurantes", "gasto", "cat-restaurantes", "utensils"),
    3: ("Transporte", "gasto", "cat-transporte", "bus"),
    4: ("Vivienda y servicios", "gasto", "cat-vivienda", "house"),
    5: ("Salud", "gasto", "cat-salud", "heart-pulse"),
    6: ("Entretenimiento", "gasto", "cat-entretenimiento", "ticket"),
    7: ("Compras", "gasto", "cat-compras", "shopping-bag"),
    8: ("Otros", "gasto", "cat-otros", "shapes"),
    9: ("Antojos", "gasto", "cat-antojos", "ice-cream-cone"),
    10: ("Sueldo", "ingreso", "cat-sueldo", "briefcase"),
    11: ("Préstamos", "ingreso", "cat-prestamos", "handshake"),
    12: ("Otros ingresos", "ingreso", "cat-otros-ingresos", "coins"),
}


CON_LA_0006 = {
    **INICIALES,
    13: ("Retiro a efectivo", "gasto", "cat-vivienda", "coins"),
    14: ("Pago de tarjeta", "gasto", "cat-prestamos", "coins"),
}


def _sql(ruta, texto, parametros=()):
    conn = sqlite3.connect(ruta)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            return conn.execute(texto, parametros).fetchall()
    finally:
        conn.close()


def _estructura(ruta):
    conn = sqlite3.connect(ruta)
    try:
        return esquema_v1.describir(conn)
    finally:
        conn.close()


def _subir_hasta(ruta, destino):
    """Como ``migrar.aplicar`` pero parando en ``destino``."""
    marcar_v1 = migrar.diagnosticar(str(ruta)).marcar_v1
    with migrar.conectar_para_migrar(str(ruta)) as conexion, conexion.begin():
        config = migrar._config(conexion)
        if marcar_v1:
            command.stamp(config, migrar.REVISION_V1)
        command.upgrade(config, destino)


def _asignaciones(ruta):
    """Todo lo que liga movimientos y reglas a sus categorías (y cómo se categorizó)."""
    return {
        "movimientos": _sql(
            ruta, "SELECT id, tipo, categoria_id, origen_categoria, regla_id FROM movimientos ORDER BY id"
        ),
        "reglas": _sql(ruta, "SELECT id, campo, texto, categoria_id FROM reglas ORDER BY id"),
    }


def _categorias(ruta):
    return {i: (n, c, co, ic) for i, n, c, co, ic in _sql(
        ruta, "SELECT id, nombre, clase, color, icono FROM categorias ORDER BY id"
    )}
