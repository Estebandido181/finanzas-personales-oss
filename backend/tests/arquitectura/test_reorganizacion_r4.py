"""Fronteras de lectura y compatibilidad de entradas operativas."""
import subprocess
import sys


def test_lectores_y_contratos_se_cargan_sin_sql_http_ni_cliente_google():
    programa = """
import sys
from finanzas.modulos.importaciones.publico import MovimientoExcel
from finanzas.modulos.importaciones.adaptadores.archivos import excel_bancolombia
from finanzas.modulos.sincronizacion.publico import MovimientoExtraido, CorreoGmail
from finanzas.modulos.sincronizacion.adaptadores.avisos import extractor, lector
from finanzas.modulos.sincronizacion.adaptadores.gmail import mime, autenticidad
prohibidos = ('sqlalchemy', 'fastapi', 'starlette', 'google', 'googleapiclient',
              'google_auth_oauthlib', 'finanzas.db', 'finanzas.importacion',
              'finanzas.sincronizacion', 'finanzas.bootstrap', 'openpyxl')
assert not any(n == p or n.startswith(p + '.') for n in sys.modules for p in prohibidos)
assert excel_bancolombia.MovimientoExcel is MovimientoExcel
assert extractor.MovimientoExtraido is MovimientoExtraido
assert mime.CorreoGmail is CorreoGmail
"""
    subprocess.run([sys.executable, '-c', programa], check=True, capture_output=True)


def test_comando_historico_y_operacion_nueva_ofrecen_la_misma_ayuda():
    resultados = []
    for modulo in ('finanzas.gmail', 'finanzas.operaciones.autorizar_gmail'):
        resultado = subprocess.run(
            [sys.executable, '-X', 'utf8', '-m', modulo, 'autorizar', '--help'],
            check=True, capture_output=True, text=True,
        )
        resultados.append(resultado.stdout)
    assert resultados[0] == resultados[1]
    assert '--sin-navegador' in resultados[0]
    assert '--borrar-credenciales' in resultados[0]
