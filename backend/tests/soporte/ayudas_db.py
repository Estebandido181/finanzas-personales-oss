"""Ayudas para que las pruebas ejecuten SQL escrito a mano (ítem 22).

Desde el ítem 22 la app usa conexiones de SQLAlchemy. Las pruebas siguen
preparando y revisando datos con SQL propio (con ``?``), igual que en la v1:

* ``sql(conn, "SELECT ... WHERE id = ?", (1,))`` lo ejecuta tal cual con el
  driver de SQLite (``exec_driver_sql``). Las filas se leen por posición
  (``fila[0]``) o por nombre (``fila["nombre"]``), como ``sqlite3.Row``.
* Si SQLite rechaza la sentencia, se lanza la **misma** excepción del
  driver (``sqlite3.IntegrityError``...), sin el envoltorio de SQLAlchemy:
  las pruebas de las restricciones de la base comprueban lo mismo que antes.
* Para confirmar, ``with db.transaccion(conn):`` hace lo que hacía
  ``with conn:`` con ``sqlite3``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection
from sqlalchemy.exc import DBAPIError


class Fila(tuple):
    """Fila que se lee por posición o por nombre de columna."""

    def __new__(cls, valores, columnas):
        fila = super().__new__(cls, valores)
        fila._columnas = tuple(columnas)
        return fila

    def __getitem__(self, clave):
        if isinstance(clave, str):
            return tuple.__getitem__(self, self._columnas.index(clave))
        return tuple.__getitem__(self, clave)

    def keys(self) -> list[str]:
        return list(self._columnas)


class Resultado:
    def __init__(self, filas: list[Fila], rowcount: int, lastrowid: Any) -> None:
        self._filas = filas
        self._siguiente = 0
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def fetchone(self) -> Fila | None:
        if self._siguiente >= len(self._filas):
            return None
        self._siguiente += 1
        return self._filas[self._siguiente - 1]

    def fetchall(self) -> list[Fila]:
        resto = self._filas[self._siguiente:]
        self._siguiente = len(self._filas)
        return resto

    def __iter__(self):
        return iter(self.fetchall())


def sql(conn: Connection, texto: str, parametros: Any = ()) -> Resultado:
    """Ejecuta ``texto`` con sus parámetros (``?`` o ``:nombre``) en la conexión."""
    if isinstance(parametros, list):
        parametros = tuple(parametros)  # una lista sería "varias filas" para SQLAlchemy
    try:
        resultado = conn.exec_driver_sql(texto, parametros)
    except DBAPIError as error:
        raise error.orig from None
    filas: list[Fila] = []
    if resultado.returns_rows:
        columnas = list(resultado.keys())
        filas = [Fila(tuple(f), columnas) for f in resultado.fetchall()]
    lastrowid = getattr(resultado, "lastrowid", None)
    return Resultado(filas, resultado.rowcount, lastrowid)
