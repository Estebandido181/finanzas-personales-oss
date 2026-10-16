"""Adaptación HTTP: consultas_mes."""
from __future__ import annotations
from finanzas.flujos import reporte
from finanzas.api.comun import _error


def _leer_mes(mes: str | None) -> tuple[int, int]:
    try:
        return reporte.mes_actual() if mes is None else reporte.leer_mes(mes)
    except reporte.ErrorReporte as error:
        raise _error(400, str(error)) from None


def _mes_vecino(anio: int, mes: int) -> str | None:
    return reporte.texto_mes(anio, mes) if reporte.en_rango(anio, mes) else None
