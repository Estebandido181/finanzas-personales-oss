"""Hora de Colombia, en un solo lugar.

Colombia usa UTC-5 todo el año (sin horario de verano). Se usa un
desplazamiento fijo para no depender de la base de zonas horarias del sistema.

Los movimientos guardan su ``fecha_hora`` en hora de Colombia **sin zona**
(``2026-08-07T16:42:00``), igual que los avisos del banco. Por eso
``ahora_colombia`` devuelve un ``datetime`` sin zona: se puede comparar y
guardar directamente.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

ZONA_COLOMBIA = timezone(timedelta(hours=-5), "COT")


def ahora_colombia() -> datetime:
    """Fecha y hora actuales en Colombia, sin zona y sin microsegundos."""
    return datetime.now(ZONA_COLOMBIA).replace(tzinfo=None, microsecond=0)


def hoy_colombia() -> date:
    """Fecha de hoy en Colombia (usa ``ahora_colombia``)."""
    return ahora_colombia().date()


def a_hora_colombia(momento: datetime) -> datetime:
    """Pasa ``momento`` a hora de Colombia sin zona.

    Un ``datetime`` sin zona se supone ya en hora de Colombia y se devuelve
    igual; uno con zona se convierte.
    """
    if momento.tzinfo is None:
        return momento
    return momento.astimezone(ZONA_COLOMBIA).replace(tzinfo=None)
