"""Comprueba fronteras y ciclos Python sin importar ni ejecutar la aplicación."""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from importlib.util import resolve_name
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[1]
COMPATIBILIDAD = frozenset(f"finanzas.{n}" for n in (
    "db", "saldo", "categorizacion", "importacion", "gestion_importaciones", "arranque",
    "inicio", "reporte", "sincronizacion", "gmail", "extractor", "excel_bancolombia",
    "tokens_ingreso", "tokens_bancarios", "deshacer", "descartes", "comprobacion_saldo", "elecciones_banco",
))


@dataclass(frozen=True)
class Dependencia:
    origen: str
    destino: str
    linea: int
    simbolos: tuple[str, ...] = ()


def modulos(raiz: Path) -> dict[str, Path]:
    resultado = {}
    paquete = raiz / "backend" / "finanzas"
    for ruta in sorted(paquete.rglob("*.py")):
        partes = ruta.relative_to(raiz / "backend").with_suffix("").parts
        nombre = ".".join(partes[:-1] if partes[-1] == "__init__" else partes)
        resultado[nombre] = ruta
    return resultado


def dependencias(origen: str, fuente: str, nombres: set[str], paquete: bool = False) -> list[Dependencia]:
    """Incluye imports diferidos y resuelve nombres relativos y módulos del from."""
    resultado = []
    base = origen if paquete else origen.rpartition(".")[0]
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Import):
            resultado.extend(Dependencia(origen, a.name, nodo.lineno) for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            destino = resolve_name("." * nodo.level + (nodo.module or ""), base) if nodo.level else nodo.module or ""
            # Un nombre del from puede ser un submódulo, no un símbolo de la fachada.
            simbolos = []
            for a in nodo.names:
                submodulo = destino + "." + a.name
                if submodulo in nombres:
                    resultado.append(Dependencia(origen, submodulo, nodo.lineno))
                else:
                    simbolos.append(a.name)
            if simbolos:
                resultado.append(Dependencia(origen, destino, nodo.lineno, tuple(simbolos)))
    return resultado


def propietario(nombre: str) -> str | None:
    partes = nombre.split(".")
    return partes[2] if len(partes) >= 3 and partes[:2] == ["finanzas", "modulos"] else None


def es_puro(nombre: str) -> bool:
    if nombre.startswith("finanzas.flujos."):
        return True
    if not propietario(nombre) or ".adaptadores." in nombre or nombre.endswith("_sqlite"):
        return False
    return nombre.rsplit(".", 1)[-1] not in {"registro_sqlite", "repositorio_sqlite"}


def violaciones(aristas: list[Dependencia]) -> list[str]:
    errores = []
    for d in aristas:
        o, t = d.origen, d.destino
        interno = o.startswith(("finanzas.modulos.", "finanzas.flujos.", "finanzas.infraestructura.", "finanzas.bootstrap.", "finanzas.api."))
        motivo = None
        if interno and t in COMPATIBILIDAD:
            motivo = "consumidor interno de compatibilidad"
        elif o.startswith("finanzas.modulos.") and t.startswith(("finanzas.bootstrap", "finanzas.api", "finanzas.web", "finanzas.operacion")):
            motivo = "módulo depende del perímetro o composición"
        elif es_puro(o) and t.startswith(("sqlalchemy", "fastapi", "starlette", "google", "finanzas.infraestructura", "finanzas.bootstrap")):
            motivo = "dominio/aplicación conoce infraestructura"
        elif es_puro(o) and (".adaptadores." in t or t.endswith("_sqlite")):
            motivo = "dominio/aplicación conoce adaptador"
        elif o.startswith("finanzas.infraestructura.") and t.startswith(("finanzas.modulos", "finanzas.flujos", "finanzas.api", "finanzas.bootstrap", "finanzas.operacion", "finanzas.migrar")):
            motivo = "infraestructura genérica depende de un participante"
        elif propietario(o) and propietario(t) and propietario(o) != propietario(t) and not t.endswith(".publico"):
            motivo = "acceso entre módulos fuera del contrato público"
        elif o.startswith("finanzas.flujos.") and propietario(t) and not t.endswith(".publico"):
            motivo = "flujo accede fuera del contrato público"
        elif propietario(o) and propietario(t) != propietario(o) and any(s.startswith("_") for s in d.simbolos):
            motivo = "símbolo privado ajeno"
        if motivo:
            errores.append(f"{o}:{d.linea} -> {t}: {motivo}")
    return errores


def ciclos(aristas: list[Dependencia], nombres: set[str]) -> list[list[str]]:
    grafo = {n: set() for n in nombres}
    for d in aristas:
        if d.destino in nombres:
            grafo[d.origen].add(d.destino)
    activos, terminados, pila, encontrados = set(), set(), [], []

    def recorrer(n):
        if n in terminados:
            return
        if n in activos:
            encontrados.append(pila[pila.index(n):] + [n])
            return
        activos.add(n)
        pila.append(n)
        for hijo in sorted(grafo[n]):
            recorrer(hijo)
        pila.pop()
        activos.remove(n)
        terminados.add(n)

    for n in sorted(nombres):
        recorrer(n)
    return encontrados


def revisar(raiz: Path = RAIZ) -> dict:
    rutas = modulos(raiz)
    nombres = set(rutas)
    aristas = [d for n, p in rutas.items() for d in dependencias(n, p.read_text(encoding="utf-8"), nombres, p.name == "__init__.py")]
    return {"modulos_python": len(nombres), "dependencias": len(aristas),
            "violaciones": violaciones(aristas), "ciclos": ciclos(aristas, nombres)}


if __name__ == "__main__":
    resultado = revisar()
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    sys.exit(bool(resultado["violaciones"] or resultado["ciclos"]))
