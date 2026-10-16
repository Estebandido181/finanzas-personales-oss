"""Ayudas compartidas extraídas de test_sincronizacion_retiro_qr_pse; datos inventados."""

from __future__ import annotations


import logging


from datetime import datetime


import pytest


from finanzas import categorizacion, db, sincronizacion


from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import DESCRIPCION_PAGO_QR


from finanzas.gmail import REMITENTE_AYN, REMITENTE_POR_DEFECTO, REMITENTES_OFICIALES, CorreoGmail


from finanzas.compartido.hora import ZONA_COLOMBIA


from finanzas.sincronizacion import ResultadoReproceso, ResultadoSincronizacion, reprocesar, sincronizar


from tests.soporte.ayudas_db import sql


from tests.soporte.gmail_falso import AUTENTICACION_LEGITIMA, ClienteFalso


ENCABEZADO = "¡Listo! Todo salió bien con tus movimientos"


PSE = ("Bancolombia: Pagaste $350,000.00 a EMPRESA EJEMPLO SAS desde tu producto 1234 el 04/09/2026 "
       "08:30:15. Si tienes dudas, llamanos al 000 000 0000.")


def _autenticacion_de(remitente: str) -> str:
    """El encabezado legítimo, con el subdominio de ``remitente`` en SPF."""
    return AUTENTICACION_LEGITIMA.replace(REMITENTE_POR_DEFECTO, remitente)


AN = {"remitente": REMITENTE_POR_DEFECTO, "autenticacion": _autenticacion_de(REMITENTE_POR_DEFECTO)}


AYN = {"remitente": REMITENTE_AYN, "autenticacion": _autenticacion_de(REMITENTE_AYN)}


def _otro(direccion: str) -> dict:
    return {"remitente": direccion, "autenticacion": _autenticacion_de(direccion)}


def _sin_dmarc_pass(autenticacion: str, cambio: str) -> str:
    if cambio == "fail":
        return autenticacion.replace("dmarc=pass", "dmarc=fail")
    if cambio == "sin_dmarc":
        return autenticacion.split(";\r\n       dmarc=")[0]
    if cambio == "otro_dominio":
        return autenticacion.replace("header.from=notificacionesbancolombia.com", "header.from=ejemplo-falso.com")
    if cambio == "vacio":
        return ""
    raise AssertionError(cambio)
