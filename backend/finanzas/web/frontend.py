"""Sirve el frontend nuevo (ítem 12, D16 y D17) en ``/app``.

El frontend es una app React compilada con Vite a archivos estáticos
(``frontend/dist``, ver ``frontend/`` y la guía de despliegue, 13.2). Esta
misma app de FastAPI los sirve, en el mismo dominio que la API: así el login
por cookie y el CSRF funcionan igual que en ``/api``.

Rutas:

* ``/app`` redirige a ``/app/`` (Vite compila con ``base: "/app/"``).
* ``/app/assets/<archivo>``: JS, CSS, fuentes e imágenes con hash en el
  nombre. Si el contenido cambia, cambia el nombre, así que se pueden
  guardar un año (``immutable``). No llevan datos.
* ``/app/<archivo con extensión>`` (``tema-inicial.js``): archivos de
  ``public/`` sin hash. Son pocos y pequeños: ``no-store``, como el índice.
* Cualquier otra ruta de ``/app/`` (``/app/saldo``, ``/app/mas``…) devuelve
  ``index.html``: el enrutador del frontend decide qué pantalla mostrar.
  ``no-store``: al publicar una versión nueva se carga la nueva.
* Un archivo que no existe da 404 (nunca ``index.html``, para que un script
  que falta no se lea como HTML).

``/app`` es público (no exige sesión): es solo el cascarón, sin datos. Los
datos llegan de ``/api``, que sí exige sesión y responde 401 sin ella; el
frontend muestra entonces su pantalla de entrar. Los encabezados de
seguridad (CSP estricta incluida) los pone el middleware de
``finanzas.web.app`` a toda respuesta.

Si no hay compilación (no se corrió ``npm run build``), la app arranca igual
y ``/app`` responde 503 con un texto que dice qué hacer; ``/`` y ``/api``
siguen funcionando.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response

PREFIJO = "/app"
PREFIJO_ASSETS = PREFIJO + "/assets/"
DIRECTORIO_POR_DEFECTO = Path(__file__).resolve().parents[3] / "frontend" / "dist"

CACHE_ASSETS = "public, max-age=31536000, immutable"
CACHE_INDICE = "no-store"

MENSAJE_SIN_COMPILAR = (
    "El frontend nuevo no está compilado. Compílalo con los pasos de la guía de "
    "despliegue (deploy/GUIA.md, 13.2) o, en local, con: "
    "cd frontend && npm ci --ignore-scripts && npm run build"
)

# El tipo MIME explícito para lo que produce Vite: el módulo ``mimetypes`` de
# Python depende del sistema y no siempre conoce woff2. Con ``nosniff`` un
# script con tipo equivocado no se ejecuta.
TIPOS = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".png": "image/png",
    ".webmanifest": "application/manifest+json",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
}


def es_ruta_frontend(ruta: str) -> bool:
    return ruta == PREFIJO or ruta.startswith(PREFIJO + "/")


def _archivo_dentro(base: Path, relativa: str) -> Path | None:
    """``base/relativa`` si existe, es un archivo y no se sale de ``base`` (sin ``..``)."""
    if not relativa or "\x00" in relativa:
        return None
    try:
        candidato = (base / relativa).resolve()
        base_real = base.resolve()
    except (OSError, ValueError):
        return None
    if not candidato.is_relative_to(base_real) or not candidato.is_file():
        return None
    return candidato


def _archivo(ruta: Path, cache: str) -> FileResponse:
    return FileResponse(
        ruta,
        media_type=TIPOS.get(ruta.suffix.lower()),
        headers={"Cache-Control": cache},
    )


def _sin_cache(texto: str, estado: int) -> PlainTextResponse:
    """404 o 503 que nadie debe guardar: bajo /app/assets/ el middleware no pone
    ``no-store`` (ahí se permite la caché), así que se pone aquí. Si no, un 404
    durante un despliegue a medias podría quedar guardado."""
    return PlainTextResponse(texto, status_code=estado, headers={"Cache-Control": CACHE_INDICE})


def instalar(app: FastAPI, directorio: Path | None = None) -> None:
    """Añade las rutas de ``/app``. ``directorio`` es la carpeta del build (las pruebas pasan otra)."""
    base = Path(directorio) if directorio is not None else DIRECTORIO_POR_DEFECTO

    @app.api_route(PREFIJO, methods=["GET", "HEAD"], include_in_schema=False)
    def ir_al_frontend() -> Response:
        return RedirectResponse(PREFIJO + "/", status_code=307)

    @app.api_route(PREFIJO + "/{ruta:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def servir_frontend(ruta: str) -> Response:
        indice = base / "index.html"
        if not indice.is_file():
            return _sin_cache(MENSAJE_SIN_COMPILAR, 503)
        if ruta.startswith("assets/"):
            archivo = _archivo_dentro(base, ruta)
            if archivo is None:
                return _sin_cache("No encontrado.", 404)
            return _archivo(archivo, CACHE_ASSETS)
        ultimo = ruta.rsplit("/", 1)[-1]
        if "." in ultimo:
            archivo = _archivo_dentro(base, ruta)
            if archivo is None or archivo.name == "index.html":
                return _sin_cache("No encontrado.", 404)
            return _archivo(archivo, CACHE_INDICE)
        return _archivo(indice, CACHE_INDICE)
