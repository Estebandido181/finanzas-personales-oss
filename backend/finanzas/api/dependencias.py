"""Dependencias de la API: usuario actual, CSRF y conexión a la base.

Defensa en profundidad: los middlewares de ``finanzas.web.app`` ya rechazan
lo que llega sin sesión (401) o sin token CSRF (403) a ``/api``; estas
dependencias lo comprueban otra vez en cada ruta y además lo declaran en la
descripción OpenAPI (el encabezado ``X-CSRF-Token`` aparece en los tipos del
frontend).
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Header, HTTPException, Request
from sqlalchemy import Connection

from finanzas.infraestructura import persistencia as db
from finanzas.api.modelos import Usuario
from finanzas.bootstrap.sesion import componer_sesion
from finanzas.modulos.sesion.publico import (
    CLAVE_AUTENTICADO, CLAVE_CSRF, LARGO_TOKEN_CSRF, SesionRequerida,
    DUENO as IDENTIDAD_DUENO,
)

ENCABEZADO_CSRF = "X-CSRF-Token"

MENSAJE_SIN_SESION = "Inicia sesión para continuar."
MENSAJE_CSRF = "Petición rechazada: falta el token de la sesión o no es válido. Recarga la app."

# D20: hoy la app tiene un solo usuario. Cuando haya varios (v3 o v4), la
# sesión guardará su id y esta es la única función que cambia.
DUENO = Usuario(id=IDENTIDAD_DUENO.id, nombre=IDENTIDAD_DUENO.nombre)


def hay_sesion(request: Request) -> bool:
    return componer_sesion(request.session).esta_iniciada()


def usuario_actual(request: Request) -> Usuario:
    """El usuario de la sesión, o 401 (en JSON, nunca una redirección)."""
    try:
        componer_sesion(request.session).usuario()
    except SesionRequerida:
        raise HTTPException(status_code=401, detail=MENSAJE_SIN_SESION)
    return DUENO


def token_csrf(request: Request) -> str:
    """El token CSRF de la sesión; lo crea si no hay (p. ej. una sesión anterior al ítem 10)."""
    return componer_sesion(request.session).token_csrf()


def csrf_valido(request: Request, recibido: str | None) -> bool:
    """``True`` si ``recibido`` es el token de esta sesión (comparación en tiempo constante)."""
    return componer_sesion(request.session).csrf_valido(recibido)


def exigir_csrf(
    request: Request,
    x_csrf_token: str = Header(alias=ENCABEZADO_CSRF, description="El csrf_token de GET /api/sesion."),
) -> None:
    if not csrf_valido(request, x_csrf_token):
        raise HTTPException(status_code=403, detail=MENSAJE_CSRF)


def conexion(request: Request) -> Iterator[Connection]:
    """Una conexión por petición; se cierra al terminar."""
    conn = db.conectar(request.app.state.config.db_path)
    try:
        yield conn
    finally:
        conn.close()
