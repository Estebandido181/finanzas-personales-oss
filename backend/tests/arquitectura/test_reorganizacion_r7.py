"""Operación explícita, rutas desde cwd ajeno y fronteras de persistencia."""
import ast
import os
from pathlib import Path
import subprocess
import sys


RAIZ = Path(__file__).resolve().parents[3]


def ejecutar(codigo, carpeta):
    entorno = dict(os.environ, PYTHONPATH=str(RAIZ / "backend"))
    resultado = subprocess.run([sys.executable, "-c", codigo], cwd=carpeta,
        env=entorno, text=True, capture_output=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr


def test_conexion_no_carga_operacion_ni_crea_tablas(tmp_path):
    ejecutar("""
import sys
from sqlalchemy import inspect
from finanzas.infraestructura.persistencia.conexion import conectar
with conectar('ejemplo.db') as conn:
    assert inspect(conn).get_table_names() == []
    assert conn.exec_driver_sql('PRAGMA foreign_keys').scalar_one() == 1
assert 'finanzas.migrar' not in sys.modules
assert 'finanzas.operacion.revisiones' not in sys.modules
""", tmp_path)


def test_catalogo_y_respaldo_se_localizan_desde_cwd_ajeno(tmp_path):
    ejecutar("""
import sys
from finanzas.operacion.revisiones import revision_final, _scripts
from finanzas.operacion.respaldo import RUTA_RESPALDO, _modulo_respaldo
assert revision_final() == '0012'
assert len(list(_scripts().walk_revisions())) == 12
assert RUTA_RESPALDO.is_file()
assert callable(_modulo_respaldo().crear_respaldo)
assert 'finanzas.migrar' not in sys.modules
assert 'finanzas.bootstrap.app' not in sys.modules
""", tmp_path)


def test_persistencia_no_importa_ejecutor_operacion_o_bootstrap():
    for ruta in (RAIZ / 'backend/finanzas/infraestructura/persistencia').glob('*.py'):
        arbol = ast.parse(ruta.read_text(encoding='utf-8'))
        imports = [n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)]
        imports += [a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names]
        assert not any(m and m.startswith(('finanzas.migrar', 'finanzas.operacion', 'finanzas.bootstrap', 'finanzas.db')) for m in imports)
