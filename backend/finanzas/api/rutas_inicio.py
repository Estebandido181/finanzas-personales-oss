"""Adaptación HTTP: inicio."""
from __future__ import annotations
from fastapi import Depends
from sqlalchemy import Connection
from finanzas.flujos import reporte
from finanzas.infraestructura.persistencia import lectura_consistente
from finanzas.bootstrap.categorias import componer_catalogo_categorias
from finanzas.bootstrap.saldo import componer_saldo
from finanzas.bootstrap.reporte import componer_reporte
from finanzas.bootstrap.flujos import componer_inicio
from finanzas.api import modelos as m
from finanzas.api.dependencias import conexion, usuario_actual
from finanzas.api.comun import ParametroMes, _ERROR_400
from finanzas.api.consultas_mes import _leer_mes, _mes_vecino
from finanzas.api.comun import crear_router

router = crear_router()


@router.get("/inicio/estado", response_model=m.EstadoInicio, summary="Acciones pendientes del Inicio")
def ver_estado_inicio(
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.EstadoInicio:
    return m.EstadoInicio(**componer_inicio(conn))


@router.get("/reporte", response_model=m.Reporte, responses=_ERROR_400, summary="Reporte del mes")
def ver_reporte(
    mes: str | None = ParametroMes,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.Reporte:
    anio, numero = _leer_mes(mes)
    # Una sola lectura: pendientes, saldo y reporte ven la misma foto de la base.
    with lectura_consistente(conn):
        pendientes = componer_catalogo_categorias(conn).resumen_pendientes()
        configurado = componer_saldo(conn).leer_configuracion() is not None
        saldo_centavos = componer_saldo(conn).saldo_actual() if configurado else None
        informe = componer_reporte(conn).reporte_mensual(anio, numero)
    return m.Reporte(
        mes=reporte.texto_mes(anio, numero),
        nombre_mes=reporte.nombre_mes(anio, numero),
        es_mes_actual=(anio, numero) == reporte.mes_actual(),
        mes_anterior=_mes_vecino(*reporte.mes_anterior(anio, numero)),
        mes_siguiente=_mes_vecino(*reporte.mes_siguiente(anio, numero)),
        total_gasto_centavos=informe.total_gasto_centavos,
        total_ingresos_centavos=informe.total_ingresos_centavos,
        por_categoria=[
            m.GastoCategoria(
                nombre=g.nombre,
                centavos=g.centavos,
                porcentaje=g.porcentaje,
                categoria=(
                    None
                    if g.categoria_id is None
                    else m.Categoria(
                        id=g.categoria_id, nombre=g.nombre, clase="gasto", color=g.color, icono=g.icono
                    )
                ),
            )
            for g in informe.por_categoria
        ],
        pendientes=pendientes.cuantos,
        pendientes_centavos=pendientes.gastos_centavos,
        pendientes_ingresos_centavos=pendientes.ingresos_centavos,
        saldo_centavos=saldo_centavos,
    )
