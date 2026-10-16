"""Fronteras originales de lectura/escritura y dialecto, sin operación."""
from collections.abc import Iterator
from contextlib import contextmanager
from sqlalchemy import Connection, Table
from sqlalchemy.dialects import sqlite as _sqlite, postgresql as _postgresql

def _es_sqlite(conn: Connection) -> bool:
    return conn.dialect.name == "sqlite"


def en_transaccion(conn: Connection) -> bool:
    """``True`` si la base tiene una transacción abierta en esta conexión.

    En SQLite se pregunta al driver: SQLAlchemy considera abierta una
    transacción desde el primer SELECT, pero en el modo clásico de ``sqlite3``
    un SELECT no abre ninguna en la base.
    """
    if _es_sqlite(conn):
        return bool(conn.connection.dbapi_connection.in_transaction)
    return conn.in_transaction()


def _cerrar_transaccion_vacia(conn: Connection) -> None:
    # Tras un SELECT, SQLAlchemy cree tener una transacción abierta que en la
    # base no existe; se cierra (no hay nada que confirmar) para poder abrir otra.
    if conn.in_transaction() and not en_transaccion(conn):
        conn.commit()


@contextmanager
def transaccion(conn: Connection, inmediata: bool = False) -> Iterator[None]:
    """Todo lo de dentro se confirma junto al salir, o se deshace si hay una excepción.

    ``inmediata``: en SQLite abre con ``BEGIN IMMEDIATE`` (reserva la
    escritura desde el principio, antes de las lecturas). Es lo que hacía la
    v1 con ``with conn: conn.execute("BEGIN IMMEDIATE")``.
    """
    _cerrar_transaccion_vacia(conn)
    if inmediata and _es_sqlite(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.rollback()
        raise
    conn.commit()


@contextmanager
def lectura_consistente(conn: Connection) -> Iterator[None]:
    """Transacción de solo lectura: todas las consultas ven la misma foto de la base.

    Si quien llama ya tiene una transacción abierta, se usa esa y no se cierra.
    Anidable: la web la abre para leer la barra (saldo y pendientes) y el
    reporte juntos, y ``reporte_mensual`` reutiliza esa misma transacción.
    """
    if en_transaccion(conn):
        yield
        return
    _cerrar_transaccion_vacia(conn)
    if _es_sqlite(conn):
        conn.exec_driver_sql("BEGIN")
    else:  # pragma: no cover - solo cuando haya otro motor
        conn.begin()
    try:
        yield
    finally:
        conn.rollback()  # no se escribió nada


def insertar(conn: Connection, tabla: Table):
    """``INSERT`` con soporte de ``ON CONFLICT`` para el motor de la conexión.

    Devuelve un ``Insert`` con ``on_conflict_do_nothing`` y
    ``on_conflict_do_update`` (misma API en SQLite y PostgreSQL).
    """
    if _es_sqlite(conn):
        return _sqlite.insert(tabla)
    return _postgresql.insert(tabla)  # pragma: no cover - solo cuando haya otro motor
