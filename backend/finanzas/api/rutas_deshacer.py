"""Adaptación HTTP: deshacer."""
from __future__ import annotations
from fastapi import Depends, Request
from sqlalchemy import Connection
from finanzas.api import deshacer
from finanzas.modulos.categorias import publico as categorizacion
from finanzas.modulos.saldo import publico as saldo
from finanzas.api import modelos as m
from finanzas.api.dependencias import conexion, usuario_actual
from finanzas.api.comun import _CSRF, _ERROR_415, _error
from finanzas.api.comun import crear_router



MENSAJE_YA_NO_SE_PUEDE_DESHACER = "Ya no se puede deshacer: pasó el tiempo o ya se deshizo."
router = crear_router()


@router.post(
    "/deshacer",
    response_model=m.Deshecho,
    dependencies=_CSRF,
    responses={
        **_ERROR_415,
        409: {
            "model": m.Error,
            "description": "Ya no se puede restaurar: algo cambió mientras tanto (un ajuste posterior, "
            "un reporte del banco importado después de borrar el ingreso, o una regla o categoría que "
            "ocupó su lugar).",
        },
        410: {"model": m.Error, "description": "Token vencido, ya usado, de otra sesión o desconocido."},
    },
    summary="Deshacer un borrado",
)
def deshacer_borrado(
    datos: m.DeshacerEntrada,
    request: Request,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.Deshecho:
    """Restaura lo borrado con el ``token`` que dio el DELETE (ingreso, regla o categoría vacía).

    El token vale una sola vez, en esta sesión y durante ``segundos``; si no,
    410. Restaurar respeta las mismas reglas que crear y borrar: 409 (sin
    cambiar nada) si un ajuste posterior lo impide, si se importó un reporte
    del banco después de borrar el ingreso (ítem 29: ese reporte pudo agregar
    su depósito sin aviso y restaurarlo lo contaría dos veces), si la
    categoría de una regla ya no existe o si otra regla o categoría ocupó su
    lugar. Lo
    restaurado queda como antes (el mismo id si seguía libre; el saldo, igual
    que antes de borrar).
    """
    pendiente = deshacer.tomar(request, request.app.state.deshacer, datos.token)
    if pendiente is None:
        raise _error(410, MENSAJE_YA_NO_SE_PUEDE_DESHACER)
    copia = pendiente.copia
    try:
        from finanzas.bootstrap.flujos import restaurar_borrado
        resultado = restaurar_borrado(conn, copia)
        if resultado is not None:
            return m.Deshecho(**resultado)
    except (saldo.RestauracionNoPermitida, categorizacion.RestauracionNoPermitida) as error:
        raise _error(409, str(error)) from None
    raise _error(410, MENSAJE_YA_NO_SE_PUEDE_DESHACER)  # pragma: no cover - solo se guardan esas copias
