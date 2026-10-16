"""Aplicación web: sesión, protección global de rutas y el frontend en ``/app``.

Arranque en local (ver README)::

    python -m finanzas.migrar --respaldos ./respaldos   # crea o pone al día la base
    uvicorn --factory finanzas.web.app:crear_app --host 127.0.0.1 --port 8000

Se usa una fábrica (``crear_app``) para que importar este módulo no exija
las variables de entorno: las pruebas crean la app con su propia ``Config``.
``finanzas.web.app:app`` también funciona: se crea de forma perezosa al
pedirlo por primera vez.

Desde el ítem 20 la única interfaz es el frontend de ``/app`` (ver
``finanzas.web.frontend``), que habla solo con la API JSON (``/api``,
``finanzas.api``). La interfaz de plantillas de la v1 se retiró; sus
direcciones de lectura redirigen (307, nunca 301) a la pantalla
equivalente de ``/app``. La app no se mueve a la raíz para no romper la PWA
instalada (manifest, ``scope``, ``id`` y service worker viven en ``/app/``).

Protección: el middleware ``_exigir_sesion`` responde 401 en JSON a todo
``/api`` sin sesión (nunca redirige); solo el login (``POST /api/sesion``)
se admite sin sesión. Fuera de ``/api`` no hay datos: ``/app`` es el
cascarón y las redirecciones no leen la base, y cualquier otra ruta da 404.
Es global, así que una ruta nueva de la API queda protegida sin hacer nada.

CSRF: la cookie de sesión es ``SameSite=Lax``, así que otro sitio no puede
enviar un POST con la sesión del dueño. Como defensa adicional,
``_verificar_origen`` rechaza con 403 todo POST, PUT, PATCH o DELETE cuyo
encabezado ``Origin`` no coincida con el host de la petición (si no viene
``Origin``, se acepta). En la API se exige además, en lo que cambia datos:

* ``Sec-Fetch-Site`` ``same-origin`` o ``none`` si el navegador lo envía;
* cuerpo ``application/json`` (415 si no): un formulario de otro sitio no
  puede enviarlo, y un ``fetch`` de otro origen con ese tipo necesita
  permiso CORS, que la app no da (no hay ``CORSMiddleware``);
* el encabezado ``X-CSRF-Token`` igual al token de la sesión
  (``_proteger_api``; se obtiene con ``GET /api/sesion``), salvo en el login,
  que aún no tiene sesión. Otro sitio no puede leer el token ni poner ese
  encabezado sin permiso CORS.

Content-Security-Policy: solo se ejecutan scripts y estilos servidos por la
propia app (``'self'``), sin nada en línea ni ``eval``. El frontend compilado
no lleva scripts ni estilos en línea (lo comprueban las pruebas y los e2e).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from starlette.middleware.sessions import SessionMiddleware

from finanzas.infraestructura import persistencia as db
from finanzas import api
from finanzas.flujos import reporte
from finanzas.bootstrap.sincronizacion import cliente_desde_config
from finanzas.api import dependencias as dependencias_api
from finanzas.api.comun import RUTA_SESION as RUTA_SESION_API
from finanzas.api.rutas_importacion import RUTA_ANALIZAR, MIME_XLSX, SEGUNDOS_ANALISIS
from finanzas.api.rutas_arranque import RUTA_ARCHIVOS
from finanzas.compartido.config import Config
from finanzas.modulos.sincronizacion.publico import ClienteGmail
from finanzas.modulos.sesion.publico import LimitadorIntentos
from finanzas.infraestructura.deshacer_ram import RegistroDeshacer
from finanzas.infraestructura.tokens_bancarios_ram import RegistroBancario, RegistroHistorial
from finanzas.infraestructura.tokens_ingreso_ram import TokensIngreso
from finanzas.web import frontend
from finanzas.bootstrap.categorias import componer_consulta_categorias

logger = logging.getLogger(__name__)

DURACION_SESION = 7 * 24 * 60 * 60  # 7 días, en segundos
# Lo único que se puede guardar en caché: los archivos con hash del frontend
# (ver finanzas.web.frontend). Todo lo demás, no-store.
PREFIJOS_CACHEABLES = (frontend.PREFIJO_ASSETS,)
ENCABEZADOS_SEGURIDAD = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    # Nada en línea ni eval: scripts, estilos y fuentes solo de la propia app.
    # ``img-src data:`` es para las imágenes que el navegador genera en memoria.
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
}
MENSAJE_ORIGEN_AJENO = "Petición rechazada: no viene de esta página."
PUERTOS_POR_DEFECTO = {"http": "80", "https": "443"}
# Métodos que pueden cambiar datos: pasan por la comprobación de Origin y, en
# la API, por la de Sec-Fetch-Site, el token CSRF y el cuerpo JSON.
METODOS_QUE_CAMBIAN = frozenset({"POST", "PUT", "PATCH", "DELETE"})
METODOS_CON_CUERPO = frozenset({"POST", "PUT", "PATCH"})
# Sec-Fetch-Site que se aceptan en la API: misma página o escrito a mano
# ("none"). "same-site" no: otro subdominio de duckdns.org sería "mismo sitio".
SITIOS_PERMITIDOS = frozenset({"same-origin", "none"})
MENSAJE_SOLO_JSON = "El cuerpo de la petición debe ser JSON (Content-Type: application/json)."

# Ítem 20: direcciones de la v1 -> pantalla equivalente de la app. Destinos
# fijos (nunca armados con lo que llega en la petición): no hay redirección
# abierta. 307 y no 301: un 301 lo guarda el navegador para siempre.
INICIO_APP = frontend.PREFIJO + "/"
REDIRECCIONES_V1 = {
    "/login": INICIO_APP,
    "/saldo": frontend.PREFIJO + "/saldo",
    "/sin-categorizar": frontend.PREFIJO + "/movimientos",
    "/reglas": frontend.PREFIJO + "/categorias",
}
CODIGO_REDIRECCION = 307


def _host_normalizado(netloc: str, esquema: str) -> str:
    """Host en minúsculas y sin el puerto por defecto del esquema."""
    netloc = netloc.strip().lower()
    puerto = PUERTOS_POR_DEFECTO.get(esquema)
    if puerto and netloc.endswith(":" + puerto):
        netloc = netloc[: -len(puerto) - 1]
    return netloc


def origen_permitido(origen: str | None, host: str | None) -> bool:
    """``True`` si no hay ``Origin`` o si su host coincide con el de la petición.

    ``Origin: null`` (p. ej. desde un iframe con sandbox) o un valor que no
    se entiende se rechazan. Se compara con el encabezado ``Host``: detrás
    de Caddy llega el del navegador, porque Caddy lo reenvía tal cual.
    """
    if origen is None:
        return True
    partes = urlsplit(origen.strip())
    if partes.scheme not in PUERTOS_POR_DEFECTO or not partes.netloc or not host:
        return False
    return _host_normalizado(partes.netloc, partes.scheme) == _host_normalizado(host, partes.scheme)


def sitio_permitido(sec_fetch_site: str | None) -> bool:
    """``True`` si no viene ``Sec-Fetch-Site`` (navegador viejo o no navegador) o es del mismo origen."""
    if sec_fetch_site is None:
        return True
    return sec_fetch_site.strip().lower() in SITIOS_PERMITIDOS


def _es_json(content_type: str | None) -> bool:
    """``application/json`` (con o sin ``; charset=...``). Un formulario de otro sitio no puede enviarlo."""
    if not content_type:
        return False
    return content_type.split(";", 1)[0].strip().lower() == "application/json"


def destino_inicio(mes: str | None) -> str:
    """A dónde va ``/`` (o ``/?mes=AAAA-MM``, el enlace de un mes en la v1).

    El mes solo se conserva si es válido, y se reescribe con ``texto_mes``:
    el destino nunca lleva texto recibido, así que no sirve como redirección
    abierta ni para inyectar nada. Si no es válido, se va al mes actual.
    """
    if mes is not None:
        try:
            return INICIO_APP + "?mes=" + reporte.texto_mes(*reporte.leer_mes(mes))
        except reporte.ErrorReporte:
            pass
    return INICIO_APP


def crear_app(
    config: Config | None = None,
    fabrica_cliente_gmail: Callable[[], ClienteGmail] | None = None,
    directorio_frontend: Path | None = None,
) -> FastAPI:
    """Crea la app. Sin ``config``, la lee del entorno (falla si falta algo obligatorio).

    ``fabrica_cliente_gmail`` crea el cliente de Gmail en cada sincronización;
    las pruebas pasan uno falso. Por defecto usa el token de ``GMAIL_TOKEN``.
    ``directorio_frontend`` es la compilación del frontend (por defecto
    ``frontend/dist``; ver ``finanzas.web.frontend``).
    Lanza ``db.BaseNoMigrada`` si la base no está en la última migración.
    """
    if config is None:
        config = Config.desde_entorno()
    if fabrica_cliente_gmail is None:
        def fabrica_cliente_gmail() -> ClienteGmail:
            return cliente_desde_config(config)

    # La app nunca crea ni cambia tablas: exige la base en la última
    # migración (python -m finanzas.migrar, ítem 22) y si no, no arranca.
    from finanzas.bootstrap.persistencia import exigir_al_dia
    exigir_al_dia(config.db_path)

    # redirect_slashes=False: ni la API ni las redirecciones de la v1
    # redirigen "/ruta/" a "/ruta" (esa redirección arma la URL con el Host
    # recibido). Una ruta con barra final da 404.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
    app.state.config = config
    app.state.consulta_categorias = componer_consulta_categorias
    app.state.limitador = LimitadorIntentos(config.max_intentos, config.bloqueo_minutos)
    app.state.fabrica_cliente_gmail = fabrica_cliente_gmail
    # Una sola sincronización a la vez desde la web. Entre procesos (web y
    # temporizador) los duplicados los evita el UNIQUE de gmail_id.
    app.state.candado_sincronizacion = threading.Lock()
    app.state.tokens_ingreso = TokensIngreso()
    app.state.deshacer = RegistroDeshacer()  # ítem 38: copias de lo borrado, unos segundos
    app.state.analisis_importaciones = RegistroBancario(segundos=SEGUNDOS_ANALISIS)
    app.state.archivos_arranque = RegistroBancario(segundos=SEGUNDOS_ANALISIS)
    app.state.analisis_arranque = RegistroBancario(segundos=SEGUNDOS_ANALISIS)
    app.state.historial_arranque = RegistroHistorial(app.state.archivos_arranque, app.state.analisis_arranque)
    app.state.deshacer_conciliacion = RegistroBancario(segundos=30)

    # Orden: el último middleware añadido es el más externo. La sesión debe
    # procesarse antes que la comprobación de login (y esta antes que el token
    # CSRF de la API), y los encabezados de seguridad se añaden a toda
    # respuesta (también a las redirecciones y a los errores).
    @app.middleware("http")
    async def _proteger_api(request: Request, call_next):
        # Solo /api, con sesión ya comprobada (ver el docstring del módulo).
        ruta, metodo = request.url.path, request.method
        if api.es_ruta_api(ruta) and metodo in METODOS_QUE_CAMBIAN:
            es_login = ruta == RUTA_SESION_API and metodo == "POST"
            if not es_login and not dependencias_api.csrf_valido(
                request, request.headers.get(dependencias_api.ENCABEZADO_CSRF)
            ):
                logger.warning("Petición a la API rechazada: token CSRF ausente o inválido")
                return api.error_json(403, dependencias_api.MENSAJE_CSRF)
            subida_banco = ruta in (RUTA_ANALIZAR, RUTA_ARCHIVOS) and metodo == "POST"
            tipo = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
            if subida_banco and tipo != MIME_XLSX:
                return api.error_json(415, "Elige un archivo .xlsx descargado del banco.")
            if metodo in METODOS_CON_CUERPO and not subida_banco and not _es_json(request.headers.get("content-type")):
                return api.error_json(415, MENSAJE_SOLO_JSON)
        return await call_next(request)

    @app.middleware("http")
    async def _exigir_sesion(request: Request, call_next):
        # Los datos solo salen de /api: sin sesión, 401 en JSON (nunca una
        # redirección); el login es la excepción. Fuera de /api, /app es el
        # cascarón sin datos, las rutas de la v1 solo redirigen a él y
        # cualquier otra ruta da 404 (sin decir nada más).
        ruta = request.url.path
        if api.es_ruta_api(ruta):
            es_login = ruta == RUTA_SESION_API and request.method == "POST"
            if not es_login and not dependencias_api.hay_sesion(request):
                return api.error_json(401, dependencias_api.MENSAJE_SIN_SESION)
        return await call_next(request)

    app.add_middleware(
        SessionMiddleware,
        secret_key=config.session_secret,
        session_cookie="sesion",
        max_age=DURACION_SESION,
        same_site="lax",
        https_only=config.cookie_secure,
    )

    # Defensa adicional contra CSRF (ver el docstring del módulo). Va por
    # fuera de la sesión: una petición de otro origen no llega a leerla ni a cambiarla.
    @app.middleware("http")
    async def _verificar_origen(request: Request, call_next):
        if request.method not in METODOS_QUE_CAMBIAN:
            return await call_next(request)
        es_api = api.es_ruta_api(request.url.path)
        if not origen_permitido(request.headers.get("origin"), request.headers.get("host")):
            logger.warning("Petición rechazada: Origin distinto del host")  # sin valores
            if es_api:
                return api.error_json(403, MENSAJE_ORIGEN_AJENO)
            return Response(MENSAJE_ORIGEN_AJENO, status_code=403, media_type="text/plain; charset=utf-8")
        if es_api and not sitio_permitido(request.headers.get("sec-fetch-site")):
            logger.warning("Petición a la API rechazada: Sec-Fetch-Site de otro sitio")
            return api.error_json(403, MENSAJE_ORIGEN_AJENO)
        return await call_next(request)

    @app.middleware("http")
    async def _encabezados_seguridad(request: Request, call_next):
        respuesta = await call_next(request)
        for nombre, valor in ENCABEZADOS_SEGURIDAD.items():
            respuesta.headers.setdefault(nombre, valor)
        # Las respuestas de la API tienen datos financieros: que ni el navegador
        # ni un proxy las guarden. Solo los archivos con hash del frontend (que
        # no llevan datos) pueden cachearse.
        if not request.url.path.startswith(PREFIJOS_CACHEABLES):
            respuesta.headers["Cache-Control"] = "no-store"
        return respuesta

    api.instalar(app)  # API JSON (ítem 10): mismas sesión, cookie y protecciones
    frontend.instalar(app, directorio_frontend)  # frontend en /app (ítem 12)
    _instalar_redirecciones_v1(app)  # ítem 20

    return app


def _instalar_redirecciones_v1(app: FastAPI) -> None:
    """Las direcciones de lectura de la v1 (marcadores, PWA vieja) llevan a ``/app``.

    Solo ``GET`` y ``HEAD``: los formularios de la v1 (``POST /login``,
    ``/logout``, ``/sincronizar``…) ya no existen y dan 404 o 405. Públicas:
    no leen la base ni la sesión.
    """

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def ir_al_inicio(request: Request) -> Response:
        # Si llega más de un ``mes``, cuenta solo el primero.
        meses = request.query_params.getlist("mes")
        return RedirectResponse(destino_inicio(meses[0] if meses else None), status_code=CODIGO_REDIRECCION)

    for ruta, destino in REDIRECCIONES_V1.items():
        app.add_api_route(ruta, _redireccion_fija(destino), methods=["GET", "HEAD"], include_in_schema=False)


def _redireccion_fija(destino: str) -> Callable[[], Response]:
    """Una ruta sin parámetros que siempre redirige a ``destino``.

    Sin parámetros a propósito: si ``destino`` fuera un argumento con valor
    por defecto, FastAPI lo leería de la URL (``/reglas?destino=...``) y
    sería una redirección abierta.
    """

    def redirigir() -> Response:
        return RedirectResponse(destino, status_code=CODIGO_REDIRECCION)

    return redirigir
