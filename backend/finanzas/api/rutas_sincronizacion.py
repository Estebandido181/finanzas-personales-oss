"""Adaptación HTTP: sincronizacion."""
from __future__ import annotations
import threading
from fastapi import Depends, Path, Request
from sqlalchemy import Connection
from finanzas.modulos.sincronizacion import publico as sincronizacion
from finanzas.infraestructura.persistencia import lectura_consistente
from finanzas.bootstrap.sincronizacion import componer_sincronizacion, componer_registro_sincronizacion, gmail_configurado
from finanzas.api import modelos as m
from finanzas.api.dependencias import conexion, usuario_actual
from finanzas.api.comun import _CSRF, _ERROR_404, _ERROR_409, _ERROR_415, _error
from finanzas.api.comun import crear_router



MENSAJE_SINCRONIZACION_EN_CURSO = "Ya hay una sincronización en curso."

MENSAJE_NO_RECONOCIDO_INEXISTENTE = "Ese correo no está en la lista de no reconocidos."

MENSAJES_ERROR_SINCRONIZACION = {
    "sin_fecha_inicio": (
        "Todavía no se ha configurado el saldo inicial ni la fecha de inicio. "
        "Configúralos antes de sincronizar."
    ),
    "gmail_no_configurado": "Gmail no está configurado en el servidor. Revisa la guía de instalación.",
    "autorizacion_gmail": (
        "Gmail rechazó el permiso de lectura (pudo vencer o ser revocado). "
        "Hay que volver a conectar Gmail en el servidor."
    ),
    "error_inesperado": (
        "No se pudo completar la sincronización con Gmail. Inténtalo más tarde; "
        "si se repite, revisa el registro del servidor."
    ),
}
router = crear_router()


def _resultado_sincronizacion(estado: sincronizacion.EstadoSincronizacion) -> m.ResultadoSincronizacion:
    if estado.resultado is None:
        contadores = None
        mensaje = MENSAJES_ERROR_SINCRONIZACION.get(
            estado.codigo_error or "", MENSAJES_ERROR_SINCRONIZACION["error_inesperado"]
        )
    else:
        contadores = m.Contadores(
            nuevos=estado.resultado.nuevos,
            duplicados=estado.resultado.duplicados,
            no_reconocidos=estado.resultado.no_reconocidos,
            errores=estado.resultado.errores,
            rechazados_autenticacion=estado.resultado.rechazados_autenticacion,
        )
        mensaje = f"Sincronización terminada: {estado.resultado.resumen()}."
    return m.ResultadoSincronizacion(
        terminada_en=estado.terminada_en,
        estado=estado.estado,
        origen=estado.origen,
        contadores=contadores,
        codigo_error=estado.codigo_error,
        mensaje=mensaje,
    )


@router.post(
    "/sincronizacion",
    response_model=m.ResultadoSincronizacion,
    dependencies=_CSRF,
    responses={**_ERROR_409, **_ERROR_415},
    summary="Sincronizar ahora",
)
def sincronizar_ahora(
    request: Request,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.ResultadoSincronizacion:
    """Trae los correos nuevos de Gmail. Responde 200 también si falló (``estado: fallida``).

    Usa el mismo candado que el botón de las plantillas: una sola a la vez desde la web.
    """
    candado: threading.Lock = request.app.state.candado_sincronizacion
    if not candado.acquire(blocking=False):
        raise _error(409, MENSAJE_SINCRONIZACION_EN_CURSO)
    try:
        config = request.app.state.config
        estado = componer_sincronizacion(conn).ejecutar_con_estado(request.app.state.fabrica_cliente_gmail, config.gmail_remitentes, origen='web')
    finally:
        candado.release()
    return _resultado_sincronizacion(estado)


@router.get("/sincronizacion", response_model=m.EstadoSincronizacion, summary="Última sincronización")
def ver_sincronizacion(
    request: Request,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.EstadoSincronizacion:
    """La última sincronización terminada (desde el botón o el temporizador), o ``null`` si nunca hubo.

    ``debe_sincronizar_al_abrir`` (ítem 38) sale de la misma lectura.
    """
    candado: threading.Lock = request.app.state.candado_sincronizacion
    en_curso = candado.locked()
    with lectura_consistente(conn):
        estado = componer_registro_sincronizacion(conn).leer_estado()
        fecha_configurada = componer_registro_sincronizacion(conn).fecha_configurada()
    return m.EstadoSincronizacion(
        en_curso=en_curso,
        ultima=None if estado is None else _resultado_sincronizacion(estado),
        ultima_correcta_en=None if estado is None else estado.ultima_correcta_en,
        debe_sincronizar_al_abrir=sincronizacion.debe_sincronizar_al_abrir(
            estado,
            gmail_configurado=gmail_configurado(request.app.state.config),
            fecha_configurada=fecha_configurada,
            en_curso=en_curso,
        ),
    )


@router.get("/no-reconocidos", response_model=m.ListaNoReconocidos, summary="Correos no reconocidos")
def ver_no_reconocidos(
    usuario: m.Usuario = Depends(usuario_actual), conn: Connection = Depends(conexion)
) -> m.ListaNoReconocidos:
    """Solo id de Gmail, fecha y asunto (nunca el cuerpo), del más reciente al más antiguo."""
    return m.ListaNoReconocidos(correos=[m.CorreoNoReconocido(**fila) for fila in componer_registro_sincronizacion(conn).listar_no_reconocidos()])


def _reprocesar(request: Request, conn: Connection, gmail_id: str | None) -> m.ResultadoReproceso:
    """Reprocesa con el mismo candado que "Sincronizar": nunca a la vez que una
    sincronización lanzada desde la web (409 si hay una en curso)."""
    candado: threading.Lock = request.app.state.candado_sincronizacion
    if not candado.acquire(blocking=False):
        raise _error(409, MENSAJE_SINCRONIZACION_EN_CURSO)
    try:
        if gmail_id is not None and not componer_registro_sincronizacion(conn).es_no_reconocido(gmail_id):
            raise _error(404, MENSAJE_NO_RECONOCIDO_INEXISTENTE)
        resultado, codigo_error = componer_sincronizacion(conn).ejecutar_reproceso(request.app.state.fabrica_cliente_gmail, request.app.state.config.gmail_remitentes, gmail_id)
    finally:
        candado.release()
    if resultado is None:
        return m.ResultadoReproceso(
            estado="fallida",
            contadores=None,
            codigo_error=codigo_error,
            mensaje=MENSAJES_ERROR_SINCRONIZACION.get(
                codigo_error or "", MENSAJES_ERROR_SINCRONIZACION["error_inesperado"]
            ),
        )
    return m.ResultadoReproceso(
        estado="con_errores" if resultado.errores else "ok",
        contadores=m.ContadoresReproceso(
            revisados=resultado.revisados,
            movimientos_creados=resultado.movimientos_creados,
            siguen_sin_reconocerse=resultado.siguen_sin_reconocerse,
            ya_registrados=resultado.ya_registrados,
            errores=resultado.errores,
        ),
        codigo_error=None,
        mensaje=f"Reproceso terminado: {resultado.resumen()}.",
    )


@router.post(
    "/no-reconocidos/reprocesar",
    response_model=m.ResultadoReproceso,
    dependencies=_CSRF,
    responses={**_ERROR_409, **_ERROR_415},
    summary="Reprocesar todos los no reconocidos",
)
def reprocesar_no_reconocidos(
    request: Request,
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.ResultadoReproceso:
    """Vuelve a descargar de Gmail cada correo de la lista y le aplica el mismo
    camino que la sincronización (remitente y DMARC, D15; aviso citado;
    extractor). Los que ahora son un aviso válido crean su movimiento (sin
    duplicar) y salen de la lista; los demás se quedan. Responde 200 también
    si falló (``estado: fallida``), como "Sincronizar"."""
    return _reprocesar(request, conn, None)


@router.post(
    "/no-reconocidos/{gmail_id}/reprocesar",
    response_model=m.ResultadoReproceso,
    dependencies=_CSRF,
    responses={**_ERROR_404, **_ERROR_409, **_ERROR_415},
    summary="Reprocesar un no reconocido",
)
def reprocesar_no_reconocido(
    request: Request,
    gmail_id: str = Path(min_length=1, max_length=m.MAXIMO_GMAIL_ID),
    usuario: m.Usuario = Depends(usuario_actual),
    conn: Connection = Depends(conexion),
) -> m.ResultadoReproceso:
    """Como el anterior, solo para un correo de la lista (404 si no está en ella)."""
    return _reprocesar(request, conn, gmail_id)
