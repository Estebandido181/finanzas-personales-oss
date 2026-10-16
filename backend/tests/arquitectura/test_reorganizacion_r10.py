"""Cierre de fronteras: fallos sintéticos e importación real sin los shims."""
from pathlib import Path
import os
import subprocess
import sys

from scripts.revisar_fronteras import Dependencia, ciclos, dependencias, revisar, violaciones


RAIZ = Path(__file__).resolve().parents[3]


def test_arbol_final_respeta_fronteras_y_no_tiene_ciclos():
    resultado = revisar(RAIZ)
    assert resultado["modulos_python"] > 0
    assert resultado["violaciones"] == []
    assert resultado["ciclos"] == []


def test_detecta_compatibilidad_relativa_y_composicion_diferida():
    aristas = dependencias("finanzas.api.rutas", "from .. import db\n", {"finanzas.db"})
    assert aristas[0].destino == "finanzas.db"
    assert "compatibilidad" in violaciones(aristas)[0]
    fuente = "def guardar():\n    from finanzas.bootstrap.importaciones import componer_reportes\n"
    aristas = dependencias("finanzas.modulos.importaciones.reportes_sqlite", fuente, set())
    assert "composición" in violaciones(aristas)[0]


def test_detecta_adaptador_desde_aplicacion_y_privado_ajeno():
    aristas = [Dependencia("finanzas.modulos.saldo.aplicacion", "sqlalchemy", 1),
               Dependencia("finanzas.modulos.importaciones.aplicacion", "finanzas.modulos.movimientos.consultas_sqlite", 2, ("_conciliado",))]
    assert len(violaciones(aristas)) == 2


def test_detecta_ciclo_incluido_import_diferido():
    nombres = {"finanzas.a", "finanzas.b"}
    aristas = dependencias("finanzas.a", "def ejecutar():\n    from . import b\n", nombres)
    aristas += dependencias("finanzas.b", "from . import a\n", nombres)
    assert ciclos(aristas, nombres) == [["finanzas.a", "finanzas.b", "finanzas.a"]]


def test_composicion_real_no_carga_compatibilidad_y_presta_la_misma_conexion(tmp_path):
    codigo = """
import sys
from sqlalchemy import create_engine
import finanzas.bootstrap.app
from finanzas.bootstrap.unidad_de_trabajo import UnidadDeTrabajoSQLite
from finanzas.bootstrap.importaciones import componer_gestion_importaciones, componer_colaboradores_importacion
from finanzas.bootstrap.arranque import componer_arranque
from finanzas.bootstrap.sincronizacion import componer_sincronizacion
from finanzas.bootstrap.reporte import componer_reporte
with create_engine('sqlite://').connect() as conn:
    unidad = UnidadDeTrabajoSQLite(conn)
    assert unidad._conn is conn
    assert unidad.categorias._conn is conn
    assert unidad.movimientos._conn is conn
    assert unidad.reglas._conn is conn
    assert unidad.saldo._conn is conn
    gestion = componer_gestion_importaciones(conn)
    assert gestion._unidad.gestion._conn is conn
    arranque = componer_arranque(conn)
    assert arranque._unidad.importaciones._conn is conn
    assert arranque._unidad.avisos._conn is conn
    sincronizacion = componer_sincronizacion(conn)
    assert sincronizacion._registro._conn is conn
    reporte = componer_reporte(conn)
    assert reporte._conn is conn
    assert reporte.movimientos._conn is conn
    assert not conn.in_transaction()
for nombre in ('db', 'saldo', 'categorizacion', 'importacion', 'gestion_importaciones',
               'arranque', 'inicio', 'reporte', 'sincronizacion', 'gmail', 'extractor',
               'excel_bancolombia', 'tokens_ingreso', 'tokens_bancarios', 'deshacer'):
    assert 'finanzas.' + nombre not in sys.modules, nombre
"""
    resultado = subprocess.run([sys.executable, "-c", codigo], cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(RAIZ / "backend")), text=True, capture_output=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr
