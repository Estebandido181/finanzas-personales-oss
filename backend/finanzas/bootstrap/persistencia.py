"""Composición de la revisión de arranque, sin aplicar migraciones."""
from finanzas.infraestructura.persistencia.conexion import conectar
from finanzas.infraestructura.persistencia.revision import exigir_al_dia as _verificar
from finanzas.operacion.revisiones import revision_final


def exigir_al_dia(ruta: str) -> None:
    _verificar(ruta, revision_final(), conectar)
