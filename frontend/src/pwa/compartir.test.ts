import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ArchivosCompartidos,
  esCompartir,
  MAX_ARCHIVO_COMPARTIDO,
  MIME_EXCEL,
} from "./compartir";
afterEach(() => vi.useRealTimers());
describe("archivo compartido solo en memoria", () => {
  it("solo la pestaña destinataria lo puede consumir, una vez", () => {
    vi.useFakeTimers();
    const memoria = new ArchivosCompartidos();
    const archivo = new File(["ejemplo inventado"], "reporte-EJEMPLO.xlsx", {
      type: MIME_EXCEL,
    });
    expect(memoria.guardar("pestaña-a", archivo, 1000)).toBe(true);
    expect(memoria.consumir("pestaña-b", 2000)).toBeNull();
    expect(memoria.consumir("pestaña-a", 2000)).toBe(archivo);
    expect(memoria.consumir("pestaña-a", 2001)).toBeNull();
  });
  it("vence, se limpia al salir y se reemplaza sin conservar el original anterior", () => {
    vi.useFakeTimers();
    const memoria = new ArchivosCompartidos();
    const archivo = new File(["x"], "reporte-EJEMPLO.xlsx");
    memoria.guardar("a", archivo, 1000);
    expect(memoria.consumir("a", 901000)).toBeNull();
    memoria.guardar("a", archivo);
    memoria.limpiar();
    expect(memoria.consumir("a")).toBeNull();
    memoria.guardar("a", archivo);
    memoria.guardar("b", archivo);
    expect(memoria.consumir("a")).toBeNull();
    vi.advanceTimersByTime(15 * 60 * 1000);
    expect(memoria.consumir("b")).toBeNull();
  });
  it("rechaza sin pestaña, otros formatos, vacío y tamaño excesivo", () => {
    const memoria = new ArchivosCompartidos();
    expect(memoria.guardar("", new File(["x"], "ejemplo.xlsx"))).toBe(false);
    expect(memoria.guardar("a", new File(["x"], "ejemplo.pdf"))).toBe(false);
    expect(memoria.guardar("a", new File([], "ejemplo.xlsx"))).toBe(false);
    expect(
      memoria.guardar(
        "a",
        new File([new Uint8Array(MAX_ARCHIVO_COMPARTIDO + 1)], "ejemplo.xlsx"),
      ),
    ).toBe(false);
  });
  it("intercepta solo el POST propio del share target", () => {
    const origen = "https://finanzas.example";
    expect(
      esCompartir({ method: "POST", url: origen + "/app/compartir" }, origen),
    ).toBe(true);
    expect(
      esCompartir({ method: "GET", url: origen + "/app/compartir" }, origen),
    ).toBe(false);
    expect(
      esCompartir(
        { method: "POST", url: "https://otro.example/app/compartir" },
        origen,
      ),
    ).toBe(false);
  });
});
