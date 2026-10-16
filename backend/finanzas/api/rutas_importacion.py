"""API bancaria: bytes acotados en memoria y decisiones calculadas en servidor."""
from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Path
from sqlalchemy import Connection
from starlette.concurrency import run_in_threadpool

from finanzas.modulos.importaciones import publico as gestion, publico as importacion
from finanzas.modulos.saldo import publico as saldo
from finanzas.api import deshacer
from finanzas.bootstrap.importaciones import componer_gestion_importaciones, componer_diferencias
from finanzas.api import modelos as m
from finanzas.api.dependencias import conexion, exigir_csrf, usuario_actual, token_csrf
from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import leer_excel_movimientos, ExcelNoReconocido, TAMANO_MAXIMO_BYTES
from finanzas.infraestructura.tokens_bancarios_ram import HistorialVencido

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
RUTA_ANALIZAR = "/api/importaciones/analizar"
SEGUNDOS_ANALISIS = 15 * 60
router = APIRouter(prefix="/api", tags=["Importación bancaria"],
    dependencies=[Depends(usuario_actual)],
    responses={401: {"model": m.Error}, 403: {"model": m.Error}, 400: {"model": m.Error},
               409: {"model": m.Error}, 410: {"model": m.Error}, 413: {"model": m.Error}, 415: {"model": m.Error},
               422: {"model": m.ErrorValidacion}},
    generate_unique_id_function=lambda ruta: ruta.name)
CSRF = [Depends(exigir_csrf)]
Id = Annotated[int, Path(ge=1, le=m.MAXIMO_ID)]


def _accion(funcion, *args):
    try:
        return funcion(*args)
    except gestion.ConflictoImportacion as error:
        raise HTTPException(409, str(error)) from None
    except gestion.ImportacionInexistente as error:
        raise HTTPException(404, str(error)) from None
    except (importacion.ErrorConciliacion, ExcelNoReconocido, saldo.ErrorSaldo) as error:
        raise HTTPException(400, str(error)) from None


@router.post("/importaciones/analizar", response_model=m.VistaPreviaImportacion, dependencies=CSRF,
    openapi_extra={"requestBody": {"required": True, "content": {MIME_XLSX: {"schema": {"type": "string", "format": "binary"}}}}})
async def analizar_importacion(request: Request,
    x_nombre_archivo: str = Header(default="movimientos.xlsx", alias="X-Nombre-Archivo", max_length=200),
    conn: Connection = Depends(conexion)):
    declarado = request.headers.get("content-length")
    if declarado:
        try:
            if int(declarado) < 0 or int(declarado) > TAMANO_MAXIMO_BYTES:
                raise HTTPException(413, "El archivo supera el tamaño permitido (2 MB).")
        except ValueError:
            raise HTTPException(400, "El tamaño declarado del archivo no es válido.") from None
    if not x_nombre_archivo.lower().endswith(".xlsx"):
        raise HTTPException(415, "Elige un archivo .xlsx descargado del banco.")
    contenido = bytearray()
    async for parte in request.stream():
        if len(contenido) + len(parte) > TAMANO_MAXIMO_BYTES:
            raise HTTPException(413, "El archivo supera el tamaño permitido (2 MB).")
        contenido.extend(parte)
    filas = await run_in_threadpool(_accion, leer_excel_movimientos, bytes(contenido), x_nombre_archivo)
    del contenido
    analisis = await run_in_threadpool(_accion, componer_gestion_importaciones(conn).analizar, filas)
    token = request.app.state.analisis_importaciones.guardar(analisis, token_csrf(request))
    return {"token": token, "segundos": SEGUNDOS_ANALISIS, **analisis.vista}


@router.post("/saldo/comprobar", response_model=m.ComprobacionSaldo, dependencies=CSRF)
def comprobar_saldo(datos: m.ComprobarSaldoEntrada, request: Request, conn: Connection = Depends(conexion)):
    if datos.tipo_analisis == "arranque":
        try:
            return request.app.state.historial_arranque.consultar(datos.token_analisis, token_csrf(request), lambda analisis: _accion(componer_gestion_importaciones(conn).comprobar_saldo, datos.saldo_real_centavos, analisis))
        except HistorialVencido:
            raise HTTPException(410, "El historial cambió, venció o ya se usó. Vuelve a agregar tus archivos.") from None
    analisis = None
    if datos.tipo_analisis == "importacion":
        pendiente = request.app.state.analisis_importaciones.ver(datos.token_analisis, token_csrf(request))
        if pendiente is None:
            raise HTTPException(410, "El análisis venció o ya se usó. Vuelve a analizar el archivo.")
        analisis = pendiente.copia
    return _accion(componer_gestion_importaciones(conn).comprobar_saldo, datos.saldo_real_centavos, analisis)


@router.delete("/importaciones/analisis", response_model=dict[str, bool], dependencies=CSRF)
def descartar_analisis(datos: m.ConfirmarImportacionEntrada, request: Request):
    request.app.state.analisis_importaciones.tomar(datos.token, token_csrf(request))
    return {"descartado": True}


@router.post("/importaciones", response_model=m.DetalleImportacion, dependencies=CSRF)
def confirmar_importacion(datos: m.ConfirmarImportacionEntrada, request: Request, conn: Connection = Depends(conexion)):
    pendiente = request.app.state.analisis_importaciones.tomar(datos.token, token_csrf(request))
    if pendiente is None:
        raise HTTPException(410, "El análisis venció o ya se usó. Vuelve a analizar el archivo.")
    return _accion(componer_gestion_importaciones(conn).confirmar, pendiente.copia)


@router.get("/importaciones/estado", response_model=m.EstadoImportaciones)
def estado_importaciones(conn: Connection = Depends(conexion)):
    return componer_gestion_importaciones(conn).estado()


@router.get("/importaciones/ultima", response_model=m.UltimaImportacion)
def ultima_importacion(conn: Connection = Depends(conexion)):
    return componer_gestion_importaciones(conn).ultima()


@router.get("/importaciones/{importacion_id}", response_model=m.DetalleImportacion)
def detalle_importacion(importacion_id: Id, conn: Connection = Depends(conexion)):
    return _accion(componer_gestion_importaciones(conn).detalle, importacion_id)


@router.post("/importaciones/{importacion_id}/deshacer", response_model=m.DetalleImportacion, dependencies=CSRF)
def deshacer_importacion(importacion_id: Id, conn: Connection = Depends(conexion)):
    return _accion(componer_gestion_importaciones(conn).deshacer_importacion, importacion_id)


@router.get("/conciliacion/preguntas", response_model=m.ListaPreguntasConciliacion)
def preguntas_conciliacion(conn: Connection = Depends(conexion)):
    return componer_diferencias(conn).preguntas()


def _decision(request, conn, funcion, *args):
    resultado, copia = _accion(funcion, *args)
    token = request.app.state.deshacer_conciliacion.guardar(copia, token_csrf(request))
    return {**resultado, "deshacer": {"token": token, "segundos": deshacer.SEGUNDOS_DESHACER}}


@router.post("/conciliacion/preguntas/respuestas", response_model=m.ResultadoDecisionConciliacion, dependencies=CSRF)
def responder_preguntas(datos: m.RespuestasConciliacionEntrada, request: Request, conn: Connection = Depends(conexion)):
    return _decision(request, conn, componer_gestion_importaciones(conn).responder, [(d.pregunta_id, d.opcion) for d in datos.respuestas])


@router.post("/conciliacion/preguntas/aceptar-sugerencias", response_model=m.ResultadoDecisionConciliacion, dependencies=CSRF)
def aceptar_sugerencias(request: Request, conn: Connection = Depends(conexion)):
    return _decision(request, conn, componer_gestion_importaciones(conn).aceptar_sugerencias)


@router.post("/conciliacion/preguntas/{pregunta_id}/respuesta", response_model=m.ResultadoDecisionConciliacion, dependencies=CSRF)
def responder_pregunta(pregunta_id: Id, datos: m.RespuestaConciliacionEntrada, request: Request, conn: Connection = Depends(conexion)):
    return _decision(request, conn, componer_gestion_importaciones(conn).responder, [(pregunta_id, datos.opcion)])


@router.get("/conciliacion/no-esta-en-el-banco", response_model=m.ListaNoEnBanco)
def no_esta_en_banco(conn: Connection = Depends(conexion)):
    return componer_diferencias(conn).no_en_banco()


@router.post("/conciliacion/no-esta-en-el-banco/{movimiento_id}/respuesta", response_model=m.ResultadoDecisionConciliacion, dependencies=CSRF)
def decidir_no_en_banco(movimiento_id: Id, datos: m.RespuestaNoEnBancoEntrada, request: Request, conn: Connection = Depends(conexion)):
    return _decision(request, conn, componer_gestion_importaciones(conn).decidir_no_en_banco, movimiento_id, datos.opcion)


@router.post("/conciliacion/deshacer", response_model=m.DecisionDeshecha, dependencies=CSRF)
def deshacer_decision(datos: m.DeshacerEntrada, request: Request, conn: Connection = Depends(conexion)):
    pendiente = request.app.state.deshacer_conciliacion.tomar(datos.token, token_csrf(request))
    if pendiente is None:
        raise HTTPException(410, "Ya no se puede deshacer: pasó el tiempo o ya se deshizo.")
    return _accion(componer_gestion_importaciones(conn).deshacer_decision, pendiente.copia)
