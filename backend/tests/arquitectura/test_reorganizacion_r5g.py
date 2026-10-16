"""Consultas, sugerencias y presentación puras sin duplicar simulación."""
import subprocess
import sys


def test_diferencias_y_frases_cargan_sin_infraestructura():
    programa = """
import sys
from finanzas.modulos.importaciones.diferencias_aplicacion import ConsultarDiferencias
from finanzas.modulos.importaciones.gestion_aplicacion import GestionarImportaciones
from finanzas.modulos.categorias.presentacion import pesos, frase_regla
prohibidos = ('sqlalchemy', 'fastapi', 'finanzas.db', 'finanzas.gestion_importaciones',
              'finanzas.bootstrap', 'finanzas.categorizacion')
assert not any(n == p or n.startswith(p + '.') for n in sys.modules for p in prohibidos)
"""
    subprocess.run([sys.executable, '-c', programa], check=True, capture_output=True)
