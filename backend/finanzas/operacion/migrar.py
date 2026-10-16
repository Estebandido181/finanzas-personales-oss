"""Aplica las migraciones pendientes de la base, con respaldo previo (ítem 22, D19).

Uso (en el servidor lo lanza ``finanzas-migrar.service``, ver deploy/GUIA.md)::

    python -m finanzas.migrar [--base RUTA] [--respaldos CARPETA]
    python -m finanzas.migrar --comprobar
    python -m finanzas.migrar --bajar-a REVISION

Sin opciones:

1. Mira en qué estado está la base, sin cambiar nada:

   * con versión (tabla ``alembic_version``): calcula las migraciones pendientes;
   * sin versión y sin tablas (instalación nueva): se aplican todas;
   * sin versión pero con tablas (la base de la v1, creada antes de las
     migraciones): si su estructura coincide **exactamente** con la de la v1
     se marca como ``0001`` (``stamp``) y se siguen las pendientes; si no
     coincide, se detiene sin tocar nada y dice qué tablas difieren.

2. Si no hay nada que hacer, lo dice y termina: no hace respaldo ni escribe
   (migrar dos veces no cambia nada).
3. Si hay cambios y la base ya tenía tablas, hace un respaldo con la misma
   lógica que el respaldo diario (``deploy/respaldo.py``: copia consistente,
   permisos 0600, ``integrity_check``) llamado
   ``finanzas-antes-de-migrar-<revisión>-AAAAMMDDTHHMMSS.db``. Ese nombre no
   sigue el patrón del respaldo diario, así que la rotación no lo borra: se
   conservan todos (la guía explica cómo verlos y borrarlos). Si el respaldo
   falla, no migra.
4. Aplica todo en **una sola transacción** (``BEGIN IMMEDIATE``): o queda
   todo aplicado o nada.

``--comprobar``: termina con 0 si la base está en la última revisión y con 1
si no (no escribe ni crea la base). ``--bajar-a``: deshace migraciones hasta
esa revisión, con respaldo previo; nunca por debajo de ``0001`` (para eso se
restaura el respaldo).

Códigos de salida: 0 bien; 1 no se pudo (o ``--comprobar`` encontró
pendientes); 2 argumentos inválidos. Solo imprime revisiones, nombres de
archivo, tamaños y nombres de tablas: nunca montos ni filas.
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import os
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType

from alembic import command
from alembic.config import Config as ConfigAlembic
from alembic.script import ScriptDirectory
from alembic.script.revision import RevisionError
from alembic.util import CommandError
from sqlalchemy import Connection, create_engine, event, inspect
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from finanzas.infraestructura import persistencia as db
from finanzas.migraciones import esquema_v1

from finanzas.operacion.revisiones import (CARPETA_MIGRACIONES, _config, _scripts, revision_final, _revision_conocida, _pendientes)
from finanzas.operacion.respaldo import RUTA_RESPALDO, _modulo_respaldo
REVISION_V1 = "0001"
RESPALDOS_POR_DEFECTO = "/var/backups/finanzas"
# Si la app o la sincronización están escribiendo, se espera hasta esto (segundos).
ESPERA_BLOQUEO = 60


class ErrorMigracion(Exception):
    """No se pudo migrar. El mensaje es para el dueño y no lleva datos de la base."""


@dataclass(frozen=True)
class Diagnostico:
    """En qué estado está la base y qué haría falta para dejarla al día."""

    actual: str | None
    pendientes: list[str] = field(default_factory=list)
    marcar_v1: bool = False
    base_nueva: bool = False

    @property
    def al_dia(self) -> bool:
        return not self.pendientes and not self.marcar_v1


# --- Alembic ----------------------------------------------------------------------

def conectar_para_migrar(ruta: str) -> Connection:
    """Conexión para migrar: cada transacción empieza con ``BEGIN IMMEDIATE`` real.

    El modo clásico del módulo ``sqlite3`` no abre transacción para los
    cambios de estructura; aquí se desactiva (``isolation_level = None``) y
    SQLAlchemy emite el BEGIN, para que toda la migración sea una sola
    transacción (receta de la documentación de SQLAlchemy para SQLite).
    """
    motor = create_engine(
        URL.create("sqlite", database=str(ruta)),
        poolclass=NullPool,
        connect_args={"timeout": ESPERA_BLOQUEO},
        hide_parameters=True,  # los errores no citan valores de la base
    )

    @event.listens_for(motor, "connect")
    def _al_conectar(conexion_dbapi, _registro) -> None:
        conexion_dbapi.isolation_level = None
        # Procedimiento de SQLite para cambiar la estructura (sqlite.org,
        # "Making Other Kinds Of Table Schema Changes"): claves foráneas
        # apagadas mientras se reconstruyen tablas y, antes de confirmar,
        # ``PRAGMA foreign_key_check`` (``env.py``), que rechaza la migración
        # si deja alguna clave rota que no estuviera ya. Con ellas encendidas
        # (aunque diferidas), copiar una fila huérfana de antes, escrita con
        # las claves apagadas, haría fallar la migración (0008).
        conexion_dbapi.execute("PRAGMA foreign_keys = OFF")

    @event.listens_for(motor, "begin")
    def _al_empezar(conexion: Connection) -> None:
        conexion.exec_driver_sql("BEGIN IMMEDIATE")

    return motor.connect()


def _tablas_de_la_app(conexion: Connection) -> list[str]:
    return [
        t for t in inspect(conexion).get_table_names()
        if t != "alembic_version" and not t.startswith("sqlite_")
    ]


def _diagnosticar(conexion: Connection) -> Diagnostico:
    actual = db.revision_actual(conexion)
    if actual is not None:
        if not _revision_conocida(actual):
            raise ErrorMigracion(
                f"La base está en la revisión {actual}, que este código no conoce "
                "(¿es una versión más nueva de la app?). No se cambió nada."
            )
        return Diagnostico(actual=actual, pendientes=_pendientes(actual))
    if not _tablas_de_la_app(conexion):
        return Diagnostico(actual=None, pendientes=_pendientes(None), base_nueva=True)
    diferencias = esquema_v1.diferencias_con_v1(conexion.connection.dbapi_connection)
    if diferencias:
        raise ErrorMigracion(
            "La base no tiene versión y su estructura no es la de la v1 esperada ("
            + "; ".join(diferencias)
            + "). No se cambió nada."
        )
    return Diagnostico(actual=None, pendientes=_pendientes(REVISION_V1), marcar_v1=True)


def diagnosticar(ruta: str) -> Diagnostico:
    """Estado de la base en ``ruta``, sin escribir nada (ni crear el archivo)."""
    if not Path(ruta).is_file():
        return Diagnostico(actual=None, pendientes=_pendientes(None), base_nueva=True)
    conexion = db.conectar(ruta)
    try:
        return _diagnosticar(conexion)
    finally:
        conexion.close()


def aplicar(ruta: str) -> Diagnostico:
    """Deja la base en la última revisión (sin respaldo). Devuelve lo que se hizo.

    Si ya está al día no escribe nada. Si hace falta, todo ocurre en una sola
    transacción que vuelve a comprobar el estado (por si cambió entretanto).
    """
    if diagnosticar(ruta).al_dia:
        return Diagnostico(actual=revision_final())
    with conectar_para_migrar(ruta) as conexion, conexion.begin():
        diagnostico = _diagnosticar(conexion)
        if diagnostico.al_dia:
            return diagnostico
        config = _config(conexion)
        if diagnostico.marcar_v1:
            command.stamp(config, REVISION_V1)
        command.upgrade(config, "head")
    return diagnostico


def bajar_a(ruta: str, revision: str) -> list[str]:
    """Deshace migraciones hasta ``revision`` (sin respaldo). Devuelve las deshechas.

    Acepta ``"base"`` (lo borra todo): solo para pruebas; el comando no lo permite.
    """
    with conectar_para_migrar(ruta) as conexion, conexion.begin():
        actual = db.revision_actual(conexion)
        if actual is None:
            raise ErrorMigracion("La base no tiene versión: no hay nada que deshacer.")
        deshechas = [
            r.revision for r in _scripts().iterate_revisions(actual, revision)
            if r.revision != revision
        ]
        command.downgrade(_config(conexion), revision)
    return deshechas


# --- Respaldo previo ----------------------------------------------------------------

def nombre_respaldo_previo(desde: str | None, momento: datetime) -> str:
    return f"finanzas-antes-de-migrar-{desde or 'v1'}-{momento:%Y%m%dT%H%M%S}.db"


def respaldar(ruta: str, carpeta: str, desde: str | None, momento: datetime | None = None) -> Path:
    """Respaldo previo a migrar. Lanza la ``ErrorRespaldo`` de ``deploy/respaldo.py`` si falla."""
    momento = momento or datetime.now()
    respaldo = _modulo_respaldo()
    return respaldo.crear_respaldo(
        Path(ruta), Path(carpeta), momento.date(), nombre=nombre_respaldo_previo(desde, momento)
    )


# --- Comando ------------------------------------------------------------------------

def _argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m finanzas.migrar",
        description="Aplica las migraciones pendientes de la base, con respaldo previo.",
    )
    parser.add_argument(
        "--base",
        default=os.environ.get("DB_PATH", "").strip() or "finanzas.db",
        help="ruta de la base SQLite (por defecto DB_PATH, o finanzas.db)",
    )
    parser.add_argument(
        "--respaldos",
        default=RESPALDOS_POR_DEFECTO,
        help=f"carpeta donde dejar el respaldo previo (por defecto {RESPALDOS_POR_DEFECTO})",
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument(
        "--comprobar", action="store_true", help="solo decir si está al día (sale con 1 si no)"
    )
    grupo.add_argument("--bajar-a", metavar="REVISION", help="deshacer migraciones hasta esa revisión")
    return parser.parse_args(argv)


def _comprobar(ruta: str) -> int:
    if not Path(ruta).is_file():
        print("No existe la base de datos: ejecuta python -m finanzas.migrar.")
        return 1
    diagnostico = diagnosticar(ruta)
    if diagnostico.al_dia:
        print(f"La base está al día (revisión {diagnostico.actual}).")
        return 0
    if diagnostico.marcar_v1:
        print("La base es de la v1 y no tiene versión: hay que marcarla con python -m finanzas.migrar.")
    if diagnostico.pendientes:
        print(f"Migraciones pendientes: {', '.join(diagnostico.pendientes)}.")
    return 1


def _migrar(ruta: str, carpeta: str) -> int:
    diagnostico = diagnosticar(ruta)
    if diagnostico.al_dia:
        print(f"La base ya está al día (revisión {diagnostico.actual}). No se cambió nada.")
        return 0
    if diagnostico.marcar_v1:
        print(f"La base es de la v1 (sin versión) y su estructura coincide: se marca como {REVISION_V1}.")
    if diagnostico.base_nueva:
        print("Base nueva: no hay nada que respaldar.")
    else:
        copia = respaldar(ruta, carpeta, diagnostico.actual)
        print(f"Respaldo previo: {copia} ({copia.stat().st_size} bytes).")
    hecho = aplicar(ruta)
    if hecho.pendientes:
        print(f"Migraciones aplicadas: {', '.join(hecho.pendientes)}.")
    print(f"Listo: la base está en la revisión {revision_final()}.")
    return 0


def _bajar(ruta: str, carpeta: str, revision: str) -> int:
    if not _revision_conocida(revision):
        # También rechaza "base": borrar todas las tablas no es volver atrás.
        print(
            f"Revisión desconocida: {revision}. No se puede bajar de {REVISION_V1}: "
            "para volver a antes de las migraciones, restaura el respaldo previo.",
            file=sys.stderr,
        )
        return 1
    diagnostico = diagnosticar(ruta)
    if diagnostico.actual is None:
        print("La base no tiene versión: no hay nada que deshacer.", file=sys.stderr)
        return 1
    if diagnostico.actual == revision:
        print(f"La base ya está en la revisión {revision}. No se cambió nada.")
        return 0
    if revision not in {r.revision for r in _scripts().iterate_revisions(diagnostico.actual, "base")}:
        print(f"La revisión {revision} no es anterior a la actual ({diagnostico.actual}).", file=sys.stderr)
        return 1
    copia = respaldar(ruta, carpeta, diagnostico.actual)
    print(f"Respaldo previo: {copia} ({copia.stat().st_size} bytes).")
    deshechas = bajar_a(ruta, revision)
    print(f"Migraciones deshechas: {', '.join(deshechas)}. La base está en la revisión {revision}.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _argumentos(argv)
    except SystemExit as salida:  # argparse ya explicó el error
        return 0 if salida.code == 0 else 2

    # La base nueva, el respaldo y los -journal de SQLite: solo para el dueño.
    umask_anterior = os.umask(0o077)
    try:
        if args.comprobar:
            return _comprobar(args.base)
        if args.bajar_a:
            return _bajar(args.base, args.respaldos, args.bajar_a)
        return _migrar(args.base, args.respaldos)
    except ErrorMigracion as error:
        print(f"No se migró: {error}", file=sys.stderr)
        return 1
    except CommandError as error:
        # Una migración que se niega a seguir (p. ej. la 0005 al bajar, si
        # perdería datos) explica por qué con un texto propio, sin datos.
        print(f"No se migró: {error}", file=sys.stderr)
        return 1
    except _modulo_respaldo().ErrorRespaldo as error:
        print(f"No se migró: el respaldo previo falló ({error}).", file=sys.stderr)
        return 1
    except (SQLAlchemyError, sqlite3.Error, OSError) as error:
        # Solo el tipo: el texto de un error de la base podría citar datos.
        print(f"No se migró: error {type(error).__name__}. La base quedó como estaba.", file=sys.stderr)
        return 1
    finally:
        os.umask(umask_anterior)


if __name__ == "__main__":
    sys.exit(main())
