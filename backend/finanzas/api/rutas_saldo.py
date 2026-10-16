"""Adaptación HTTP: saldo."""
from __future__ import annotations
from fastapi import Depends, Request
from sqlalchemy import Connection
from finanzas.compartido import hora
from finanzas.api import tokens_ingreso
from finanzas.modulos.saldo import publico as saldo
from finanzas.flujos import reporte
from finanzas.infraestructura.persistencia import lectura_consistente
from finanzas.bootstrap.saldo import componer_saldo
from finanzas.api import modelos as m
from finanzas.api.dependencias import conexion, usuario_actual
from finanzas.api.comun import IdMovimiento, _CSRF, _ERROR_400, _ERROR_404, _ERROR_409, _ERROR_415, _error
from finanzas.api.mapeadores_deshacer import _deshacer
from finanzas.api.comun import crear_router



MENSAJE_TOKEN_INGRESO_INVALIDO = (
    "El formulario ya no es válido. Vuelve a abrir la pantalla de saldo e inténtalo de nuevo."
)

MENSAJE_INGRESO_REPETIDO = (
    "Este ingreso ya se envió. Revisa la lista de ingresos antes de volver a registrarlo."
)
router = crear_router()


def _hora_iso(momento) -> str:
    return momento.isoformat(timespec="seconds")


@router.get("/saldo", response_model=m.Saldo, summary="Saldo, ingresos y ajustes del mes")
def ver_saldo(
    request: Request,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.Saldo:
    """Saldo con su desglose, ingresos y ajustes del mes actual y total de ajustes del mes.

    Cada lectura con el saldo configurado emite un ``token_ingreso`` nuevo (de
    un solo uso). Todo sale de una sola lectura (la misma foto de la base).
    """
    ahora = hora.ahora_colombia()
    anio, numero = ahora.year, ahora.month
    comun = {
        "ahora": _hora_iso(ahora),
        "hoy": ahora.date().isoformat(),
        "mes": reporte.texto_mes(anio, numero),
        "nombre_mes": reporte.nombre_mes(anio, numero),
        "maximo_descripcion": saldo.MAXIMO_DESCRIPCION,
    }
    with lectura_consistente(conn):
        configuracion = componer_saldo(conn).leer_configuracion()
        # Misma regla que el PUT de la configuración (no se deduce del desglose).
        comun["configuracion_fija"] = componer_saldo(conn).configuracion_fija()
        if configuracion is None:
            return m.Saldo(
                configuracion=None, saldo_centavos=None, desglose=None, del_mes=[],
                ajustes_del_mes=None, ultimos=[], token_ingreso=None, fecha_hora_minima=None,
                **comun,
            )
        desde, hasta = reporte.limites_del_mes(anio, numero)
        desglose = componer_saldo(conn).desglose_saldo()
        del_mes = componer_saldo(conn).ingresos_y_ajustes_entre(desde, hasta)
        total_ajustes, cantidad_ajustes = componer_saldo(conn).ajustes_entre(desde, hasta)
        ultimos = componer_saldo(conn).ultimos_ingresos_y_ajustes()
    return m.Saldo(
        configuracion=m.ConfiguracionSaldo(
            saldo_inicial_centavos=configuracion.saldo_inicial_centavos,
            fecha_inicio=configuracion.fecha_inicio.isoformat(),
        ),
        saldo_centavos=desglose.saldo_centavos,
        desglose=m.DesgloseSaldo(
            saldo_inicial_centavos=desglose.saldo_inicial_centavos,
            ingresos_centavos=desglose.ingresos_centavos,
            gastos_centavos=desglose.gastos_centavos,
            ajustes_centavos=desglose.ajustes_centavos,
        ),
        del_mes=[m.IngresoOAjusteDelMes(**fila) for fila in del_mes],
        ajustes_del_mes=m.AjustesDelMes(total_centavos=total_ajustes, cantidad=cantidad_ajustes),
        ultimos=[m.IngresoOAjuste(**fila) for fila in ultimos],
        token_ingreso=tokens_ingreso.emitir(request),
        fecha_hora_minima=configuracion.fecha_inicio.isoformat() + "T00:00:00",
        **comun,
    )


@router.put(
    "/saldo/configuracion",
    response_model=m.ConfiguracionSaldo,
    dependencies=_CSRF,
    responses={**_ERROR_400, **_ERROR_415},
    summary="Configurar saldo inicial y fecha de inicio",
)
def configurar_saldo(
    datos: m.ConfigurarSaldoEntrada,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.ConfiguracionSaldo:
    """Solo mientras no haya movimientos (después se corrige con un ajuste)."""
    try:
        fecha = saldo.leer_fecha(datos.fecha_inicio)
        componer_saldo(conn).configurar(datos.saldo_inicial_centavos, fecha)
    except saldo.ErrorSaldo as error:
        raise _error(400, str(error)) from None
    return m.ConfiguracionSaldo(
        saldo_inicial_centavos=datos.saldo_inicial_centavos, fecha_inicio=fecha.isoformat()
    )


@router.post(
    "/ingresos",
    status_code=201,
    response_model=m.IngresoRegistrado,
    dependencies=_CSRF,
    responses={**_ERROR_400, **_ERROR_409, **_ERROR_415},
    summary="Registrar un ingreso manual",
)
def registrar_ingreso(
    datos: m.IngresoEntrada,
    request: Request,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.IngresoRegistrado:
    """Dinero que entra sin aviso por correo. ``token`` es el ``token_ingreso`` de ``GET /api/saldo``."""
    registro: tokens_ingreso.TokensIngreso = request.app.state.tokens_ingreso
    reserva = tokens_ingreso.reservar(request, registro, datos.token)
    if reserva is tokens_ingreso.Reserva.REPETIDO:
        raise _error(409, MENSAJE_INGRESO_REPETIDO)
    if reserva is tokens_ingreso.Reserva.INVALIDO:
        raise _error(400, MENSAJE_TOKEN_INGRESO_INVALIDO)
    try:
        momento = saldo.leer_fecha_hora(datos.fecha_hora)
        nuevo_id = componer_saldo(conn).registrar_ingreso(datos.monto_centavos, momento, datos.descripcion)
    except saldo.ErrorSaldo as error:
        registro.liberar(datos.token)  # no se guardó: corregido, el mismo token sigue sirviendo
        raise _error(400, str(error)) from None
    except Exception:
        registro.liberar(datos.token)
        raise
    tokens_ingreso.confirmar(request, datos.token)
    return m.IngresoRegistrado(id=nuevo_id, monto_centavos=datos.monto_centavos)


@router.post(
    "/ajustes",
    response_model=m.Ajuste,
    dependencies=_CSRF,
    responses={**_ERROR_400, **_ERROR_415},
    summary="Ajustar el saldo al real",
)
def ajustar_saldo(
    datos: m.AjusteEntrada,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.Ajuste:
    """Guarda la diferencia (saldo real − calculado). Si ya coincide, no guarda nada."""
    try:
        diferencia = componer_saldo(conn).ajustar_saldo(datos.saldo_real_centavos)
    except saldo.ErrorSaldo as error:
        raise _error(400, str(error)) from None
    # Justo después del ajuste, el saldo calculado es el real.
    return m.Ajuste(
        registrado=diferencia != 0,
        diferencia_centavos=diferencia,
        saldo_centavos=datos.saldo_real_centavos,
    )


@router.delete(
    "/ingresos/{movimiento_id}",
    response_model=m.IngresoBorrado,
    dependencies=_CSRF,
    responses={
        **_ERROR_404,
        409: {
            "model": m.Error,
            "description": "No se puede borrar: es un ajuste, viene de Gmail o es anterior al último ajuste.",
        },
    },
    summary="Borrar un ingreso manual",
)
def borrar_ingreso(
    request: Request,
    movimiento_id: int = IdMovimiento,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.IngresoBorrado:
    """Borra un ingreso registrado a mano por error; el saldo baja exactamente su monto.

    409 si es un ajuste, un movimiento de Gmail o un ingreso con algún ajuste
    posterior (la base no cambia); 404 si no existe. La regla vive en
    ``saldo.borrar_ingreso``, no aquí. ``deshacer`` (ítem 38): para
    restaurarlo unos segundos con ``POST /api/deshacer``.
    """
    try:
        copia, saldo_despues = componer_saldo(conn).borrar_ingreso_con_copia(movimiento_id)
    except saldo.MovimientoNoEncontrado as error:
        raise _error(404, str(error)) from None
    except saldo.BorradoNoPermitido as error:
        raise _error(409, str(error)) from None
    return m.IngresoBorrado(
        id=movimiento_id,
        monto_centavos=copia.monto_centavos,
        saldo_centavos=saldo_despues,
        deshacer=_deshacer(request, copia),
    )
