"""Frontera pura del diario y sus huellas."""
import subprocess
import sys


def test_diario_y_contrato_de_analisis_sin_infraestructura():
    programa = """
import sys
from finanzas.modulos.importaciones.diario import diario, huella_de_foto
from finanzas.modulos.importaciones.contratos import Analisis
prohibidos = ('sqlalchemy', 'fastapi', 'finanzas.db', 'finanzas.gestion_importaciones',
              'finanzas.bootstrap', 'finanzas.excel_bancolombia')
assert not any(n == p or n.startswith(p + '.') for n in sys.modules for p in prohibidos)
"""
    subprocess.run([sys.executable, '-c', programa], check=True, capture_output=True)
