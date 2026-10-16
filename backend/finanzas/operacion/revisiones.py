"""Catálogo de Alembic para leer/verificar; no aplica revisiones."""
import functools
from pathlib import Path
from sqlalchemy import Connection
from alembic.config import Config as ConfigAlembic
from alembic.script import ScriptDirectory
from alembic.script.revision import RevisionError
from alembic.util import CommandError

CARPETA_MIGRACIONES = Path(__file__).resolve().parents[1] / "migraciones"

def _config(conexion: Connection | None = None) -> ConfigAlembic:
    config = ConfigAlembic()
    config.set_main_option("script_location", str(CARPETA_MIGRACIONES))
    config.attributes["connection"] = conexion
    return config


@functools.cache
def _scripts() -> ScriptDirectory:
    return ScriptDirectory.from_config(_config())


def revision_final() -> str:
    """La última revisión (``head``) de las migraciones del código."""
    return str(_scripts().get_current_head())


def _revision_conocida(revision: str) -> bool:
    """``True`` si ``revision`` es una migración de este código (``"base"`` no lo es)."""
    try:
        return _scripts().get_revision(revision) is not None
    except (CommandError, RevisionError):
        return False


def _pendientes(desde: str | None) -> list[str]:
    """Revisiones después de ``desde`` hasta la final, de la más antigua a la más nueva."""
    revisiones = _scripts().iterate_revisions("head", desde or "base")
    return [r.revision for r in reversed(list(revisiones))]
