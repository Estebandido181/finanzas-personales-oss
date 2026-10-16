"""Preview real por puertos, rollback siempre y contrato puro."""
from finanzas.bootstrap.saldo import componer_saldo
import subprocess
import sys
import pytest
from finanzas import gestion_importaciones as gestion
from finanzas.modulos.importaciones.gestion_sqlite import GestionSQLite
from tests.soporte.importacion import conn, fila  # noqa: F401


def test_gestion_interactiva_carga_sin_sql_ni_bootstrap():
    programa = """
import sys
from finanzas.modulos.importaciones.gestion_aplicacion import GestionarImportaciones
prohibidos = ('sqlalchemy', 'fastapi', 'finanzas.db', 'finanzas.gestion_importaciones',
              'finanzas.bootstrap', 'finanzas.excel_bancolombia')
assert not any(n == p or n.startswith(p + '.') for n in sys.modules for p in prohibidos)
"""
    subprocess.run([sys.executable, '-c', programa], check=True, capture_output=True)


def test_fallo_en_preview_despues_del_guardado_no_deja_filas_ni_diario(conn, monkeypatch):
    antes = gestion.huella(conn)
    saldo_antes = componer_saldo(conn).saldo_actual()
    contar = GestionSQLite.entran_categorizados

    def fallar_despues(self, ident):
        contar(self, ident)
        raise RuntimeError('fallo inventado después del guardado')

    monkeypatch.setattr(GestionSQLite, 'entran_categorizados', fallar_despues)
    with pytest.raises(RuntimeError, match='fallo inventado'):
        gestion.analizar(conn, [fila(10, -150000)])
    assert gestion.huella(conn) == antes
    assert componer_saldo(conn).saldo_actual() == saldo_antes
