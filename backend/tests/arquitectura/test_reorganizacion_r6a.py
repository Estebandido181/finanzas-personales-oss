"""Fronteras puras de flujos y copias opacas en RAM."""
import ast
from pathlib import Path
from finanzas.infraestructura.tokens_bancarios_ram import RegistroBancario
from finanzas.infraestructura.deshacer_ram import RegistroDeshacer


def test_flujos_no_importan_sql_http_ni_bootstrap():
    for ruta in Path("backend/finanzas/flujos").glob("*.py"):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        imports = [n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)]
        imports += [a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names]
        assert not any(m and m.startswith(("sqlalchemy", "fastapi", "starlette", "finanzas.bootstrap", "finanzas.db")) for m in imports)


def test_ram_preserva_copia_opaca_y_propietario_sin_conocer_su_tipo():
    copia = object()
    registro = RegistroBancario(30, reloj=lambda: 0)
    token = registro.guardar(copia, "sesion-ejemplo")
    assert registro.tomar(token, "otra-sesion") is None
    assert registro.ver(token, "sesion-ejemplo").copia is copia
    assert registro.tomar(token, "sesion-ejemplo").copia is copia
    assert registro.tomar(token, "sesion-ejemplo") is None
    deshacer = RegistroDeshacer(30, reloj=lambda: 0)
    token = deshacer.guardar(copia)
    assert deshacer.tomar(token).copia is copia
    assert deshacer.tomar(token) is None
