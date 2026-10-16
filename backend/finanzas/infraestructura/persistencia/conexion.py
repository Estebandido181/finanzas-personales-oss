"""Motor y conexión sin migraciones ni creación de tablas."""
import functools
import sqlite3
from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

ESPERA_POR_DEFECTO = 5.0

def _al_conectar_sqlite(conexion_dbapi: sqlite3.Connection, _registro) -> None:
    conexion_dbapi.execute("PRAGMA foreign_keys = ON")


@functools.lru_cache(maxsize=64)
def crear_motor(ruta: str, espera: float = ESPERA_POR_DEFECTO) -> Engine:
    """Motor para la base SQLite en ``ruta`` (el archivo se crea si no existe).

    ``NullPool``: cada ``connect()`` abre una conexión nueva y ``close()`` la
    cierra de verdad, como hacía la v1 con ``sqlite3.connect``. Para una app
    de un usuario sobra, y evita compartir conexiones SQLite entre hilos.
    Cada conexión activa las claves foráneas (SQLite las trae apagadas).
    ``hide_parameters``: el texto de un error nunca lleva los valores (montos,
    comercios), igual que en la v1, donde el error de ``sqlite3`` no los citaba.
    """
    motor = create_engine(
        URL.create("sqlite", database=ruta),
        poolclass=NullPool,
        connect_args={"timeout": espera},
        # Los errores de SQLAlchemy citan los parámetros de la sentencia
        # (montos, descripciones) y acabarían en los registros: se ocultan.
        hide_parameters=True,
    )
    event.listen(motor, "connect", _al_conectar_sqlite)
    return motor


def conectar(ruta: str, espera: float = ESPERA_POR_DEFECTO) -> Connection:
    """Abre una conexión a la base en ``ruta``. Quien la abre la cierra (``close()``)."""
    return crear_motor(str(ruta), espera).connect()


def ruta_de(conn: Connection) -> str:
    """Ruta del archivo de la base de una conexión."""
    return str(conn.engine.url.database)
