#!/usr/bin/env python3
"""Respaldo diario de la base SQLite (ítem 07).

Solo usa la librería estándar, para que funcione aunque el entorno virtual de
la app esté roto. Lo ejecuta ``finanzas-respaldo.service`` una vez al día::

    python3 deploy/respaldo.py --origen /var/lib/finanzas/finanzas.db \\
        --destino /var/backups/finanzas --dias 14

Qué hace:

1. Copia la base con la API de respaldo de SQLite
   (``sqlite3.Connection.backup``). Es una copia consistente aunque la app o
   la sincronización estén escribiendo: SQLite toma un bloqueo de lectura y
   copia una foto completa de la base (copiar el archivo con ``cp`` podría
   dejar una transacción a medias).
2. La escribe primero en un archivo temporal de la carpeta de destino, creado
   con permisos 0600, y comprueba la copia con ``PRAGMA integrity_check``.
3. Solo si está bien, la mueve con ``os.replace`` a
   ``finanzas-AAAA-MM-DD.db`` (fecha local del sistema). Así nunca queda un
   respaldo a medio escribir con el nombre definitivo.
4. Borra los respaldos de más de ``--dias`` días (14 por defecto). Solo toca
   archivos normales que siguen exactamente el patrón ``finanzas-AAAA-MM-DD.db``
   y nunca el de hoy.

Códigos de salida: 0 todo bien; 1 algo falló (no hay base de origen, la
carpeta de destino no existe, la copia no pasó la comprobación, etc.);
2 argumentos inválidos.

Registros: solo nombres de archivo, tamaños y contadores. Nunca el contenido
de la base ni el texto de los errores de SQLite (solo su tipo).
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sqlite3
import stat
import sys
import tempfile
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from urllib.parse import quote

logger = logging.getLogger("respaldo")

DIAS_POR_DEFECTO = 14
# [0-9] y no \d: \d también acepta dígitos Unicode (p. ej. "２０２０").
PATRON_RESPALDO = re.compile(r"finanzas-([0-9]{4})-([0-9]{2})-([0-9]{2})\.db")
# Tiempo máximo (segundos) que se espera si la app tiene la base bloqueada.
ESPERA_BLOQUEO = 60


class ErrorRespaldo(Exception):
    """El respaldo no se pudo crear. El mensaje no lleva datos de la base."""


def nombre_respaldo(dia: date) -> str:
    return f"finanzas-{dia.isoformat()}.db"


def fecha_de_respaldo(nombre: str) -> date | None:
    """La fecha de un nombre ``finanzas-AAAA-MM-DD.db``, o ``None`` si no sigue el patrón."""
    coincidencia = PATRON_RESPALDO.fullmatch(nombre)
    if not coincidencia:
        return None
    try:
        return date(*(int(parte) for parte in coincidencia.groups()))
    except ValueError:  # p. ej. finanzas-2026-13-40.db
        return None


def _abrir_origen(origen: Path) -> sqlite3.Connection:
    # mode=rw: nunca crea una base vacía si la ruta está mal escrita.
    # No se usa mode=ro porque, si la app se cayó a mitad de una transacción,
    # SQLite necesita escribir para deshacerla antes de poder leer.
    uri = f"file:{quote(str(origen.resolve()))}?mode=rw"
    return sqlite3.connect(uri, uri=True, timeout=ESPERA_BLOQUEO)


def _comprobar_integridad(ruta: Path) -> None:
    conn = sqlite3.connect(f"file:{quote(str(ruta))}?mode=ro", uri=True)
    try:
        filas = conn.execute("PRAGMA integrity_check").fetchall()
    finally:
        conn.close()
    if filas != [("ok",)]:
        # No se registran las filas: podrían citar contenido de la base.
        raise ErrorRespaldo("la copia no pasó PRAGMA integrity_check")


def _sincronizar_carpeta(carpeta: Path) -> None:
    descriptor = os.open(carpeta, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def crear_respaldo(origen: Path, destino: Path, hoy: date, nombre: str | None = None) -> Path:
    """Crea ``destino/finanzas-<hoy>.db`` (0600) y devuelve su ruta.

    Si ya existía el respaldo de hoy, lo reemplaza por uno nuevo.
    ``nombre`` cambia el nombre del archivo: lo usa ``python -m
    finanzas.migrar`` para el respaldo previo a migrar
    (``finanzas-antes-de-migrar-...db``), que no sigue el patrón de la
    rotación y por eso nunca se borra solo.
    Lanza ``ErrorRespaldo`` si algo falla; en ese caso no deja temporales.
    """
    if not origen.is_file():
        raise ErrorRespaldo("no existe la base de origen")
    if not destino.is_dir():
        # No se crea: una carpeta que falta suele ser un error de configuración,
        # y crearla en silencio escondería el problema.
        raise ErrorRespaldo("no existe la carpeta de destino")

    if nombre is not None and (Path(nombre).name != nombre or nombre.startswith(".")):
        raise ErrorRespaldo("nombre de respaldo no válido")
    final = destino / (nombre or nombre_respaldo(hoy))
    # mkstemp crea el archivo con 0600 y un nombre que no sigue el patrón,
    # así que la rotación nunca lo toca.
    descriptor, crudo = tempfile.mkstemp(dir=destino, prefix=".finanzas-", suffix=".db.tmp")
    temporal = Path(crudo)
    try:
        os.fchmod(descriptor, 0o600)
        os.close(descriptor)
        fuente = _abrir_origen(origen)
        try:
            copia = sqlite3.connect(temporal)
            try:
                # pages=-1: todo de una vez, bajo un único bloqueo de lectura.
                fuente.backup(copia, pages=-1)
            finally:
                copia.close()
        finally:
            fuente.close()
        _comprobar_integridad(temporal)
        with open(temporal, "rb") as archivo:
            os.fsync(archivo.fileno())
        os.replace(temporal, final)
        _sincronizar_carpeta(destino)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise
    return final


def rotar(destino: Path, hoy: date, dias: int) -> list[Path]:
    """Borra los respaldos con más de ``dias`` días de antigüedad y devuelve cuáles.

    Nunca borra el de hoy, ni los de fecha futura, ni nada que no sea un
    archivo normal llamado exactamente ``finanzas-AAAA-MM-DD.db``.
    """
    if dias < 1:
        raise ValueError("dias debe ser al menos 1")
    borrados: list[Path] = []
    for entrada in sorted(destino.iterdir()):
        fecha = fecha_de_respaldo(entrada.name)
        if fecha is None or fecha >= hoy:
            continue
        if not stat.S_ISREG(entrada.lstat().st_mode):  # ni enlaces ni carpetas
            continue
        if (hoy - fecha).days > dias:
            entrada.unlink()
            borrados.append(entrada)
    return borrados


def _dias(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError:
        raise argparse.ArgumentTypeError("debe ser un número entero") from None
    if valor < 1:
        raise argparse.ArgumentTypeError("debe ser al menos 1")
    return valor


def _argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Respaldo diario de la base de Finanzas personales.")
    parser.add_argument("--origen", required=True, type=Path, help="base SQLite de la app (DB_PATH)")
    parser.add_argument("--destino", required=True, type=Path, help="carpeta de los respaldos")
    parser.add_argument(
        "--dias",
        type=_dias,
        default=DIAS_POR_DEFECTO,
        help=f"borrar respaldos con más de estos días (por defecto {DIAS_POR_DEFECTO})",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, hoy: date | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        args = _argumentos(argv)
    except SystemExit as salida:  # argparse ya explicó el error
        return 0 if salida.code == 0 else 2
    hoy = hoy or date.today()

    # Que ningún archivo auxiliar de SQLite (el -journal de la copia) quede
    # legible por otros usuarios. Se restaura al terminar (importa en pruebas).
    umask_anterior = os.umask(0o077)
    try:
        final = crear_respaldo(args.origen, args.destino, hoy)
    except ErrorRespaldo as error:
        logger.error("Respaldo fallido: %s.", error)
        return 1
    except (sqlite3.Error, OSError) as error:
        # Solo el tipo: el texto de un error podría citar rutas o datos.
        logger.error("Respaldo fallido (%s).", type(error).__name__)
        return 1
    finally:
        os.umask(umask_anterior)
    logger.info("Respaldo creado: %s (%d bytes).", final.name, final.stat().st_size)

    try:
        borrados = rotar(args.destino, hoy, args.dias)
    except OSError as error:
        logger.error("No se pudieron borrar los respaldos antiguos (%s).", type(error).__name__)
        return 1
    for ruta in borrados:
        logger.info("Respaldo antiguo borrado: %s.", ruta.name)
    logger.info("Rotación terminada: %d borrados, se conservan %d días.", len(borrados), args.dias)
    return 0


if __name__ == "__main__":
    sys.exit(main())
