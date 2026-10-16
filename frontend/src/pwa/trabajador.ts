/**
 * Lógica del service worker (ítem 18), separada de sus eventos para poder
 * probarla con Vitest. `sw.ts` solo conecta estos pasos a install, activate,
 * fetch y message.
 *
 * Regla de seguridad: la caché solo guarda el **cascarón estático** de esta
 * versión, una lista cerrada que se arma al compilar (`plugin-sw.ts`): los
 * archivos con hash de `assets/` (JS, CSS, fuentes, texturas), los íconos, el
 * manifest, `tema-inicial.js` y el índice `/app/` (el HTML vacío, sin datos).
 *
 * - Solo se escribe en la caché al instalar, y solo esa lista, pedida **sin
 *   cookies** (`credentials: "omit"`): nada de lo guardado pudo depender de la
 *   sesión. Ninguna respuesta que pase por `fetch` se guarda.
 * - `/api` nunca pasa por aquí: el service worker no la toca y va directo a
 *   la red (con su `no-store`), así que los datos financieros nunca quedan en
 *   Cache Storage.
 * - Sin conexión, una navegación recibe el índice guardado: la app arranca,
 *   GET /api/sesion falla y muestra su pantalla "No hay conexión…", sin datos.
 */

export const PREFIJO_CACHE = "finanzas-cascaron-";
/** Mensaje que manda la página al cerrar sesión (`registrar.ts`). */
export const MENSAJE_LIMPIAR = "limpiar";
/** El índice se guarda con esta dirección (el servidor no sirve /app/index.html). */
export const RUTA_INDICE = "/app/";
const PREFIJO_APP = "/app/";

export interface ConfigTrabajador {
  /** Nombre de la caché de esta versión (`finanzas-cascaron-<hash>`). */
  cache: string;
  /** Rutas del cascarón (`/app/…`), generadas al compilar. */
  precache: readonly string[];
}

export type Decision = "red" | "cascaron" | "navegacion";

/** Rutas de la API: nunca se guardan ni se responden desde la caché. */
export function esRutaApi(ruta: string): boolean {
  return ruta === "/api" || ruta.startsWith("/api/");
}

/** Solo lo de /app/, sin /api y sin el propio service worker, puede ir al cascarón. */
export function puedeIrAlCascaron(ruta: string): boolean {
  return ruta.startsWith(PREFIJO_APP) && !esRutaApi(ruta) && ruta !== "/app/sw.js";
}

export function nombreCache(version: string): string {
  return PREFIJO_CACHE + version;
}

/**
 * Qué hacer con una petición:
 * - `red`: el service worker no responde y el navegador va a la red como si
 *   no existiera (API, otros métodos, otros orígenes, la interfaz de la v1).
 * - `navegacion`: abrir una pantalla de /app; primero la red y, sin conexión,
 *   el índice guardado.
 * - `cascaron`: un archivo de la lista; se sirve desde la caché.
 */
export function decidir(
  peticion: { method: string; url: string; mode?: RequestMode },
  origen: string,
  precache: ReadonlySet<string>,
): Decision {
  if (peticion.method !== "GET") return "red";
  const url = new URL(peticion.url);
  if (url.origin !== origen) return "red";
  if (esRutaApi(url.pathname)) return "red";
  if (url.pathname !== "/app" && !url.pathname.startsWith(PREFIJO_APP)) return "red";
  if (peticion.mode === "navigate") return "navegacion";
  if (url.search === "" && precache.has(url.pathname)) return "cascaron";
  return "red";
}

/** Una respuesta del cascarón solo se guarda si es un 200 propio, sin redirigir. */
export function esGuardable(respuesta: Response): boolean {
  if (respuesta.status !== 200 || respuesta.redirected) return false;
  if (respuesta.type !== "basic" && respuesta.type !== "default") return false;
  const tipo = respuesta.headers.get("content-type") ?? "";
  return !tipo.includes("json") || tipo.includes("manifest+json");
}

/**
 * Instalar: descarga el cascarón de esta versión y lo guarda. Si algo falla,
 * la instalación falla entera (y queda la versión anterior).
 */
export async function instalar(
  config: ConfigTrabajador,
  almacen: CacheStorage,
  pedir: typeof fetch,
  origen: string,
): Promise<void> {
  const cache = await almacen.open(config.cache);
  try {
    for (const ruta of config.precache) {
      if (!puedeIrAlCascaron(ruta)) throw new Error(`Ruta fuera del cascarón: ${ruta}`);
      const respuesta = await pedir(
        new Request(new URL(ruta, origen), { credentials: "omit", cache: "reload" }),
      );
      if (!esGuardable(respuesta)) throw new Error(`No se pudo guardar ${ruta} (${respuesta.status})`);
      await cache.put(ruta, respuesta);
    }
  } catch (error) {
    // No dejar una caché a medias: el próximo intento empieza de cero.
    await almacen.delete(config.cache).catch(() => false);
    throw error;
  }
}

/**
 * Solo se aceptan mensajes de una página de este mismo origen (el que manda
 * `registrar.ts` al cerrar sesión). Un origen vacío o ajeno se ignora.
 */
export function esMensajeLimpiar(evento: { origin: string; data: unknown }, origen: string): boolean {
  if (evento.origin !== origen) return false;
  const datos = evento.data;
  return !!datos && typeof datos === "object" && (datos as { tipo?: unknown }).tipo === MENSAJE_LIMPIAR;
}

/**
 * Deja solo el cascarón de esta versión: borra las cachés viejas (o ajenas) y,
 * en la actual, cualquier entrada que no sea de la lista. Se llama al activar
 * una versión nueva y al cerrar sesión.
 */
export async function limpiar(config: ConfigTrabajador, almacen: CacheStorage): Promise<void> {
  for (const nombre of await almacen.keys()) {
    if (nombre !== config.cache) await almacen.delete(nombre);
  }
  if (!(await almacen.has(config.cache))) return;
  const permitidas = new Set(config.precache);
  const cache = await almacen.open(config.cache);
  for (const peticion of await cache.keys()) {
    if (!permitidas.has(new URL(peticion.url).pathname)) await cache.delete(peticion);
  }
}

/**
 * Responde una petición, o devuelve `null` para que vaya a la red sin pasar
 * por el service worker. Nunca escribe en la caché.
 */
export function responder(
  peticion: Request,
  config: ConfigTrabajador,
  almacen: CacheStorage,
  pedir: typeof fetch,
  origen: string,
  precache: ReadonlySet<string>,
): Promise<Response> | null {
  switch (decidir(peticion, origen, precache)) {
    case "red":
      return null;
    case "navegacion":
      return pedir(peticion).catch(async (error: unknown) => {
        const indice = await (await almacen.open(config.cache)).match(RUTA_INDICE);
        if (indice) return indice;
        throw error;
      });
    case "cascaron":
      return almacen
        .open(config.cache)
        .then((cache) => cache.match(new URL(peticion.url).pathname))
        .then((guardada) => guardada ?? pedir(peticion));
  }
}
