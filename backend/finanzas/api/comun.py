"""Adaptación HTTP: comun."""
from __future__ import annotations
import logging
from fastapi import Depends, HTTPException, Path, Query
from fastapi.routing import APIRoute
from dataclasses import asdict
from finanzas.api import modelos as m
from finanzas.api.dependencias import exigir_csrf
from fastapi import APIRouter


logger = logging.getLogger("finanzas.api.rutas")


PREFIJO = "/api"


RUTA_SESION = PREFIJO + "/sesion"


















_ERRORES = {
    401: {"model": m.Error, "description": "Sin sesión."},
    403: {"model": m.Error, "description": "Origen ajeno o token CSRF ausente o inválido."},
    422: {"model": m.ErrorValidacion, "description": "La forma de la petición no es válida."},
}


_ERROR_400 = {400: {"model": m.Error, "description": "Dato no válido o acción no permitida."}}


_ERROR_404 = {404: {"model": m.Error, "description": "No existe."}}


_ERROR_409 = {409: {"model": m.Error, "description": "Conflicto."}}


_ERROR_415 = {415: {"model": m.Error, "description": "El cuerpo debe ser application/json."}}




def _id_operacion(ruta: APIRoute) -> str:
    # Nombres estables y legibles en los tipos generados (p. ej. "ver_reporte").
    return ruta.name


_CSRF = [Depends(exigir_csrf)]


IdMovimiento = Path(ge=1, le=m.MAXIMO_ID)


IdRegla = Path(ge=1, le=m.MAXIMO_ID)


IdCategoria = Path(ge=1, le=m.MAXIMO_ID)


def _error(estado: int, detalle: str) -> HTTPException:
    return HTTPException(status_code=estado, detail=detalle)


ParametroMes = Query(None, description="aaaa-mm; sin él, el mes actual en Colombia.", max_length=7)


def _datos_opcionales(fila):
    return None if fila is None else asdict(fila)


def crear_router() -> APIRouter:
    return APIRouter(prefix=PREFIJO, responses=_ERRORES, generate_unique_id_function=_id_operacion)
