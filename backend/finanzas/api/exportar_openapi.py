"""Exporta la descripción OpenAPI de la API a un archivo, sin arrancar el servidor.

Uso (desde la raíz del repositorio)::

    python -m finanzas.api.exportar_openapi            # escribe openapi/openapi.json
    python -m finanzas.api.exportar_openapi --salida otra/ruta.json

No necesita variables de entorno ni base de datos. El JSON sale ordenado y
con saltos de línea estables, para que el diff de un cambio de la API se lea
bien. ``openapi/openapi.json`` se versiona y una prueba falla si no coincide
con el código: al cambiar la API hay que volver a exportarlo.

Los tipos de TypeScript se generan a partir de este archivo (ver el README).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from finanzas.api import esquema_openapi

RAIZ = Path(__file__).resolve().parents[3]
SALIDA_POR_DEFECTO = RAIZ / "openapi" / "openapi.json"


def texto_openapi() -> str:
    return json.dumps(esquema_openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exporta openapi.json de la API.")
    parser.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO, help="archivo de salida")
    argumentos = parser.parse_args(argv)
    argumentos.salida.parent.mkdir(parents=True, exist_ok=True)
    argumentos.salida.write_text(texto_openapi(), encoding="utf-8")
    print(f"OpenAPI escrito en {argumentos.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
