"""API: la descripción OpenAPI versionada coincide con el código (ítem 10).

``openapi/openapi.json`` es el contrato del que salen los tipos de TypeScript
del frontend. Si esta prueba falla, la API cambió: vuelve a exportarlo con
``python -m finanzas.api.exportar_openapi`` y revisa el diff.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from finanzas.api import esquema_openapi
from finanzas.api.exportar_openapi import SALIDA_POR_DEFECTO, main, texto_openapi

RAIZ = Path(__file__).resolve().parents[3]


def test_el_archivo_versionado_coincide_con_el_codigo():
    assert SALIDA_POR_DEFECTO == RAIZ / "openapi" / "openapi.json"
    assert SALIDA_POR_DEFECTO.read_text(encoding="utf-8") == texto_openapi(), (
        "openapi/openapi.json está desactualizado: ejecuta python -m finanzas.api.exportar_openapi"
    )


def test_exportar_sin_entorno_ni_base(tmp_path):
    # Sin variables de entorno de la app ni base de datos: solo el código.
    entorno = {k: v for k, v in os.environ.items() if k not in {"DB_PATH", "APP_PASSWORD_HASH", "SESSION_SECRET"}}
    salida = tmp_path / "sub" / "openapi.json"
    r = subprocess.run(
        [sys.executable, "-m", "finanzas.api.exportar_openapi", "--salida", str(salida)],
        cwd=tmp_path, env={**entorno, "PYTHONPATH": str(RAIZ / "backend")}, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert salida.read_text(encoding="utf-8") == texto_openapi()
    assert list(tmp_path.glob("*.db")) == []


def test_main_escribe_el_archivo(tmp_path, capsys):
    salida = tmp_path / "openapi.json"
    assert main(["--salida", str(salida)]) == 0
    assert json.loads(salida.read_text(encoding="utf-8"))["openapi"].startswith("3.")


def test_contrato_basico():
    esquema = esquema_openapi()
    rutas = esquema["paths"]
    assert all(ruta.startswith("/api/") for ruta in rutas)
    ids = [op["operationId"] for ops in rutas.values() for op in ops.values()]
    assert len(ids) == len(set(ids))  # nombres únicos y estables para los tipos
    assert "ver_reporte" in ids and "iniciar_sesion" in ids
    # Montos enteros: ningún campo *_centavos es "number".
    for nombre, modelo in esquema["components"]["schemas"].items():
        for campo, definicion in modelo.get("properties", {}).items():
            if campo.endswith("_centavos") or campo == "centavos":
                tipos = [definicion.get("type")] + [o.get("type") for o in definicion.get("anyOf", [])]
                assert "number" not in tipos, (nombre, campo)
                assert "integer" in tipos, (nombre, campo)
                for opcion in [definicion] + definicion.get("anyOf", []):
                    for limite in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
                        if limite in opcion:
                            assert isinstance(opcion[limite], int), (nombre, campo, limite)
    # Lo que cambia datos declara el encabezado CSRF, salvo el login.
    for ruta, operaciones in rutas.items():
        for metodo, operacion in operaciones.items():
            if metodo in {"post", "put", "patch", "delete"} and operacion["operationId"] != "iniciar_sesion":
                encabezados = [p["name"] for p in operacion.get("parameters", []) if p["in"] == "header"]
                assert "X-CSRF-Token" in encabezados, (metodo, ruta)
    # Ningún límite numérico sale como float (1000000000000.0), tampoco en los ids.
    texto = json.dumps(esquema)
    assert ".0," not in texto and ".0}" not in texto and "e+" not in texto
    # Los 422 usan el formato propio (sin eco de valores), no el de FastAPI.
    assert "HTTPValidationError" not in esquema["components"]["schemas"]
