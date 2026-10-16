"""Inspección de columnas para compatibilidad con bases históricas."""
from sqlalchemy import Connection

def columnas(conn: Connection, tabla: str) -> set[str]:
    return {fila[1] for fila in conn.exec_driver_sql(f'PRAGMA table_info("{tabla}")')}
