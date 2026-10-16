"""0012 protege rastro, restricciones y rollback de ambos sentidos."""
import pytest
import sqlite3
from alembic import command, op
from alembic.util import CommandError
from finanzas import migrar
from finanzas.migraciones import esquema_v1
from tests.soporte.migracion_0005 import _sql, _subir_hasta
from tests.soporte.migraciones import crear_base_v1, diferencias, huella, revision


@pytest.fixture
def base(tmp_path):
    ruta = tmp_path / "descartes-inventados.db"
    crear_base_v1(ruta)
    _subir_hasta(ruta, "0011")
    return ruta


def bajar(base):
    with migrar.conectar_para_migrar(str(base)) as conn, conn.begin():
        command.downgrade(migrar._config(conn), "0011")


def test_upgrade_schema_y_downgrade_vacio_conserva_datos(base):
    def foto():
        nombres = [f[0] for f in _sql(base, "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        with sqlite3.connect(base) as conn:
            estructura = esquema_v1.describir(conn)
        return (estructura, {n: _sql(base, f'SELECT * FROM "{n}" ORDER BY 1') for n in nombres})
    antes = foto()
    _subir_hasta(base, "0012")
    assert revision(base) == "0012" and diferencias(base) == []
    bajar(base)
    assert revision(base) == "0011" and foto() == antes


@pytest.mark.parametrize("restaurado", [None, "2026-08-11T10:00:00"])
def test_downgrade_no_pierde_historial_aun_restaurado(base, restaurado):
    _subir_hasta(base, "0012")
    _sql(base, "INSERT INTO descartes_movimientos (movimiento_id,descartado_en,restaurado_en,fecha,monto_centavos,huella_movimiento,huella_contexto) VALUES (1,'2026-08-10T10:00:00',?,'2026-08-10',-12300,'hash-inventado','hash-inventado')", (restaurado,))
    antes = huella(base)
    with pytest.raises(CommandError, match="respaldo"):
        bajar(base)
    assert revision(base) == "0012" and huella(base) == antes


def test_upgrade_error_rollback_no_deja_tabla(base, monkeypatch):
    original = op.create_index
    def fallar(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("fallo inventado")
    monkeypatch.setattr(op, "create_index", fallar)
    antes = huella(base)
    with pytest.raises(RuntimeError):
        _subir_hasta(base, "0012")
    assert revision(base) == "0011" and huella(base) == antes


def test_ddl_portable_metadata_y_migracion_sin_servidor(monkeypatch):
    import importlib
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateIndex, CreateTable
    from finanzas import db
    from types import SimpleNamespace
    metadata = sa.MetaData()
    sa.Table("movimientos", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    preguntas = sa.Table("preguntas_conciliacion", metadata,
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("fuente", sa.Text()),
        sa.Column("respuesta", sa.Text()))
    monkeypatch.setattr(op, "get_bind", lambda: SimpleNamespace(dialect=postgresql.dialect()))
    monkeypatch.setattr(op, "add_column", lambda nombre, columna: preguntas.append_column(columna))
    capturada = {}
    def tabla(nombre, *elementos):
        capturada["tabla"] = sa.Table(nombre, metadata, *elementos)
    def indice(nombre, nombre_tabla, columnas, **kwargs):
        sa.Index(nombre, *(capturada["tabla"].c[c] for c in columnas), **kwargs)
    monkeypatch.setattr(op, "create_table", tabla)
    monkeypatch.setattr(op, "create_index", indice)
    importlib.import_module("finanzas.migraciones.versions.0012_descartes_movimientos").upgrade()
    for t in (db.descartes_movimientos, capturada["tabla"]):
        ddl = str(CreateTable(t).compile(dialect=postgresql.dialect()))
        assert "GLOB" not in ddl and "typeof" not in ddl
        assert "monto_centavos <> 0" in ddl
        assert "monto_banco_centavos <> 0" in ddl
        for dialecto in (postgresql.dialect(), sqlite.dialect()):
            index = str(CreateIndex(next(iter(t.indexes))).compile(dialect=dialecto))
            assert "UNIQUE INDEX" in index and "WHERE restaurado_en IS NULL" in index


@pytest.mark.parametrize("elegido", [False, True])
def test_downgrade_no_pierde_ocurrencias_o_elecciones(base, elegido):
    _subir_hasta(base, "0012")
    _sql(base, "INSERT INTO preguntas_conciliacion (tipo,fuente,fecha,monto_centavos,ocurrencia_banco) VALUES ('es_el_mismo','banco','2026-08-10',-12300,1)")
    if elegido:
        _sql(base, "UPDATE preguntas_conciliacion SET respuesta='si',respondida_en='2026-08-11T10:00:00',movimiento_elegido_id=1")
    antes = huella(base)
    with pytest.raises(CommandError, match="respaldo"):
        bajar(base)
    assert revision(base) == "0012" and huella(base) == antes
