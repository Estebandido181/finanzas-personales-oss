"""Ayudas compartidas extraídas de test_api_arranque; datos inventados."""

from datetime import date


import pytest


from sqlalchemy import text


from fastapi.testclient import TestClient


from finanzas import db, gestion_importaciones as g


from finanzas.api.rutas_importacion import MIME_XLSX, TAMANO_MAXIMO_BYTES


from tests.soporte.excel_inventado import generar_excel


from tests.soporte.gmail_falso import ClienteFalso


from tests.soporte.ayudas_api import *  # noqa: F401,F403


def agregar(api, token=None, contenido=None, **headers):
    archivo = generar_excel([(date(2026, 7, 10), "TIENDA INVENTADA", "3000000009", -5)]) if contenido is None else contenido
    return api.cliente.post("/api/arranque/archivos", content=archivo,
        headers={"Content-Type": MIME_XLSX, "X-CSRF-Token": api.csrf,
            **({"X-Historial-Token": token} if token else {}), **headers})


def calcular(api, token, *, modo="arranque", saldo=100000):
    return api.post("/api/arranque/calcular", json={"token": token, "modo": modo, "saldo_actual_centavos": saldo})
