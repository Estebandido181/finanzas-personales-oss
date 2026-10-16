"""Asignación: la frontera de aplicación permanece independiente de adaptadores."""
import subprocess
import sys


def test_asignacion_no_carga_sql_http_fuentes_ni_composicion():
    codigo = (
        "import sys; import finanzas.modulos.categorias.asignacion; "
        "assert not any(m.startswith(('sqlalchemy', 'fastapi', 'starlette', "
        "'finanzas.db', 'finanzas.bootstrap', 'finanzas.infraestructura', "
        "'finanzas.extractor', 'finanzas.gmail')) for m in sys.modules)"
    )
    resultado = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr
