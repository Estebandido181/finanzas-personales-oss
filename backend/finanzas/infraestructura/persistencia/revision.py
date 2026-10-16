"""Verificación inyectada: inspecciona, nunca ejecuta migraciones."""
from pathlib import Path
from collections.abc import Callable
from sqlalchemy import Connection, inspect, text


class BaseNoMigrada(Exception):
    """La base no está en la última migración. El mensaje dice qué hacer (sin datos)."""


def revision_actual(conn: Connection) -> str | None:
    """Revisión de Alembic guardada en la base, o ``None`` si no tiene (base v1 o vacía)."""
    if "alembic_version" not in inspect(conn).get_table_names():
        return None
    fila = conn.execute(text("SELECT version_num FROM alembic_version")).first()
    return None if fila is None else str(fila[0])




def exigir_al_dia(ruta: str, revision_esperada: str, conectar: Callable[[str], Connection]) -> None:
    mensaje = (
        "La base de datos no está en la última versión de su estructura. "
        "Aplica las migraciones con: python -m finanzas.migrar "
        "(en el servidor: sudo systemctl start finanzas-migrar.service)."
    )
    if not Path(ruta).is_file():
        raise BaseNoMigrada(mensaje)
    conn = conectar(ruta)
    try:
        actual = revision_actual(conn)
    finally:
        conn.close()
    if actual != revision_esperada:
        raise BaseNoMigrada(mensaje)
