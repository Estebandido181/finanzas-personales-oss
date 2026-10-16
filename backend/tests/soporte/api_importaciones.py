"""Ayudas compartidas extraídas de test_api_importaciones; datos inventados."""

from datetime import date, datetime


import pytest


from sqlalchemy import text


from finanzas import db


from finanzas.api.rutas_importacion import MIME_XLSX, TAMANO_MAXIMO_BYTES


from tests.soporte.excel_inventado import generar_excel


from tests.soporte.ayudas_api import *  # noqa: F401,F403


def excel():
    return generar_excel([(date(2026, 8, 10), "TIENDA EJEMPLO", "3000000009", -500)])


PRIMER_DIA = (date(2026, 8, 9), "ANCLA INVENTADA", None, -777)


def primer_dia(config):
    """Correo categorizado del día 9 cuya fila va primero en el reporte: el día
    más antiguo de un reporte nunca marca "no está en el banco" (D51). Su
    correo ya cuenta en el saldo y la fila lo confirma sin moverlo."""
    insertar_movimiento(config, fecha_hora="2026-08-09T10:00:00", monto=77700, descripcion="ANCLA INVENTADA",
                        categoria_id=1)
    return PRIMER_DIA


def excel_con_primer_dia(config):
    return generar_excel([primer_dia(config), (date(2026, 8, 10), "TIENDA EJEMPLO", "3000000009", -500)])


def analizar(api, contenido=None, **headers):
    return api.cliente.post("/api/importaciones/analizar", content=excel() if contenido is None else contenido,
        headers={"Content-Type": MIME_XLSX, "X-CSRF-Token": api.csrf, "X-Nombre-Archivo": "reporte-inventado.xlsx", **headers})
