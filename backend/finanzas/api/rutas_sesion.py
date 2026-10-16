"""Adaptación HTTP: sesion."""
from __future__ import annotations
from fastapi import Depends, Request, Response
from finanzas.api import modelos as m
from finanzas.api.dependencias import DUENO, token_csrf, usuario_actual
from finanzas.bootstrap.sesion import componer_acceso
from finanzas.modulos.sesion.publico import AccesoBloqueado, ContrasenaIncorrecta
from finanzas.api.comun import _CSRF, _ERROR_415, _error, logger
from finanzas.api.comun import crear_router



MENSAJE_LOGIN_FALLIDO = "Contraseña incorrecta."

MENSAJE_BLOQUEO = "Demasiados intentos fallidos. Espera unos minutos y vuelve a intentarlo."
router = crear_router()


def _revocar_bancarios(request):
    propietario = request.session.get("csrf_token")
    if isinstance(propietario, str):
        request.app.state.analisis_importaciones.revocar(propietario)
        request.app.state.historial_arranque.revocar(propietario)
        request.app.state.deshacer_conciliacion.revocar(propietario)


def _ip_cliente(request: Request) -> str:
    # Detrás de Caddy, uvicorn con --proxy-headers pone aquí la IP real (ítem 07).
    return request.client.host if request.client else "desconocida"


@router.post(
    "/sesion",
    response_model=m.Sesion,
    responses={401: {"model": m.Error, "description": "Contraseña incorrecta."},
               429: {"model": m.Error, "description": "Demasiados intentos."}, **_ERROR_415},
    summary="Iniciar sesión",
)
async def iniciar_sesion(datos: m.LoginEntrada, request: Request) -> m.Sesion:
    """Mismo límite de intentos que ``POST /login`` (comparten el limitador por IP).

    No pide token CSRF (aún no hay sesión): lo protegen la comprobación de
    ``Origin``/``Sec-Fetch-Site`` y el cuerpo JSON obligatorio, que un
    formulario de otro sitio no puede enviar.
    """
    acceso = componer_acceso(request.session, request.app.state.limitador,
                            lambda: _revocar_bancarios(request))
    # Sin await: mantiene atómica la secuencia de comprobar/registrar intento
    # en el event loop del proceso único, como antes de la extracción.
    try:
        acceso.iniciar(datos.contrasena, request.app.state.config.app_password_hash,
                       _ip_cliente(request))
    except AccesoBloqueado:
        logger.warning("Intento de login rechazado: origen bloqueado temporalmente")
        raise _error(429, MENSAJE_BLOQUEO) from None
    except ContrasenaIncorrecta:
        logger.warning("Login fallido")  # sin contraseña ni otros datos
        raise _error(401, MENSAJE_LOGIN_FALLIDO) from None
    return m.Sesion(usuario=DUENO, csrf_token=token_csrf(request))


@router.get("/sesion", response_model=m.Sesion, summary="Estado de la sesión")
def ver_sesion(request: Request, usuario: m.Usuario = Depends(usuario_actual)) -> m.Sesion:
    """El usuario y el token CSRF de la sesión. 401 si no hay sesión."""
    return m.Sesion(usuario=usuario, csrf_token=token_csrf(request))


@router.delete("/sesion", status_code=204, dependencies=_CSRF, summary="Cerrar sesión")
def cerrar_sesion(request: Request, usuario: m.Usuario = Depends(usuario_actual)) -> Response:
    componer_acceso(request.session, request.app.state.limitador,
                   lambda: _revocar_bancarios(request)).cerrar()
    return Response(status_code=204)
