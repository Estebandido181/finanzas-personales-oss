"""Ayudas compartidas extraídas de test_excel_bancolombia; datos inventados."""

from __future__ import annotations


import io


import time as reloj


import zipfile


from datetime import date, datetime


import pytest


from openpyxl import Workbook


from finanzas.modulos.importaciones.adaptadores.archivos import excel_bancolombia as eb


from tests.soporte import excel_inventado


from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import (
    ExcelNoReconocido,
    MovimientoExcel,
    leer_excel_movimientos,
    monto_a_centavos,
)


def reescribir(contenido, cambiar=None, agregar=None, quitar=(), renombrar=None):
    """Copia un .xlsx cambiando, agregando, quitando o renombrando partes del ZIP."""
    renombrar = renombrar or {}
    cambiar = cambiar or {}
    agregar = agregar or {}
    salida = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(contenido)) as origen, \
            zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as destino:
        for info in origen.infolist():
            if info.filename in quitar:
                continue
            datos = origen.read(info.filename)
            if info.filename in cambiar:
                datos = cambiar[info.filename](datos)
            destino.writestr(renombrar.get(info.filename, info.filename), datos)
        for nombre, datos in agregar.items():
            destino.writestr(nombre, datos)
    return salida.getvalue()
