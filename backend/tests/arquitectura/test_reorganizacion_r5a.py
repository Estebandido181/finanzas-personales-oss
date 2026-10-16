"""Fronteras del motor y de incorporación de avisos tardíos."""
import ast
from pathlib import Path
import subprocess
import sys


def test_motor_y_contratos_se_cargan_sin_persistencia_ni_sincronizacion():
    programa = """
import sys
from finanzas.modulos.importaciones import motor, publico
prohibidos = ('sqlalchemy', 'fastapi', 'finanzas.db', 'finanzas.sincronizacion',
              'finanzas.importacion', 'finanzas.bootstrap', 'googleapiclient')
assert not any(n == p or n.startswith(p + '.') for n in sys.modules for p in prohibidos)
"""
    subprocess.run([sys.executable, '-c', programa], check=True, capture_output=True)


def test_importacion_no_depende_del_modulo_historico_de_sincronizacion():
    from finanzas import importacion, sincronizacion
    for modulo, prohibido in ((importacion, 'sincronizacion'), (sincronizacion, 'importacion')):
        arbol = ast.parse(Path(modulo.__file__).read_text(encoding='utf-8'))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom):
                assert nodo.module != 'finanzas.' + prohibido
                if nodo.module == 'finanzas':
                    assert prohibido not in {a.name for a in nodo.names}
            elif isinstance(nodo, ast.Import):
                assert 'finanzas.' + prohibido not in {a.name for a in nodo.names}
