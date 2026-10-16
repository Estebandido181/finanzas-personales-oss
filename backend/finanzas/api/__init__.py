"""API JSON (ítem 10, D16 y D20): la lógica de negocio expuesta al frontend.

Vive en la misma app que sirve el frontend (``finanzas.web.app.crear_app``
llama a ``instalar``). El login es ``POST /api/sesion`` y la sesión va en
una cookie del mismo dominio.

Seguridad (ver el docstring de ``finanzas.web.app``):

* sin sesión, todo ``/api`` responde 401 en JSON (nunca redirige), salvo
  ``POST /api/sesion`` (el login);
* lo que cambia datos exige el encabezado ``X-CSRF-Token`` con el token de la
  sesión, cuerpo ``application/json`` y un ``Origin``/``Sec-Fetch-Site`` del
  mismo sitio. Sin CORS: la API no se abre a otros dominios.

Errores: siempre ``{"detalle": "..."}``; los 422 añaden ``campos`` (dónde y
qué tipo de error, sin repetir nunca los valores enviados, que podrían ser
la contraseña o montos).

La descripción OpenAPI no se publica en la app (``/openapi.json`` da 404):
se exporta con ``python -m finanzas.api.exportar_openapi`` (ver el README).
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from finanzas.api.comun import PREFIJO
from finanzas.api.rutas_sesion import router as router_sesion
from finanzas.api.rutas_inicio import router as router_inicio
from finanzas.api.rutas_movimientos import router as router_movimientos
from finanzas.api.rutas_categorias import router as router_categorias
from finanzas.api.rutas_saldo import router as router_saldo
from finanzas.api.rutas_deshacer import router as router_deshacer
from finanzas.api.rutas_sincronizacion import router as router_sincronizacion
from finanzas.api.rutas_importacion import router as router_importacion
from finanzas.api.rutas_arranque import router as router_arranque
ROUTERS = (router_sesion, router_inicio, router_movimientos, router_categorias,
           router_saldo, router_deshacer, router_sincronizacion,
           router_importacion, router_arranque)

TITULO = "Finanzas personales"
VERSION = "1"
MENSAJE_VALIDACION = "Revisa los datos enviados."
MENSAJE_CUERPO_ILEGIBLE = "El cuerpo de la petición no es un JSON válido."
# FastAPI lanza este 400 (en inglés) cuando no puede leer el cuerpo: JSON
# demasiado anidado, un entero de miles de cifras, etc.
_DETALLE_CUERPO_FASTAPI = "There was an error parsing the body"
# Límites numéricos del esquema JSON: FastAPI los guarda como float
# (``1000000000000.0``); se devuelven a entero si lo son.
_LIMITES = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum")
MENSAJES_HTTP = {
    404: "No encontrado.",
    405: "Método no permitido.",
}


def _frase(estado: int) -> str:
    try:
        return HTTPStatus(estado).phrase
    except ValueError:
        return ""


def es_ruta_api(ruta: str) -> bool:
    return ruta == PREFIJO or ruta.startswith(PREFIJO + "/")


def error_json(estado: int, detalle: str, encabezados: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"detalle": detalle}, status_code=estado, headers=encabezados)


async def _error_http(request: Request, error: StarletteHTTPException):
    if not es_ruta_api(request.url.path):
        return await http_exception_handler(request, error)
    detalle = error.detail if isinstance(error.detail, str) else ""
    if error.status_code == 400 and detalle == _DETALLE_CUERPO_FASTAPI:
        return error_json(400, MENSAJE_CUERPO_ILEGIBLE)  # nunca repite el cuerpo
    # Los errores propios traen un texto en español; los de Starlette (ruta
    # inexistente, método no permitido) traen la frase en inglés del estado.
    if not detalle or detalle == _frase(error.status_code):
        detalle = MENSAJES_HTTP.get(error.status_code, "Error.")
    return error_json(error.status_code, detalle, getattr(error, "headers", None))


async def _error_validacion(request: Request, error: RequestValidationError):
    if not es_ruta_api(request.url.path):
        return await request_validation_exception_handler(request, error)
    campos: list[dict[str, Any]] = [
        {
            "ubicacion": [str(p) if not isinstance(p, int) else p for p in e.get("loc", ())],
            "tipo": str(e.get("type", "")),
            "mensaje": str(e.get("msg", "")),
        }
        for e in error.errors()
    ]
    # Nunca e["input"]: podría ser la contraseña o un monto.
    return JSONResponse({"detalle": MENSAJE_VALIDACION, "campos": campos}, status_code=422)


def instalar(app: FastAPI) -> None:
    """Añade las rutas de la API y los manejadores de error en JSON (solo para ``/api``)."""
    for router in ROUTERS:
        app.include_router(router)
    app.add_exception_handler(StarletteHTTPException, _error_http)
    app.add_exception_handler(RequestValidationError, _error_validacion)


def esquema_openapi() -> dict[str, Any]:
    """La descripción OpenAPI de la API, sin configuración ni base de datos."""
    app = FastAPI(
        title=TITULO,
        version=VERSION,
        description="API JSON de la app de finanzas personales. Montos en centavos enteros.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    for router in ROUTERS:
        app.include_router(router)
    return _limites_enteros(app.openapi())


def _limites_enteros(nodo: Any) -> Any:
    """``maximum: 1000000000000.0`` -> ``1000000000000`` (montos e ids son enteros)."""
    if isinstance(nodo, dict):
        return {
            clave: (
                int(valor)
                if clave in _LIMITES and isinstance(valor, float) and valor.is_integer()
                else _limites_enteros(valor)
            )
            for clave, valor in nodo.items()
        }
    if isinstance(nodo, list):
        return [_limites_enteros(valor) for valor in nodo]
    return nodo
