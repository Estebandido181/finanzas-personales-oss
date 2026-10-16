"""Bootstrap: no instalar al comprobar, fallos visibles y npm dentro del checkout."""
from pathlib import Path
import os
import subprocess
import sys

import pytest

from scripts import preparar_entorno as entorno


def test_paquete_instalado_y_comando_desde_otro_directorio(tmp_path):
    """La VM invoca finanzas desde la raíz: pytest por sí solo no instala el paquete."""
    env = {clave: valor for clave, valor in os.environ.items() if clave != "PYTHONPATH"}
    importacion = subprocess.run(
        [sys.executable, "-c", "import finanzas; print(finanzas.__file__)"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )
    assert importacion.returncode == 0, importacion.stderr
    assert "backend" in Path(importacion.stdout.strip()).parts
    comando = subprocess.run(
        [sys.executable, "-m", "finanzas.migrar", "--help"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )
    assert comando.returncode == 0, comando.stderr


def test_npm_local_y_ruta_explicita(tmp_path, monkeypatch):
    monkeypatch.setattr(entorno.shutil, "which", lambda _: None)
    npm = tmp_path / ".codex-local/npm/node_modules/npm/bin/npm-cli.js"
    npm.parent.mkdir(parents=True)
    npm.write_text("// inventado", encoding="utf-8")
    assert entorno.encontrar_npm(tmp_path / "node", None, tmp_path) == npm.resolve()
    with pytest.raises(ValueError):
        entorno.encontrar_npm(tmp_path / "node", tmp_path / "ausente", tmp_path)


def test_check_no_crea_venv_ni_instala(monkeypatch):
    monkeypatch.setattr(entorno.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(entorno, "ejecutar", lambda *a, **k: pytest.fail("instalación inesperada"))
    assert entorno.main(["--backend", "--check"]) == 0


def test_node_incompatible_no_instala(monkeypatch):
    monkeypatch.setattr(entorno.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(entorno.subprocess, "check_output", lambda *a, **k: "v22.0.0")
    monkeypatch.setattr(entorno, "ejecutar", lambda *a, **k: pytest.fail("instalación inesperada"))
    assert entorno.main(["--frontend", "--node", "node-inventado"]) == 1


def test_fallo_pip_detiene_preparacion(monkeypatch, tmp_path):
    monkeypatch.setattr(entorno.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(entorno.subprocess, "check_output", lambda *a, **k: "3.12")
    python = tmp_path / "python"
    python.touch()
    monkeypatch.setattr(entorno, "python_venv", lambda: python)
    llamadas = []

    def fallar(comando, **kwargs):
        llamadas.append(comando)
        raise subprocess.CalledProcessError(1, comando)

    monkeypatch.setattr(entorno, "ejecutar", fallar)
    assert entorno.main(["--backend"]) == 1
    assert len(llamadas) == 1
    assert llamadas[0][1:] == ["-m", "pip", "install", "-r", "backend/requirements-dev.txt", "-e", "."]


def test_venv_incompatible_no_instala(monkeypatch, tmp_path):
    monkeypatch.setattr(entorno.sys, "version_info", (3, 12, 0))
    python = tmp_path / "python"
    python.touch()
    monkeypatch.setattr(entorno, "python_venv", lambda: python)
    monkeypatch.setattr(entorno.subprocess, "check_output", lambda *a, **k: "3.11")
    monkeypatch.setattr(entorno, "ejecutar", lambda *a, **k: pytest.fail("instalación inesperada"))
    assert entorno.main(["--backend"]) == 1


def test_ejecucion_sin_shell_y_fallo_propagado(monkeypatch, tmp_path):
    def simular(comando, **kwargs):
        assert comando == ["programa", "ruta con espacios"]
        assert kwargs == {"cwd": tmp_path, "env": {"PATH": "inventado"}, "check": True}
        raise subprocess.CalledProcessError(2, comando)

    monkeypatch.setattr(entorno.subprocess, "run", simular)
    with pytest.raises(subprocess.CalledProcessError):
        entorno.ejecutar(["programa", "ruta con espacios"], cwd=tmp_path, env={"PATH": "inventado"})
