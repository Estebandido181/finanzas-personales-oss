"""Arranque e historial31: subir, calcular y aprobar antes de guardar."""
from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Path
from sqlalchemy import Connection
from starlette.concurrency import run_in_threadpool

from finanzas.infraestructura import persistencia as db
from finanzas.compartido import hora
from finanzas.flujos import historial as arranque
from finanzas.modulos.importaciones import publico as gestion
from finanzas.modulos.sincronizacion import publico as sincronizacion
from finanzas.bootstrap.arranque import componer_arranque, snapshot_preparacion, preparar_avisos
from finanzas.bootstrap.importaciones import componer_gestion_importaciones
from finanzas.bootstrap.sincronizacion import componer_registro_sincronizacion
from finanzas.api import modelos as m
from finanzas.api.dependencias import conexion, exigir_csrf, usuario_actual, token_csrf
from finanzas.api.rutas_importacion import _accion, MIME_XLSX, SEGUNDOS_ANALISIS
from finanzas.api.rutas_sincronizacion import _resultado_sincronizacion
from finanzas.modulos.importaciones.adaptadores.archivos.excel_bancolombia import leer_excel_movimientos, TAMANO_MAXIMO_BYTES
from finanzas.modulos.sincronizacion.publico import ErrorAutorizacionGmail
from finanzas.infraestructura.tokens_bancarios_ram import HistorialVencido

RUTA_ARCHIVOS = "/api/arranque/archivos"
router = APIRouter(prefix="/api/arranque", tags=["Arranque e historial"],
    dependencies=[Depends(usuario_actual)], responses={
        400: {"model": m.Error}, 401: {"model": m.Error}, 403: {"model": m.Error},
        409: {"model": m.Error}, 410: {"model": m.Error}, 413: {"model": m.Error},
        415: {"model": m.Error}, 422: {"model": m.ErrorValidacion}, 503: {"model": m.Error}},
    generate_unique_id_function=lambda ruta: ruta.name)
CSRF = [Depends(exigir_csrf)]
Id = Annotated[int, Path(ge=1, le=m.MAXIMO_ID)]


def _historial(accion, *args):
    try:
        return accion(*args)
    except HistorialVencido:
        raise HTTPException(410, "El historial cambió, venció o ya se usó. Vuelve a agregar tus archivos.") from None


def _vista_archivos(archivos, token):
    return {"token": token, "segundos": SEGUNDOS_ANALISIS,
        "limite_archivos": arranque.MAXIMO_ARCHIVOS, "limite_filas": arranque.MAXIMO_FILAS_HISTORIAL,
        "puede_calcular": any(archivos), "archivos": [{"id": i + 1, "estado": "leido", "filas": len(filas),
            "desde": min(f.fecha for f in filas).isoformat() if filas else None,
            "hasta": max(f.fecha for f in filas).isoformat() if filas else None, "truncado": False}
            for i, filas in enumerate(archivos)]}


@router.post("/archivos", response_model=m.ArchivosHistorial, dependencies=CSRF,
    openapi_extra={"requestBody": {"required": True, "content": {MIME_XLSX: {"schema": {"type": "string", "format": "binary"}}}}})
async def agregar_archivo_historial(request: Request,
    x_historial_token: str | None = Header(default=None, max_length=100),
    x_nombre_archivo: str = Header(default="movimientos.xlsx", max_length=200)):
    declarado = request.headers.get("content-length")
    if declarado:
        try:
            cantidad = int(declarado)
        except ValueError:
            raise HTTPException(400, "El tamaño declarado del archivo no es válido.") from None
        if not 0 <= cantidad <= TAMANO_MAXIMO_BYTES:
            raise HTTPException(413, "El archivo supera el tamaño permitido (2 MB).")
    if not x_nombre_archivo.lower().endswith(".xlsx"):
        raise HTTPException(415, "Elige un archivo .xlsx descargado del banco.")
    registro, propietario = request.app.state.historial_arranque, token_csrf(request)
    if x_historial_token:
        previo, generacion = _historial(registro.leer_archivos, x_historial_token, propietario)
    else:
        previo, generacion = (), _historial(registro.iniciar_subida, propietario)
    if len(previo) >= arranque.MAXIMO_ARCHIVOS:
        raise HTTPException(400, "Ya agregaste el máximo de archivos permitido. Descarta el historial para elegir otro periodo.")
    contenido = bytearray()
    async for parte in request.stream():
        if len(contenido) + len(parte) > TAMANO_MAXIMO_BYTES:
            raise HTTPException(413, "El archivo supera el tamaño permitido (2 MB).")
        contenido.extend(parte)
    filas = await run_in_threadpool(_accion, leer_excel_movimientos, bytes(contenido), x_nombre_archivo)
    del contenido
    archivos = (*previo, tuple(filas))
    try:
        arranque.unir_archivos(archivos)
    except arranque.ErrorArranque as error:
        raise HTTPException(400, str(error)) from None
    token = await run_in_threadpool(_historial, registro.agregar,
        x_historial_token, generacion, archivos, propietario)
    return _vista_archivos(archivos, token)


@router.get("/archivos/{token}", response_model=m.ArchivosHistorial)
def ver_archivos_historial(request: Request, token: Annotated[str, Path(min_length=1, max_length=100)]):
    archivos, _ = _historial(request.app.state.historial_arranque.leer_archivos, token, token_csrf(request))
    return _vista_archivos(archivos, token)


@router.delete("/archivos", response_model=dict[str, bool], dependencies=CSRF)
def descartar_archivos_historial(datos: m.ConfirmarImportacionEntrada, request: Request):
    _historial(request.app.state.historial_arranque.descartar_archivos, datos.token, token_csrf(request))
    return {"descartado": True}


@router.delete("/archivos/{archivo_id}", response_model=m.ArchivosHistorial, dependencies=CSRF)
def quitar_archivo_historial(archivo_id: Id, datos: m.ConfirmarImportacionEntrada, request: Request):
    def quitar(archivos):
        if archivo_id > len(archivos):
            raise HTTPException(404, "Ese archivo ya no está en el historial.")
        return archivos[:archivo_id - 1] + archivos[archivo_id:]
    token, restantes = _historial(request.app.state.historial_arranque.modificar,
        datos.token, token_csrf(request), quitar)
    return _vista_archivos(restantes, token)


@router.delete("/analisis", response_model=dict[str, bool], dependencies=CSRF)
def descartar_calculo_arranque(datos: m.ConfirmarImportacionEntrada, request: Request):
    _historial(request.app.state.historial_arranque.descartar_analisis, datos.token, token_csrf(request))
    return {"descartado": True}


@router.post("/calcular", response_model=m.VistaPreviaArranque, dependencies=CSRF)
def calcular_arranque(datos: m.CalcularArranqueEntrada, request: Request, conn: Connection = Depends(conexion)):
    recibido_en = hora.ahora_colombia().isoformat(timespec="seconds")
    registro, propietario = request.app.state.historial_arranque, token_csrf(request)
    archivos, generacion = _historial(registro.leer_archivos, datos.token, propietario)
    try:
        historial = arranque.unir_archivos(archivos)
        if historial.desde is None:
            raise arranque.ErrorArranque("Los archivos no tienen movimientos. Agrega un reporte con historial.")
        # Snapshot breve y cerrado antes de las llamadas a Gmail.
        huella, registrados = snapshot_preparacion(conn)
        candado = request.app.state.candado_sincronizacion
        if not candado.acquire(blocking=False):
            raise HTTPException(409, "Hay una sincronización en curso. Espera a que termine y vuelve a calcular.")
        try:
            avisos = preparar_avisos(request.app.state.fabrica_cliente_gmail(), historial.desde,
                registrados, request.app.state.config.gmail_remitentes)
        finally:
            candado.release()
        analisis = componer_arranque(conn).analizar(archivos, datos.saldo_actual_centavos, modo=datos.modo, avisos=avisos, huella_esperada=huella, saldo_real_centavos=datos.saldo_real_centavos, recibido_en=recibido_en)
    except arranque.ErrorArranque as error:
        raise HTTPException(400, str(error)) from None
    except (ErrorAutorizacionGmail, sincronizacion.SincronizacionNoConfigurada):
        raise HTTPException(503, "No se pudo acceder a Gmail. Revisa su autorización antes de calcular el historial.") from None
    except gestion.ConflictoImportacion as error:
        raise HTTPException(409, str(error)) from None
    except HTTPException:
        raise
    except Exception:
        # Nunca propagar el cuerpo, asunto ni parámetros de un error externo.
        raise HTTPException(503, "No se pudo leer el historial de Gmail. No se guardó ningún cambio; vuelve a intentar.") from None
    token = _historial(registro.publicar, datos.token, generacion, analisis, propietario)
    return {"token": token, "segundos": SEGUNDOS_ANALISIS, **analisis.vista}


@router.post("/confirmar", response_model=m.ResultadoArranque, dependencies=CSRF)
def confirmar_arranque(datos: m.ConfirmarImportacionEntrada, request: Request, conn: Connection = Depends(conexion)):
    resultado = _historial(request.app.state.historial_arranque.confirmar, datos.token, token_csrf(request), lambda analisis: _accion(componer_arranque(conn).confirmar, analisis))
    return _con_estado(conn, resultado)


def _con_estado(conn, resultado):
    estado = componer_registro_sincronizacion(conn).leer_estado()
    return {**resultado, "sincronizacion": _resultado_sincronizacion(estado) if estado else None}


@router.get("/estado", response_model=m.EstadoArranque)
def ver_estado_arranque(conn: Connection = Depends(conexion)):
    with db.lectura_consistente(conn):
        return componer_arranque(conn).estado_arranque()


@router.get("/{importacion_id}", response_model=m.ResultadoArranque)
def ver_arranque(importacion_id: Id, conn: Connection = Depends(conexion)):
    return _con_estado(conn, _accion(componer_arranque(conn).resultado_arranque, importacion_id))


@router.post("/{importacion_id}/deshacer", response_model=m.ResultadoArranque, dependencies=CSRF)
def deshacer_arranque(importacion_id: Id, conn: Connection = Depends(conexion)):
    _accion(componer_arranque(conn).resultado_arranque, importacion_id)
    _accion(componer_gestion_importaciones(conn).deshacer_importacion, importacion_id)
    return _con_estado(conn, componer_arranque(conn).resultado_arranque(importacion_id))
