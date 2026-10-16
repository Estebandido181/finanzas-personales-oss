"""0011 conserva datos, downgrade explícito y rollback sin perdida del diario."""
import pytest
from alembic import command
from alembic.util import CommandError
from finanzas import migrar
from tests.soporte.migracion_0005 import _sql, _subir_hasta
from tests.soporte.migraciones import crear_base_v1, huella, revision


@pytest.fixture
def base(tmp_path):
    ruta = tmp_path / "historial-inventado.db"
    crear_base_v1(ruta)
    _subir_hasta(ruta, "0010")
    return ruta


def bajar(base):
    with migrar.conectar_para_migrar(str(base)) as conn, conn.begin():
        command.downgrade(migrar._config(conn), "0010")


def test_upgrade_y_downgrade_sin_arranque_conservan_datos(base):
    nombres = [fila[0] for fila in _sql(base, "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    # SQLite reformatea CREATE TABLE al DROP COLUMN; la igualdad relevante
    # es de filas, columnas y restricciones, no el espacio del DDL textual.
    def foto():
        return {nombre: (_sql(base, f'SELECT * FROM "{nombre}"'),
            _sql(base, f'PRAGMA table_info("{nombre}")'),
            _sql(base, f'PRAGMA foreign_key_list("{nombre}")'),
            _sql(base, f'PRAGMA index_list("{nombre}")')) for nombre in nombres}
    antes = foto()
    _subir_hasta(base, "0011")
    assert revision(base) == "0011"
    assert _sql(base, "SELECT arranque FROM reversiones_importacion") == []
    bajar(base)
    assert revision(base) == "0010" and foto() == antes


def test_downgrade_impide_perder_reversion_guiada(base):
    _subir_hasta(base, "0011")
    _sql(base, "INSERT INTO importaciones (id,filas) VALUES (1,0)")
    _sql(base, "INSERT INTO reversiones_importacion VALUES (1,'[]','{}',6,'{}')")
    antes = huella(base)
    with pytest.raises(CommandError, match="respaldo"):
        bajar(base)
    assert huella(base) == antes and revision(base) == "0011"


def test_upgrade_error_revierte_columna_y_revision(base, monkeypatch):
    from alembic import op
    original = op.add_column
    def fallar(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("fallo inventado")
    monkeypatch.setattr(op, "add_column", fallar)
    antes = huella(base)
    with pytest.raises(RuntimeError):
        _subir_hasta(base, "0011")
    assert huella(base) == antes and revision(base) == "0010"
