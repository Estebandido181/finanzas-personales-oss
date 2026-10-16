"""Ayudas compartidas extraídas de test_extractor; datos inventados."""

from datetime import datetime


from pathlib import Path


import pytest


from finanzas.modulos.sincronizacion.adaptadores.avisos.extractor import (
    MovimientoExtraido,
    extraer,
    extraer_compraste,
    extraer_transferiste,
)


def transferiste(monto="$6,000.00", fecha="15/03/26", hora="09:15"):
    return (
        f"Bancolombia: Transferiste {monto} desde tu cuenta *1234 a la cuenta *5678 "
        f"el {fecha} a las {hora}."
    )
