import { describe, expect, it } from "vitest";
import { esSeccionActual, SECCIONES } from "@/app/navegacion/secciones";

describe("esSeccionActual", () => {
  it("Inicio solo es actual en la raíz", () => {
    expect(esSeccionActual("/", "/")).toBe(true);
    expect(esSeccionActual("/", "")).toBe(true);
    expect(esSeccionActual("/", "/saldo")).toBe(false);
  });

  it("una sección es actual en su ruta y en sus subrutas", () => {
    expect(esSeccionActual("/saldo", "/saldo")).toBe(true);
    expect(esSeccionActual("/saldo", "/saldo/")).toBe(true);
    expect(esSeccionActual("/saldo", "/saldo/detalle")).toBe(true);
  });

  it("no confunde rutas que empiezan igual", () => {
    expect(esSeccionActual("/mas", "/mascotas")).toBe(false);
    expect(esSeccionActual("/saldo", "/")).toBe(false);
  });
});

describe("SECCIONES", () => {
  it("la barra inferior tiene 5 elementos y la lateral 5 (SISTEMA.md)", () => {
    expect(SECCIONES.filter((s) => s.enInferior).map((s) => s.nombreCorto)).toEqual([
      "Inicio",
      "Movimientos",
      "Saldo",
      "Categorías",
      "Más",
    ]);
    expect(SECCIONES.filter((s) => s.enLateral).map((s) => s.nombre)).toEqual([
      "Inicio",
      "Movimientos",
      "Saldo",
      "Categorías y reglas",
      "No reconocidos",
    ]);
  });
});
