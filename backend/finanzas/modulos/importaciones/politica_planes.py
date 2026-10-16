"""Preparación del plan: misma compensación inicial y cobertura del motor."""
from __future__ import annotations
from collections.abc import Sequence
from datetime import date
from . import motor as c
from .contratos import MovimientoExcel, Conteos, EstadoParaConciliar

def filas_desde_excel(movimientos: Sequence[MovimientoExcel]) -> list[c.FilaBanco]:
    return [c.FilaBanco(m.fecha, m.monto_centavos, m.descripcion, m.referencia) for m in movimientos]


def conteos(plan: c.Plan, sin_formato: int = 0) -> Conteos:
    return Conteos(
        filas=plan.filas,
        ya_estaban=len(plan.ya_estaban) + len(plan.descartadas),
        ya_preguntadas=len(plan.ya_preguntadas),
        confirmados=len(plan.confirmar),
        corregidos=len(plan.corregir),
        agregados=len(plan.agregar),
        preguntas_es_el_mismo=sum(p.tipo == c.PREGUNTA_ES_EL_MISMO for p in plan.preguntas),
        preguntas_ajuste=sum(p.tipo == c.PREGUNTA_YA_ESTABA for p in plan.preguntas),
        no_en_banco=len(plan.marcar),
        anteriores=plan.anteriores,
        sin_formato=sin_formato,
        ajuste_reducido=bool(plan.reduccion_ajuste),
    )



def preparar_plan(filas: Sequence[c.FilaBanco], estado: EstadoParaConciliar,
                  cobertura: Sequence[tuple[date, date]] | None = None,
                  compensar_en_inicial_antes: date | None = None) -> c.Plan:
    plan = c.conciliar(filas, estado.movimientos, estado.fecha_inicio, estado.ultimo_ajuste,
                       estado.preguntas_pendientes, estado.descartes, estado.elecciones)
    if compensar_en_inicial_antes is not None and estado.ultimo_ajuste is not None:
        # Extender historial31 compensa el pasado nuevo con el saldo
        # inicial. El último ajuste pertenecía al periodo ya configurado:
        # no debe absorber también los mismos efectos anteriores al inicio.
        limite = min(compensar_en_inicial_antes, estado.ultimo_ajuste.fecha)
        efecto = sum(f.monto_centavos for f in plan.agregar if f.fecha < limite)
        movimientos = {m.id: m for m in estado.movimientos}
        efecto += sum(p.fila.monto_centavos - c.monto_con_signo(movimientos[p.movimiento_id])
            for p in plan.corregir if p.fila.fecha < limite)
        plan.reduccion_ajuste -= efecto
        if plan.reduccion_ajuste == 0:
            plan.ajuste_id = None
    if cobertura is not None:
        # Ítem31: varias descargas no acreditan los días entre archivos.
        # Cada frontera truncada conserva su protección. Solo restringe
        # marcas del motor: nunca crea una ausencia adicional ni cambia
        # su emparejamiento. El día más antiguo de cada archivo nunca marca
        # (D51), y el motor tampoco marca el día más antiguo de la unión.
        por_id = {m.id: m.fecha for m in estado.movimientos}
        plan.marcar = [ident for ident in plan.marcar if any(
            desde <= por_id[ident] <= hasta for desde, hasta in cobertura)]
    return plan
