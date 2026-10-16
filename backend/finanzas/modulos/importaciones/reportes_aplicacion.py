"""Coordinación de planes por puertos; sin SQL ni conexiones externas."""
from __future__ import annotations
from collections.abc import Sequence
from contextlib import nullcontext
from datetime import date
from . import motor as c
from .contratos import MovimientoExcel, ResumenImportacion, UnidadReporte
from .politica_planes import filas_desde_excel, conteos, preparar_plan


class OperarReportes:
    def __init__(self, unidad: UnidadReporte):
        self._unidad = unidad

    def planear(self, filas: Sequence[c.FilaBanco]) -> c.Plan:
        estado = self._unidad.importaciones.leer_estado(filas)
        return preparar_plan(filas, estado)

    def importar(self, movimientos_excel: Sequence[MovimientoExcel], *, transaccion_externa: bool = False,
                 cobertura: Sequence[tuple[date, date]] | None = None,
                 compensar_en_inicial_antes: date | None = None) -> ResumenImportacion:
        filas = filas_desde_excel(movimientos_excel)
        sin_formato = sum(1 for m in movimientos_excel if m.referencia_sin_formato)
        with nullcontext() if transaccion_externa else self._unidad.escritura(inmediata=True):
            registro = self._unidad.importaciones
            estado = registro.leer_estado(filas)
            plan = preparar_plan(filas, estado, cobertura, compensar_en_inicial_antes)
            resumen = conteos(plan, sin_formato)
            importacion_id = registro.crear_resumen(plan, resumen, sin_formato)
            for par in plan.confirmar:
                registro.confirmar(importacion_id, par.fila, par.movimiento_id, corregir=False)
            for par in plan.corregir:
                registro.confirmar(importacion_id, par.fila, par.movimiento_id, corregir=True)
            for par in plan.descartadas:
                registro.confirmar_descarte(importacion_id, par.fila, par.movimiento_id)
            for fila in plan.agregar:
                registro.agregar(importacion_id, fila)
            ajuste_id = None if estado.ultimo_ajuste is None else estado.ultimo_ajuste.id
            for pregunta in plan.preguntas:
                registro.crear_pregunta(importacion_id, pregunta, ajuste_id)
            for movimiento_id in plan.marcar:
                registro.marcar_ausencia(importacion_id, movimiento_id)
            if plan.ajuste_id is not None:
                registro.reducir_ajuste(importacion_id, plan.ajuste_id, plan.reduccion_ajuste)
        return ResumenImportacion(importacion_id, resumen)
