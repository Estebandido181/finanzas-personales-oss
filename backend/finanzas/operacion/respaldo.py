"""Carga explícita del respaldo estándar, sin bootstrap ni migraciones."""
import functools
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Protocol
from datetime import date

RUTA_RESPALDO = Path(__file__).resolve().parents[3] / "deploy" / "respaldo.py"


class Respaldo(Protocol):
    def crear_respaldo(self, origen: Path, destino: Path, hoy: date, nombre: str | None = None) -> Path: ...


@functools.cache
def _modulo_respaldo() -> Respaldo:
    """``deploy/respaldo.py`` (solo usa la librería estándar; no es un paquete)."""
    spec = importlib.util.spec_from_file_location("finanzas_respaldo", RUTA_RESPALDO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo
