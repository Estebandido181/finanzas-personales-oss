"""Adaptación HTTP: movimientos."""
from __future__ import annotations
from fastapi import Depends, Query
from sqlalchemy import Connection
from dataclasses import asdict
from finanzas.modulos.categorias import publico as categorizacion
from finanzas.modulos.movimientos import descartes_contratos as descartes
from finanzas.flujos import reporte
from finanzas.infraestructura.persistencia import lectura_consistente
from finanzas.bootstrap.categorias import componer_catalogo_categorias
from finanzas.bootstrap.descartes import componer_descartes
from finanzas.bootstrap.reporte import componer_reporte
from finanzas.api import modelos as m
from finanzas.api.dependencias import conexion, usuario_actual
from finanzas.api.comun import IdMovimiento, ParametroMes, _CSRF, _ERROR_400, _ERROR_404, _ERROR_409, _ERROR_415, _error
from finanzas.api.consultas_mes import _leer_mes
from finanzas.api.mapeadores_movimientos import _grupo, _movimiento
from finanzas.api.comun import crear_router

router = crear_router()


@router.get(
    "/movimientos", response_model=m.MovimientosDelMes, responses=_ERROR_400, summary="Movimientos del mes"
)
def ver_movimientos(
    mes: str | None = ParametroMes,
    tipo: m.TipoFiltro | None = Query(
        None, description="Solo este tipo; «gasto» son las compras y las transferencias."
    ),
    categoria_id: int | None = Query(
        None, ge=1, le=m.MAXIMO_ID, description="Solo los movimientos (gastos o ingresos) con esta categoría."
    ),
    sin_categoria: bool = Query(
        False,
        description="Solo los pendientes del mes (gastos e ingresos sin categoría). No se combina con categoria_id.",
    ),
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.MovimientosDelMes:
    """Los movimientos del mes, del más reciente al más antiguo, con los filtros pedidos.

    Cada uno dice cómo se categorizó (``origen_categoria``) y por qué regla (``regla``).
    """
    with lectura_consistente(conn):
        anio, numero = _leer_mes(mes)
        informe = componer_reporte(conn).reporte_mensual(anio, numero)
        try:
            filtrados = reporte.filtrar_movimientos(
                informe.movimientos, tipo=tipo, categoria_id=categoria_id, sin_categoria=sin_categoria
            )
        except reporte.ErrorReporte as error:
            raise _error(400, str(error)) from None
        return m.MovimientosDelMes(
            mes=reporte.texto_mes(anio, numero),
            movimientos=[_movimiento(mov, conn) for mov in filtrados],
        )


@router.get(
    "/movimientos/sin-categorizar", response_model=m.SinCategorizar, summary="Bandeja Sin categorizar"
)
def ver_sin_categorizar(
    usuario: m.Usuario = Depends(usuario_actual), conn: Connection = Depends(conexion)
) -> m.SinCategorizar:
    """Los pendientes de todos los meses, gastos e ingresos, del más reciente al más antiguo.

    Mismo esquema ``Movimiento`` que ``GET /api/movimientos``: sin categoría,
    ``pendiente: true``, la ``clase_categoria`` que aceptan y la
    ``regla_posible`` de cada uno. ``es_gasto`` distingue los gastos de los
    ingresos (sus montos no se suman entre sí).
    """
    with lectura_consistente(conn):
        filas = [asdict(fila) for fila in componer_catalogo_categorias(conn).pendientes()]
        return m.SinCategorizar(
            total=len(filas),
            grupos=[_grupo(g) for g in categorizacion.agrupar_pendientes(filas)],
            movimientos=[
                _movimiento(
                    reporte.MovimientoReporte(
                        id=int(fila["id"]),
                        fecha_hora=str(fila["fecha_hora"]),
                        tipo=str(fila["tipo"]),
                        descripcion=str(fila["descripcion"]),
                        categoria=reporte.SIN_CATEGORIZAR,
                        monto_centavos=int(fila["monto_centavos"]),
                        es_gasto=reporte.es_gasto(fila["tipo"]),
                        origen=str(fila["origen"]),
                    ), conn
                )
                for fila in filas
            ],
        )


@router.get("/movimientos/descartados", response_model=m.MovimientosDescartados,
            summary="Movimientos automáticos descartados")
def ver_descartados(usuario: m.Usuario = Depends(usuario_actual),
                    conn: Connection = Depends(conexion)) -> m.MovimientosDescartados:
    return m.MovimientosDescartados(**componer_descartes(conn).listar())


def _cambiar_descarte(conn, movimiento_id, *, restaurar=False):
    try:
        return m.ResultadoDescarte(**componer_descartes(conn).cambiar(movimiento_id, restaurar=restaurar))
    except descartes.MovimientoInexistente as error:
        raise _error(404, str(error)) from None
    except descartes.DescarteNoPermitido as error:
        raise _error(409, str(error)) from None


@router.post("/movimientos/{movimiento_id}/descartar", response_model=m.ResultadoDescarte,
             dependencies=_CSRF, responses={**_ERROR_404, **_ERROR_409, **_ERROR_415},
             summary="Descartar un movimiento automático")
def descartar_movimiento(movimiento_id: int = IdMovimiento,
                         usuario: m.Usuario = Depends(usuario_actual),
                         conn: Connection = Depends(conexion)) -> m.ResultadoDescarte:
    return _cambiar_descarte(conn, movimiento_id)


@router.post("/movimientos/{movimiento_id}/restaurar", response_model=m.ResultadoDescarte,
             dependencies=_CSRF, responses={**_ERROR_404, **_ERROR_409, **_ERROR_415},
             summary="Restaurar un movimiento automático descartado")
def restaurar_movimiento(movimiento_id: int = IdMovimiento,
                         usuario: m.Usuario = Depends(usuario_actual),
                         conn: Connection = Depends(conexion)) -> m.ResultadoDescarte:
    return _cambiar_descarte(conn, movimiento_id, restaurar=True)
