import { describe, expect, it, vi } from "vitest";
import {
  decidir,
  esMensajeLimpiar,
  esGuardable,
  instalar,
  limpiar,
  nombreCache,
  puedeIrAlCascaron,
  responder,
  type ConfigTrabajador,
} from "./trabajador";

const ORIGEN = "https://finanzas.ejemplo.test";
const PRECACHE = ["/app/", "/app/assets/index-abc123.js", "/app/manifest.webmanifest", "/app/iconos/icono-192.png"];
const LISTA = new Set(PRECACHE);
const CONFIG: ConfigTrabajador = { cache: nombreCache("v2"), precache: PRECACHE };

/** Cache Storage en memoria, con lo mínimo que usa el service worker. */
function cachesFalsas() {
  const cachés = new Map<string, Map<string, Response>>();
  const clave = (x: RequestInfo | URL) =>
    new URL(typeof x === "string" || x instanceof URL ? x : x.url, ORIGEN).toString();
  const abrir = (nombre: string): Cache => {
    if (!cachés.has(nombre)) cachés.set(nombre, new Map());
    const c = cachés.get(nombre)!;
    return {
      put: async (pet: RequestInfo | URL, resp: Response) => void c.set(clave(pet), resp),
      match: async (pet: RequestInfo | URL) => c.get(clave(pet))?.clone(),
      keys: async () => [...c.keys()].map((u) => new Request(u)),
      delete: async (pet: RequestInfo | URL) => c.delete(clave(pet)),
    } as unknown as Cache;
  };
  const almacen = {
    open: async (nombre: string) => abrir(nombre),
    keys: async () => [...cachés.keys()],
    has: async (nombre: string) => cachés.has(nombre),
    delete: async (nombre: string) => cachés.delete(nombre),
  } as unknown as CacheStorage;
  const rutas = (nombre: string) => [...(cachés.get(nombre)?.keys() ?? [])].map((u) => new URL(u).pathname);
  return { almacen, cachés, rutas };
}

const peticion = (ruta: string, extra: RequestInit & { mode?: RequestMode } = {}) => ({
  method: extra.method ?? "GET",
  url: ruta.startsWith("http") ? ruta : ORIGEN + ruta,
  mode: extra.mode ?? "cors",
});

describe("decidir", () => {
  it("la API va siempre directo a la red, también al navegar", () => {
    for (const ruta of ["/api", "/api/sesion", "/api/reporte?mes=2026-08", "/api/movimientos/1"]) {
      expect(decidir(peticion(ruta), ORIGEN, LISTA)).toBe("red");
      expect(decidir(peticion(ruta, { mode: "navigate" }), ORIGEN, LISTA)).toBe("red");
    }
  });

  it("solo GET: lo que cambia datos nunca pasa por la caché", () => {
    for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
      expect(decidir(peticion("/app/assets/index-abc123.js", { method }), ORIGEN, LISTA)).toBe("red");
    }
  });

  it("otro origen, la interfaz de la v1 y lo que no está en la lista van a la red", () => {
    expect(decidir(peticion("https://otro.ejemplo.test/app/assets/index-abc123.js"), ORIGEN, LISTA)).toBe("red");
    expect(decidir(peticion("/login", { mode: "navigate" }), ORIGEN, LISTA)).toBe("red");
    expect(decidir(peticion("/static/estilos.css"), ORIGEN, LISTA)).toBe("red");
    expect(decidir(peticion("/app/assets/otro-zzz.js"), ORIGEN, LISTA)).toBe("red");
    expect(decidir(peticion("/app/sw.js"), ORIGEN, LISTA)).toBe("red");
    // Con parámetros no es el archivo de la lista.
    expect(decidir(peticion("/app/assets/index-abc123.js?x=1"), ORIGEN, LISTA)).toBe("red");
  });

  it("los archivos del cascarón salen de la caché y las pantallas de /app son navegación", () => {
    expect(decidir(peticion("/app/assets/index-abc123.js"), ORIGEN, LISTA)).toBe("cascaron");
    expect(decidir(peticion("/app/iconos/icono-192.png"), ORIGEN, LISTA)).toBe("cascaron");
    expect(decidir(peticion("/app/movimientos?mes=2026-08", { mode: "navigate" }), ORIGEN, LISTA)).toBe(
      "navegacion",
    );
  });
});

describe("puedeIrAlCascaron y esGuardable", () => {
  it("nada de /api ni fuera de /app", () => {
    expect(puedeIrAlCascaron("/app/assets/a.js")).toBe(true);
    expect(puedeIrAlCascaron("/api/sesion")).toBe(false);
    expect(puedeIrAlCascaron("/login")).toBe(false);
    expect(puedeIrAlCascaron("/app/sw.js")).toBe(false);
  });

  it("solo respuestas 200 que no son JSON (salvo el manifest)", () => {
    expect(esGuardable(new Response("x", { headers: { "content-type": "text/javascript" } }))).toBe(true);
    expect(esGuardable(new Response("{}", { headers: { "content-type": "application/manifest+json" } }))).toBe(
      true,
    );
    expect(esGuardable(new Response("{}", { headers: { "content-type": "application/json" } }))).toBe(false);
    expect(esGuardable(new Response("no", { status: 404 }))).toBe(false);
    expect(esGuardable(new Response("x", { status: 503 }))).toBe(false);
  });
});

describe("instalar", () => {
  it("guarda exactamente la lista, pedida sin cookies", async () => {
    const { almacen, rutas } = cachesFalsas();
    const pedir = vi.fn(async (_: RequestInfo | URL) => new Response("x", { headers: { "content-type": "text/plain" } }));
    await instalar(CONFIG, almacen, pedir as unknown as typeof fetch, ORIGEN);
    expect(rutas(CONFIG.cache).sort()).toEqual([...PRECACHE].sort());
    for (const [pet] of pedir.mock.calls) {
      const r = pet as Request;
      expect(r.credentials).toBe("omit");
      expect(r.cache).toBe("reload");
    }
  });

  it("si una ruta de la lista es de la API, no instala nada", async () => {
    const { almacen } = cachesFalsas();
    const pedir = vi.fn(async () => new Response("x"));
    await expect(
      instalar({ cache: "c", precache: ["/app/", "/api/reporte"] }, almacen, pedir as unknown as typeof fetch, ORIGEN),
    ).rejects.toThrow(/fuera del cascarón/);
  });

  it("si el servidor no responde 200, la instalación falla", async () => {
    const { almacen } = cachesFalsas();
    const pedir = vi.fn(async () => new Response("no", { status: 404 }));
    await expect(instalar(CONFIG, almacen, pedir as unknown as typeof fetch, ORIGEN)).rejects.toThrow();
  });

  it("si falla a mitad, borra la caché nueva a medias y relanza el error", async () => {
    const { almacen, cachés } = cachesFalsas();
    const vieja = nombreCache("v1");
    await (await almacen.open(vieja)).put("/app/", new Response("anterior"));
    let llamadas = 0;
    const pedir = vi.fn(async () => {
      llamadas += 1;
      if (llamadas === 3) throw new TypeError("Failed to fetch");
      return new Response("x", { headers: { "content-type": "text/plain" } });
    });
    await expect(instalar(CONFIG, almacen, pedir as unknown as typeof fetch, ORIGEN)).rejects.toThrow(
      "Failed to fetch",
    );
    // La nueva no queda; la de la versión anterior sigue intacta.
    expect([...cachés.keys()]).toEqual([vieja]);
  });
});

describe("esMensajeLimpiar", () => {
  const limpiarMsg = { tipo: "limpiar" };
  it("acepta solo el mensaje de limpiar desde este mismo origen", () => {
    expect(esMensajeLimpiar({ origin: ORIGEN, data: limpiarMsg }, ORIGEN)).toBe(true);
  });
  it("ignora un origen vacío o ajeno", () => {
    expect(esMensajeLimpiar({ origin: "", data: limpiarMsg }, ORIGEN)).toBe(false);
    expect(esMensajeLimpiar({ origin: "https://otro.ejemplo.test", data: limpiarMsg }, ORIGEN)).toBe(false);
  });
  it("ignora otros mensajes", () => {
    for (const data of [null, "limpiar", { tipo: "otro" }, {}]) {
      expect(esMensajeLimpiar({ origin: ORIGEN, data }, ORIGEN)).toBe(false);
    }
  });
});

describe("limpiar", () => {
  it("borra las versiones viejas y lo que no es del cascarón actual", async () => {
    const { almacen, cachés, rutas } = cachesFalsas();
    const vieja = await almacen.open(nombreCache("v1"));
    await vieja.put("/app/assets/index-viejo.js", new Response("x"));
    const ajena = await almacen.open("otra-cosa");
    await ajena.put("/api/reporte", new Response("{}"));
    const actual = await almacen.open(CONFIG.cache);
    await actual.put("/app/", new Response("<html>"));
    await actual.put("/api/movimientos", new Response("{}"));
    await limpiar(CONFIG, almacen);
    expect([...cachés.keys()]).toEqual([CONFIG.cache]);
    expect(rutas(CONFIG.cache)).toEqual(["/app/"]);
  });

  it("sin caché actual no falla", async () => {
    const { almacen, cachés } = cachesFalsas();
    await almacen.open(nombreCache("v1"));
    await limpiar(CONFIG, almacen);
    expect(cachés.size).toBe(0);
  });
});

describe("responder", () => {
  const preparar = async () => {
    const falsas = cachesFalsas();
    const c = await falsas.almacen.open(CONFIG.cache);
    await c.put("/app/", new Response("indice"));
    await c.put("/app/assets/index-abc123.js", new Response("js guardado"));
    return falsas;
  };

  it("la API no se responde (null) y nunca se guarda", async () => {
    const { almacen, rutas } = await preparar();
    const pedir = vi.fn();
    expect(
      responder(new Request(ORIGEN + "/api/reporte"), CONFIG, almacen, pedir as unknown as typeof fetch, ORIGEN, LISTA),
    ).toBeNull();
    expect(pedir).not.toHaveBeenCalled();
    expect(rutas(CONFIG.cache)).not.toContain("/api/reporte");
  });

  it("un archivo del cascarón sale de la caché; si falta, de la red sin guardarlo", async () => {
    const { almacen, rutas } = await preparar();
    const pedir = vi.fn(async () => new Response("de la red"));
    const r = await responder(
      new Request(ORIGEN + "/app/assets/index-abc123.js"),
      CONFIG,
      almacen,
      pedir as unknown as typeof fetch,
      ORIGEN,
      LISTA,
    );
    expect(await r!.text()).toBe("js guardado");
    expect(pedir).not.toHaveBeenCalled();
    const r2 = await responder(
      new Request(ORIGEN + "/app/manifest.webmanifest"),
      CONFIG,
      almacen,
      pedir as unknown as typeof fetch,
      ORIGEN,
      LISTA,
    );
    expect(await r2!.text()).toBe("de la red");
    expect(rutas(CONFIG.cache)).not.toContain("/app/manifest.webmanifest");
  });

  it("al navegar va a la red y no guarda la respuesta", async () => {
    const { almacen, rutas } = await preparar();
    const pedir = vi.fn(async () => new Response("pantalla"));
    const nav = { method: "GET", url: ORIGEN + "/app/movimientos", mode: "navigate" } as Request;
    const r = await responder(nav, CONFIG, almacen, pedir as unknown as typeof fetch, ORIGEN, LISTA);
    expect(await r!.text()).toBe("pantalla");
    expect(rutas(CONFIG.cache).sort()).toEqual(["/app/", "/app/assets/index-abc123.js"]);
  });

  it("sin conexión, al navegar devuelve el índice guardado (la app muestra «sin conexión»)", async () => {
    const { almacen } = await preparar();
    const pedir = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const nav = { method: "GET", url: ORIGEN + "/app/saldo", mode: "navigate" } as Request;
    const r = await responder(nav, CONFIG, almacen, pedir as unknown as typeof fetch, ORIGEN, LISTA);
    expect(await r!.text()).toBe("indice");
  });

  it("sin conexión y sin índice guardado, el error sigue (el navegador muestra el suyo)", async () => {
    const { almacen } = cachesFalsas();
    const pedir = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const nav = { method: "GET", url: ORIGEN + "/app/", mode: "navigate" } as Request;
    await expect(
      responder(nav, CONFIG, almacen, pedir as unknown as typeof fetch, ORIGEN, LISTA),
    ).rejects.toThrow(TypeError);
  });
});
