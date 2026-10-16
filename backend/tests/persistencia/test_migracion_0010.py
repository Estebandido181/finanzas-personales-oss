"""0010: saldo intacto, límites de base y downgrade sin pérdida silenciosa."""
import pytest
from alembic import command
from alembic.util import CommandError
from finanzas import db, migrar
from tests.soporte.migracion_0005 import _sql, _subir_hasta
from tests.soporte.migraciones import crear_base_v1, huella, revision


@pytest.fixture
def base(tmp_path):
    ruta = tmp_path / "banco-inventado.db"
    crear_base_v1(ruta)
    _subir_hasta(ruta, "0009")
    return ruta


def bajar(ruta):
    with migrar.conectar_para_migrar(str(ruta)) as conn, conn.begin():
        cfg = migrar._config(conn)
        command.downgrade(cfg, "0009")


def test_upgrade_y_downgrade_vacio_conservan_datos_y_revision(base):
    antes = _sql(base, "SELECT * FROM movimientos"), _sql(base, "SELECT * FROM reglas")
    _subir_hasta(base, "0010")
    assert revision(base) == "0010"
    assert _sql(base, "SELECT borrado_en,revisado_no_en_banco FROM movimientos") == [(None, 0)] * 6
    assert _sql(base, "SELECT modo_texto,origen_regla FROM reglas") == [("exacta", "todos")]
    bajar(base)
    assert revision(base) == "0009"
    assert (_sql(base, "SELECT * FROM movimientos"), _sql(base, "SELECT * FROM reglas")) == antes


@pytest.mark.parametrize("sentencia", [
    "UPDATE movimientos SET revisado_no_en_banco=1 WHERE id=1",
    "UPDATE movimientos SET borrado_en='2026-08-10T10:00:00' WHERE id=1",
    "UPDATE reglas SET modo_texto='contiene',origen_regla='extracto' WHERE id=1",
    "UPDATE reglas SET texto_visible='COMERCIO INVENTADO' WHERE id=1"])
def test_downgrade_se_niega_sin_tocar_nada_si_se_uso(base, sentencia):
    _subir_hasta(base, "0010")
    _sql(base, sentencia)
    antes = huella(base)
    with pytest.raises(CommandError, match="respaldo"):
        bajar(base)
    assert huella(base) == antes and revision(base) == "0010"


@pytest.mark.parametrize("sentencia", [
    "UPDATE movimientos SET revisado_no_en_banco=7",
    "UPDATE reglas SET modo_texto='regex'",
    "UPDATE reglas SET origen_regla='sin_limite'"])
def test_checks_se_aplican_en_base_migrada(base, sentencia):
    import sqlite3
    _subir_hasta(base, "0010")
    with pytest.raises(sqlite3.IntegrityError):
        _sql(base, sentencia)


def test_fallo_intermedio_de_upgrade_revierte_estructura_y_datos(base, monkeypatch):
    from alembic import op
    original = op.create_table
    def fallar(nombre, *args, **kwargs):
        if nombre == "reversiones_importacion":
            raise RuntimeError("fallo de prueba")
        return original(nombre, *args, **kwargs)
    antes = huella(base)
    monkeypatch.setattr(op, "create_table", fallar)
    with pytest.raises(RuntimeError):
        _subir_hasta(base, "0010")
    assert huella(base) == antes and revision(base) == "0009"
