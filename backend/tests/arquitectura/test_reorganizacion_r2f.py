"""R2: grupos y consultas dependen de datos puros y del registro público."""
import subprocess
import sys


def test_grupos_catalogo_y_asignacion_no_cargan_infraestructura():
    codigo = (
        "import sys; import finanzas.modulos.categorias.grupos; "
        "import finanzas.modulos.categorias.catalogo; import finanzas.modulos.categorias.asignacion; "
        "assert not any(m.startswith(('sqlalchemy', 'fastapi', 'starlette', "
        "'finanzas.db', 'finanzas.bootstrap', 'finanzas.infraestructura', "
        "'finanzas.extractor', 'finanzas.saldo')) for m in sys.modules)"
    )
    resultado = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr
