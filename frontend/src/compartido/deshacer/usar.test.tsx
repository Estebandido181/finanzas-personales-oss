import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { guardarTokenCsrf } from "@/compartido/http/cliente";
import { simularApi, TOKEN_INVENTADO, type Manejador, type Respuesta } from "@/pruebas/api-simulada";
import { restaurar, useDeshacer } from "@/compartido/deshacer/usar";

const ok = (cuerpo: unknown): Respuesta => ({ estado: 200, cuerpo });
const HECHO = { que: "regla", id: 7, saldo_centavos: null };

function montar(rutas: Record<string, Manejador | Respuesta> = {}, alRestaurar = vi.fn()) {
  const api = simularApi({ "POST /api/deshacer": ok(HECHO), ...rutas });
  const hook = renderHook(() => useDeshacer(api.cliente, alRestaurar));
  return { ...api, ...hook, alRestaurar };
}

const OFERTA = {
  deshacer: { token: "token-deshacer-inventado", segundos: 10 },
  texto: "Regla borrada.",
  restaurado: () => "Regla restaurada.",
};

beforeEach(() => {
  guardarTokenCsrf(TOKEN_INVENTADO);
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  guardarTokenCsrf(null);
});

describe("restaurar", () => {
  it("envía el token con el CSRF y devuelve lo restaurado", async () => {
    vi.useRealTimers();
    const { cliente, peticiones } = simularApi({ "POST /api/deshacer": ok(HECHO) });
    expect(await restaurar(cliente, "tok")).toEqual({ tipo: "ok", datos: HECHO });
    expect(peticiones[0]!.headers.get("X-CSRF-Token")).toBe(TOKEN_INVENTADO);
    expect(await peticiones[0]!.json()).toEqual({ token: "tok" });
  });

  it("410 y 409: el texto que manda la API; sin él, uno propio", async () => {
    vi.useRealTimers();
    const api = (estado: number, cuerpo?: unknown) => simularApi({ "POST /api/deshacer": { estado, cuerpo } }).cliente;
    expect(await restaurar(api(410, { detalle: "Pasó el tiempo." }), "t")).toEqual({
      tipo: "error",
      texto: "Pasó el tiempo.",
    });
    expect(await restaurar(api(410), "t")).toEqual({
      tipo: "error",
      texto: "Ya no se puede deshacer: pasó el tiempo o ya se deshizo.",
    });
    expect(await restaurar(api(409), "t")).toEqual({
      tipo: "error",
      texto: "No se puede deshacer: algo cambió mientras tanto.",
    });
  });

  it("sin red, lo dice", async () => {
    vi.useRealTimers();
    const { cliente } = simularApi({ "POST /api/deshacer": "sin-red" });
    expect(await restaurar(cliente, "t")).toEqual({
      tipo: "error",
      texto: "No hay conexión con la app. Revisa tu internet y vuelve a intentarlo.",
    });
  });
});

describe("useDeshacer", () => {
  it("ofrece Deshacer solo los segundos que mandó el servidor", () => {
    const { result } = montar();
    act(() => result.current.ofrecer(OFERTA));
    expect(result.current.estado).toEqual({ fase: "oferta", texto: "Regla borrada." });
    act(() => void vi.advanceTimersByTime(9_999));
    expect(result.current.estado?.fase).toBe("oferta");
    act(() => void vi.advanceTimersByTime(1));
    expect(result.current.estado).toBeNull();
  });

  it("deshacer restaura, dice qué pasó y avisa para recargar; el token no se reutiliza", async () => {
    vi.useRealTimers();
    const { result, alRestaurar, peticiones } = montar();
    act(() => result.current.ofrecer(OFERTA));
    await act(async () => result.current.deshacer());
    expect(result.current.estado).toEqual({ fase: "hecho", texto: "Regla restaurada." });
    expect(alRestaurar).toHaveBeenCalledWith(HECHO);
    // Un segundo toque no envía otra petición.
    await act(async () => result.current.deshacer());
    expect(peticiones.filter((p) => new URL(p.url).pathname === "/api/deshacer")).toHaveLength(1);
  });

  it("mientras se deshace, el aviso sigue (deshaciendo) aunque pase el tiempo", async () => {
    vi.useRealTimers();
    let responder: (r: Respuesta) => void = () => {};
    const { result } = montar({ "POST /api/deshacer": () => new Promise<Respuesta>((r) => (responder = r)) });
    act(() => result.current.ofrecer({ ...OFERTA, deshacer: { ...OFERTA.deshacer, segundos: 0.05 } }));
    act(() => void result.current.deshacer());
    await waitFor(() => expect(result.current.estado?.fase).toBe("deshaciendo"));
    await new Promise((r) => setTimeout(r, 120));
    expect(result.current.estado?.fase).toBe("deshaciendo");
    await act(async () => responder(ok(HECHO)));
    expect(result.current.estado?.fase).toBe("hecho");
  });

  it("un 409 se muestra como error con el motivo de la API y vuelve a leer la pantalla (D44)", async () => {
    vi.useRealTimers();
    const detalle = "No se puede deshacer: ya hay una regla con esas mismas condiciones.";
    const { result, alRestaurar } = montar({ "POST /api/deshacer": { estado: 409, cuerpo: { detalle } } });
    act(() => result.current.ofrecer(OFERTA));
    await act(async () => result.current.deshacer());
    expect(result.current.estado).toEqual({ fase: "error", texto: detalle });
    // Otra pestaña pudo cambiar algo: se muestra lo que hay en el servidor.
    expect(alRestaurar).toHaveBeenCalledTimes(1);
  });

  it("un 410 también vuelve a leer la pantalla", async () => {
    vi.useRealTimers();
    const { result, alRestaurar } = montar({ "POST /api/deshacer": { estado: 410, cuerpo: {} } });
    act(() => result.current.ofrecer(OFERTA));
    await act(async () => result.current.deshacer());
    expect(result.current.estado?.fase).toBe("error");
    expect(alRestaurar).toHaveBeenCalledTimes(1);
  });

  it("pausar detiene la cuenta y reanudar sigue con lo que faltaba", () => {
    const { result } = montar();
    act(() => result.current.ofrecer(OFERTA));
    act(() => void vi.advanceTimersByTime(6_000));
    act(() => result.current.pausar());
    // Aunque pase mucho tiempo, el aviso sigue.
    act(() => void vi.advanceTimersByTime(60_000));
    expect(result.current.estado?.fase).toBe("oferta");
    act(() => result.current.reanudar());
    act(() => void vi.advanceTimersByTime(3_999));
    expect(result.current.estado?.fase).toBe("oferta");
    act(() => void vi.advanceTimersByTime(1));
    expect(result.current.estado).toBeNull();
  });

  it("ofrecer otro borrado reemplaza al anterior: solo vale el último token", async () => {
    vi.useRealTimers();
    const { result, peticiones } = montar();
    act(() => result.current.ofrecer({ ...OFERTA, deshacer: { token: "uno", segundos: 10 } }));
    act(() => result.current.ofrecer({ ...OFERTA, deshacer: { token: "dos", segundos: 10 }, texto: "Otra." }));
    await act(async () => result.current.deshacer());
    expect(await peticiones[0]!.json()).toEqual({ token: "dos" });
  });

  it("limpiar quita el aviso y el token", async () => {
    vi.useRealTimers();
    const { result, peticiones } = montar();
    act(() => result.current.ofrecer(OFERTA));
    act(() => result.current.limpiar());
    expect(result.current.estado).toBeNull();
    await act(async () => result.current.deshacer());
    expect(peticiones).toHaveLength(0);
  });

  it("el token vive solo en memoria: nada en localStorage ni sessionStorage", () => {
    const { result } = montar();
    act(() => result.current.ofrecer(OFERTA));
    for (const almacen of [localStorage, sessionStorage]) {
      expect(JSON.stringify({ ...almacen })).not.toContain("token-deshacer-inventado");
      expect(almacen.length).toBe(0);
    }
  });

  it("un error ajeno (409 al borrar) se muestra en el mismo aviso y quita el token", async () => {
    vi.useRealTimers();
    const { result, peticiones } = montar();
    act(() => result.current.ofrecer(OFERTA));
    act(() => result.current.mostrarError("No se puede borrar."));
    expect(result.current.estado).toEqual({ fase: "error", texto: "No se puede borrar." });
    await act(async () => result.current.deshacer());
    expect(peticiones).toHaveLength(0);
  });
});
