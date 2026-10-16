import { describe, expect, it } from "vitest";
import { COLORES, componenteIcono, estiloCategoria, ICONOS, nombreColor, nombreIcono, type ConEstilo } from "./categorias";

describe("categorías", () => {
  it("el color y el ícono salen de las claves de la API", () => {
    expect(estiloCategoria({ color: "cat-mercado", icono: "shopping-basket" }).color).toBe(
      "[--c:var(--cat-mercado)]",
    );
    // Una categoría propia (ítem 15): cualquier par de la paleta.
    const propia = estiloCategoria({ color: "cat-antojos", icono: "heart-pulse" });
    expect(propia.color).toBe("[--c:var(--cat-antojos)]");
    expect(propia.icono).toBe(componenteIcono("heart-pulse"));
    expect(propia.vacia).toBe(false);
  });

  it("una clave desconocida se pinta como «Otros»", () => {
    const rara = { color: "toString", icono: "constructor" } as unknown as ConEstilo;
    expect(estiloCategoria(rara).color).toBe("[--c:var(--cat-otros)]");
    expect(estiloCategoria(rara).icono).toBe(componenteIcono("shapes"));
  });

  it("«Sin categorizar» (sin categoría) es hueca", () => {
    expect(estiloCategoria(null).vacia).toBe(true);
    expect(estiloCategoria(undefined).vacia).toBe(true);
  });

  it("la paleta y los íconos son los 12 de SISTEMA.md, con nombre", () => {
    expect(COLORES).toHaveLength(12);
    expect(ICONOS).toHaveLength(12);
    expect(nombreColor("cat-salud")).toBe("Vino");
    expect(nombreIcono("coins")).toBe("Monedas");
  });
});
