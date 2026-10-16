import { readdirSync, readFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import ts from "typescript";

const raiz = resolve(import.meta.dirname, "..");
function archivos(carpeta: string): string[] {
  return readdirSync(carpeta, { withFileTypes: true }).flatMap((entrada) => {
    const ruta = resolve(carpeta, entrada.name);
    return entrada.isDirectory() ? archivos(ruta) : /\.tsx?$/.test(ruta) ? [ruta] : [];
  });
}

/** Comprueba imports estáticos, reexportaciones y cargas diferidas; también
 * resuelve rutas relativas para que cambiar el alias no eluda la frontera. */
function dependencias(ruta: string): string[] {
  const fuente = ts.createSourceFile(ruta, readFileSync(ruta, "utf8"), ts.ScriptTarget.Latest, true);
  const resultados: string[] = [];
  function visitar(nodo: ts.Node) {
    let literal: ts.Expression | undefined;
    if (ts.isImportDeclaration(nodo) || ts.isExportDeclaration(nodo)) literal = nodo.moduleSpecifier;
    if (ts.isCallExpression(nodo) && nodo.expression.kind === ts.SyntaxKind.ImportKeyword) literal = nodo.arguments[0];
    if (literal && ts.isStringLiteral(literal)) {
      const nombre = literal.text;
      if (nombre.startsWith("@/")) resultados.push(nombre.slice(2));
      else if (nombre.startsWith(".")) resultados.push(relative(raiz, resolve(dirname(ruta), nombre)).replaceAll("\\", "/"));
    }
    ts.forEachChild(nodo, visitar);
  }
  visitar(fuente);
  return resultados;
}

describe("fronteras del frontend", () => {
  it("compartido no depende de funcionalidades ni composición", () => {
    const prohibidas = archivos(resolve(raiz, "compartido"))
      .filter((ruta) => !ruta.includes(".test."))
      .flatMap((ruta) => dependencias(ruta).filter((nombre) => /^(funcionalidades|app)\//.test(nombre)).map((nombre) => `${relative(raiz, ruta)} → ${nombre}`));
    expect(prohibidas).toEqual([]);
  });

  it("sesión no conoce Inicio ni el controlador de sincronización", () => {
    const prohibidas = archivos(resolve(raiz, "funcionalidades/sesion"))
      .filter((ruta) => !ruta.includes(".test."))
      .flatMap(dependencias)
      .filter((nombre) => /^funcionalidades\/(inicio|sincronizacion)\//.test(nombre));
    expect(prohibidas).toEqual([]);
  });

  it("los controladores de funcionalidades no importan composición", () => {
    const prohibidas = archivos(resolve(raiz, "funcionalidades"))
      .filter((ruta) => !ruta.includes(".test."))
      .flatMap(dependencias)
      .filter((nombre) => nombre.startsWith("app/"));
    expect(prohibidas).toEqual([]);
  });
});
