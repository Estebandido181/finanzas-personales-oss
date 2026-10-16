// @vitest-environment node
import { beforeEach, afterEach, afterAll, expect, it, vi } from "vitest";
import {
  ArchivosCompartidos,
  MAX_ARCHIVO_COMPARTIDO,
  recibirCompartido,
} from "./compartir";
// El preparador común limpia DOM/localStorage; esta prueba usa Fetch/FormData
// nativos de Node para verificar multipart sin las conversiones de jsdom.
beforeEach(() => {
  vi.stubGlobal("localStorage", { clear() {} });
  vi.stubGlobal("document", { documentElement: { removeAttribute() {} } });
});
afterEach(() => vi.useRealTimers());
afterAll(() => vi.unstubAllGlobals());
const peticion = (datos: FormData) =>
  new Request("https://finanzas.example/app/compartir", {
    method: "POST",
    body: datos,
  });
it("recibe el multipart limitado sin enviar el original a la red y lo entrega al documento una vez", async () => {
  vi.useFakeTimers();
  const memoria = new ArchivosCompartidos();
  const datos = new FormData();
  datos.append(
    "archivo",
    new File(["Excel inventado"], "reporte-EJEMPLO.xlsx"),
  );
  expect(await recibirCompartido(peticion(datos), "documento-a", memoria)).toBe(
    true,
  );
  expect(memoria.consumir("documento-b")).toBeNull();
  expect(await memoria.consumir("documento-a")?.text()).toBe("Excel inventado");
  expect(memoria.consumir("documento-a")).toBeNull();
});
it("rechaza múltiples archivos y nombres de campos inesperados", async () => {
  const memoria = new ArchivosCompartidos();
  const datos = new FormData();
  datos.append("archivo", new File(["x"], "ejemplo-a.xlsx"));
  datos.append("archivo", new File(["y"], "ejemplo-b.xlsx"));
  expect(await recibirCompartido(peticion(datos), "a", memoria)).toBe(false);
  const otro = new FormData();
  otro.append("archivo", new File(["x"], "ejemplo.xlsx"));
  otro.append("otra", new File(["y"], "ejemplo-otra.xlsx"));
  expect(await recibirCompartido(peticion(otro), "a", memoria)).toBe(false);
  expect(memoria.consumir("a")).toBeNull();
});
it("limita bytes reales aunque el Content-Length falte o mienta", async () => {
  const memoria = new ArchivosCompartidos();
  const envio = new Request("https://finanzas.example/app/compartir", {
    method: "POST",
    body: new Uint8Array(MAX_ARCHIVO_COMPARTIDO + 80 * 1024),
    headers: {
      "Content-Type": "multipart/form-data; boundary=ejemplo",
      "Content-Length": "10",
    },
  });
  expect(await recibirCompartido(envio, "a", memoria)).toBe(false);
  expect(memoria.consumir("a")).toBeNull();
});
it("rechaza Content-Length anunciado excesivo antes de consumir y formulario mal formado", async () => {
  const memoria = new ArchivosCompartidos();
  const datos = new FormData();
  datos.append("archivo", new File(["x"], "ejemplo.xlsx"));
  const envio = peticion(datos);
  envio.headers.set("Content-Length", String(10 * MAX_ARCHIVO_COMPARTIDO));
  expect(await recibirCompartido(envio, "a", memoria)).toBe(false);
  expect(envio.bodyUsed).toBe(false);
  const roto = new Request("https://finanzas.example/app/compartir", {
    method: "POST",
    body: "archivo roto",
    headers: { "Content-Type": "multipart/form-data; boundary=ejemplo" },
  });
  expect(await recibirCompartido(roto, "a", memoria)).toBe(false);
});
