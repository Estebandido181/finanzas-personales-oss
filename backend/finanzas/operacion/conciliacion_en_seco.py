"""Conciliación en seco (ítem 29, D44): el motor con el Excel real, sin guardar nada.

Antes de activar la importación (ítem 30), el dueño corre en la VM el motor
de conciliación con su reporte real del banco y su base real, y ve **solo
conteos**: cuántas filas ya estaban, cuántas faltaban, cuántas se
preguntarían y cuántos movimientos del correo no están en el banco. Nunca
montos, nombres, descripciones, fechas, cuentas ni referencias.

Qué hace, igual que la prueba en seco del lector de avisos
(``finanzas.prueba_en_seco``):

1. lee el archivo de la ruta dada, o de la entrada estándar con ``-`` (así
   en la VM el servicio no necesita leer la carpeta del dueño), con el mismo
   lector y las mismas revisiones de seguridad que usará la importación
   (``excel_bancolombia.leer_excel_movimientos``). El archivo no se copia ni
   se guarda en ninguna parte;
2. abre la base **en solo lectura** (``mode=ro``) y le pide al motor su plan
   (``importacion.planear``), sin llamar a nada que guarde;
3. imprime los conteos.

Funciona con la base en la 0008 y también en la 0007 (sin las columnas
nuevas, todo lo del correo cuenta como sin conciliar).

Uso::

    python -m finanzas.conciliacion_en_seco RUTA.xlsx
    python -m finanzas.conciliacion_en_seco - < RUTA.xlsx

Códigos de salida: 0 terminó; 1 error inesperado (solo se muestra su tipo);
2 falta configuración, la base o el archivo no se puede leer como reporte.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from finanzas.modulos.importaciones import publico as importacion
from finanzas.modulos.importaciones.politica_planes import filas_desde_excel, conteos
from finanzas.bootstrap.importaciones import componer_reportes
from finanzas.compartido.config import Config, ErrorConfiguracion
from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import TAMANO_MAXIMO_BYTES, ExcelNoReconocido, leer_excel_movimientos


class BaseNoDisponible(Exception):
    """La base no existe o no se puede abrir (el mensaje no lleva datos)."""


def conectar_solo_lectura(ruta_db: str):
    """Conexión de SQLAlchemy a la base en solo lectura: ninguna escritura es posible."""
    ruta = Path(ruta_db)
    if not ruta.is_file():
        raise BaseNoDisponible(f"No existe la base en {ruta} (variable DB_PATH).")
    uri = f"{ruta.resolve().as_uri()}?mode=ro"
    motor = create_engine(
        "sqlite://", creator=lambda: sqlite3.connect(uri, uri=True), poolclass=NullPool,
        hide_parameters=True,
    )
    return motor.connect()


def leer_archivo(origen: BinaryIO) -> bytes:
    """Lee como máximo el tamaño permitido + 1 byte (el lector rechaza lo que sobre)."""
    return origen.read(TAMANO_MAXIMO_BYTES + 1)


def calcular(contenido: bytes, ruta_db: str, nombre_archivo: str | None = None) -> importacion.Conteos:
    """Conteos del plan del motor para este archivo y esta base. No escribe nada."""
    movimientos = leer_excel_movimientos(contenido, nombre_archivo=nombre_archivo)
    filas = filas_desde_excel(movimientos)
    sin_formato = sum(1 for m in movimientos if m.referencia_sin_formato)
    conn = conectar_solo_lectura(ruta_db)
    try:
        plan = componer_reportes(conn).planear(filas)
    finally:
        conn.close()
    return conteos(plan, sin_formato)


def informe(cuentas: importacion.Conteos) -> list[str]:
    """Líneas de la salida: solo conteos (D44)."""
    ya = cuentas.ya_estaban + cuentas.ya_preguntadas + cuentas.confirmados + cuentas.corregidos
    lineas = [
        f"Conciliación en seco (no se guardó nada). Filas del reporte: {cuentas.filas}.",
        f"Resumen: {ya} ya estaban, {cuentas.agregados} faltaban, {cuentas.preguntas} para preguntar, "
        f"{cuentas.no_en_banco} no están en el banco.",
        "Detalle:",
        f"- ya importadas antes (no cambiarían): {cuentas.ya_estaban + cuentas.ya_preguntadas}"
        + (f" (de ellas, {cuentas.ya_preguntadas} esperan tu respuesta)" if cuentas.ya_preguntadas else ""),
        f"- llegaron por correo o a mano y el banco las confirmaría: {cuentas.confirmados}",
        f"- montos parecidos que se corregirían al monto del banco: {cuentas.corregidos}",
        f"- faltaban y entrarían sin aviso: {cuentas.agregados}",
        f"- para preguntar \"¿es el mismo?\": {cuentas.preguntas_es_el_mismo}",
        f"- para preguntar \"¿ya estaba en el saldo que ajustaste?\": {cuentas.preguntas_ajuste}",
        f"- del correo que no están en el banco (se marcarían, nada se borra): {cuentas.no_en_banco}",
        f"- anteriores a tu fecha de inicio (no se importarían): {cuentas.anteriores}",
        f"- con Referencia sin formato (entrarían sin destino): {cuentas.sin_formato}",
        "- el último ajuste se reduciría: " + ("sí" if cuentas.ajuste_reducido else "no"),
    ]
    return lineas


def main(argv: list[str] | None = None, entrada: BinaryIO | None = None) -> int:
    """Punto de entrada de ``python -m finanzas.conciliacion_en_seco``."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="python -m finanzas.conciliacion_en_seco",
        description="Corre el motor de conciliación con un reporte del banco, sin guardar nada, "
        "y muestra solo conteos.",
    )
    parser.add_argument("archivo", help="ruta del .xlsx descargado del banco, o - para leerlo de la entrada estándar")
    args = parser.parse_args(argv)
    try:
        config = Config.desde_entorno()
    except ErrorConfiguracion as error:
        print(f"Error de configuración: {error}", file=sys.stderr)
        return 2
    try:
        if args.archivo == "-":
            contenido = leer_archivo(entrada or sys.stdin.buffer)
            nombre = None
        else:
            with open(args.archivo, "rb") as origen:
                contenido = leer_archivo(origen)
            nombre = Path(args.archivo).name
        cuentas = calcular(contenido, config.db_path, nombre)
    except OSError as error:
        print(f"No se pudo leer el archivo ({type(error).__name__}).", file=sys.stderr)
        return 2
    except ExcelNoReconocido as error:
        # El motivo nunca trae datos del archivo (ver excel_bancolombia).
        print(f"El archivo no se reconoce como reporte del banco: {error.motivo}", file=sys.stderr)
        return 2
    except (BaseNoDisponible, importacion.SinConfiguracion) as error:
        print(f"No se pudo hacer la conciliación en seco: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        # Solo el tipo: el mensaje de una excepción podría traer datos.
        print(f"La conciliación en seco falló ({type(error).__name__}).", file=sys.stderr)
        return 1
    for linea in informe(cuentas):
        print(linea)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
