"""Prepara desarrollo local sin credenciales ni cambios en la VM (Python 3.12)."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

RAIZ = Path(__file__).resolve().parents[1]


def python_venv(raiz: Path = RAIZ) -> Path:
    return raiz / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def encontrar_npm(node: Path, explicito: Path | None, raiz: Path = RAIZ) -> Path:
    if explicito:
        candidatos = [explicito]
    else:
        candidatos = [
            raiz / ".codex-local/npm/node_modules/npm/bin/npm-cli.js",
            node.parent / "node_modules/npm/bin/npm-cli.js",
            node.parent.parent / "lib/node_modules/npm/bin/npm-cli.js",
        ]
        comando = shutil.which("npm")
        if comando:
            resuelto = Path(comando).resolve()
            if resuelto.suffix == ".js":
                candidatos.append(resuelto)
            candidatos.append(resuelto.parent / "node_modules/npm/bin/npm-cli.js")
    for candidato in candidatos:
        if candidato.is_file():
            return candidato.resolve()
    raise ValueError("No se encontró npm-cli.js. Instala Node 24 con npm o indica --npm-cli RUTA.")


def ejecutar(comando: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    # Sin shell, sin activaciones globales y sin imprimir variables de entorno.
    subprocess.run(comando, cwd=cwd, env=env, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Solo comprueba herramientas; no instala.")
    parser.add_argument("--backend", action="store_true", help="Prepara solo Python.")
    parser.add_argument("--frontend", action="store_true", help="Prepara solo frontend.")
    parser.add_argument("--browser", action="store_true", help="Instala Chromium de Playwright (opcional).")
    parser.add_argument("--node", type=Path, help="Ruta a Node 24 cuando no está en PATH.")
    parser.add_argument("--npm-cli", type=Path, help="Ruta a npm-cli.js cuando npm no está en PATH.")
    args = parser.parse_args(argv)
    backend = args.backend or not args.frontend
    frontend = args.frontend or not args.backend or args.browser
    if sys.version_info[:2] != (3, 12):
        parser.error("Se necesita Python 3.12, igual que CI y la VM.")
    entorno = os.environ.copy()
    entorno["PYTHONUTF8"] = "1"
    try:
        node = npm = None
        if frontend:
            encontrado = str(args.node) if args.node else shutil.which("node")
            if not encontrado:
                raise ValueError("No se encontró Node 24. Usa --node RUTA.")
            node = Path(encontrado).resolve()
            version = subprocess.check_output([str(node), "--version"], text=True).strip()
            if not version.startswith("v24."):
                raise ValueError(f"Se necesita Node 24; se encontró {version}.")
            npm = encontrar_npm(node, args.npm_cli)
            entorno["PATH"] = str(node.parent) + os.pathsep + entorno.get("PATH", "")
        print("Herramientas compatibles. La comprobación no certifica dependencias ni pruebas.")
        if args.check:
            return 0
        python = python_venv()
        if backend:
            if not python.exists():
                ejecutar([sys.executable, "-m", "venv", str(RAIZ / ".venv")], cwd=RAIZ, env=entorno)
            version_python = subprocess.check_output(
                [str(python), "-c", "import sys; print('.'.join(map(str, sys.version_info[:2])))"],
                text=True,
            ).strip()
            if version_python != "3.12":
                raise ValueError("La .venv existente no usa Python 3.12; conserva su contenido y crea un entorno compatible.")
            ejecutar([str(python), "-m", "pip", "install", "-r", "backend/requirements-dev.txt", "-e", "."], cwd=RAIZ, env=entorno)
        if frontend:
            assert node is not None and npm is not None
            ejecutar([str(node), str(npm), "ci", "--ignore-scripts"], cwd=RAIZ / "frontend", env=entorno)
            if args.browser:
                ejecutar([str(node), str(RAIZ / "frontend/node_modules/@playwright/test/cli.js"),
                          "install", "--only-shell", "chromium"], cwd=RAIZ / "frontend", env=entorno)
        print("Entorno preparado. Ejecuta los controles de instrucciones/project-codex.md.")
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"No se pudo preparar el entorno: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
