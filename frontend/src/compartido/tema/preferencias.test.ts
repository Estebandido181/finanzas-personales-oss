import { beforeEach, describe, expect, it } from "vitest";
import { aplicarTema, CLAVE_TEMA, elegirTema, leerTema, reiniciarTemaEnMemoria } from "@/compartido/tema/preferencias";

beforeEach(() => reiniciarTemaEnMemoria());

describe("apariencia", () => {
  it("por defecto sigue al sistema", () => {
    expect(leerTema()).toBe("sistema");
  });

  it("claro y oscuro se guardan y se ponen en <html>", () => {
    elegirTema("oscuro");
    expect(localStorage.getItem(CLAVE_TEMA)).toBe("oscuro");
    expect(document.documentElement.dataset.tema).toBe("oscuro");
    expect(leerTema()).toBe("oscuro");
    elegirTema("claro");
    expect(document.documentElement.dataset.tema).toBe("claro");
  });

  it("«Sistema» no se guarda y quita el atributo", () => {
    elegirTema("oscuro");
    elegirTema("sistema");
    expect(localStorage.getItem(CLAVE_TEMA)).toBeNull();
    expect(document.documentElement.hasAttribute("data-tema")).toBe(false);
  });

  it("un valor raro guardado vale como «Sistema»", () => {
    localStorage.setItem(CLAVE_TEMA, "morado");
    expect(leerTema()).toBe("sistema");
  });

  it("solo guarda la preferencia: una clave en localStorage", () => {
    elegirTema("claro");
    expect(Object.keys(localStorage)).toEqual([CLAVE_TEMA]);
  });

  it("aplicarTema acepta otra raíz", () => {
    const raiz = document.createElement("div");
    aplicarTema("oscuro", raiz);
    expect(raiz.getAttribute("data-tema")).toBe("oscuro");
    aplicarTema("sistema", raiz);
    expect(raiz.hasAttribute("data-tema")).toBe(false);
  });
});
