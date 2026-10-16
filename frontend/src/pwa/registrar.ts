/**
 * Registro del service worker desde la página (ítem 18) y limpieza al cerrar
 * sesión. El service worker solo guarda el cascarón estático (ver
 * `trabajador.ts`); aun así, al cerrar sesión se le pide que borre todo lo que
 * no sea el cascarón de la versión actual.
 */
import { MENSAJE_LIMPIAR, PREFIJO_CACHE } from "./trabajador";

export const RUTA_SW = "/app/sw.js";
export const ALCANCE_SW = "/app/";

export type ResultadoRegistro = "registrado" | "sin-soporte" | "desactivado" | "fallo";

/**
 * Registra /app/sw.js con alcance /app/. Solo en la compilación de producción
 * (en `npm run dev` no existe sw.js). `updateViaCache: "none"`: el navegador
 * siempre pide sw.js a la red para saber si hay una versión nueva.
 */
export async function registrarServiceWorker(
  navegador: Pick<Navigator, "serviceWorker"> | undefined = globalThis.navigator,
  produccion: boolean = import.meta.env.PROD,
): Promise<ResultadoRegistro> {
  if (!produccion) return "desactivado";
  const contenedor = navegador?.serviceWorker;
  if (!contenedor) return "sin-soporte";
  try {
    await contenedor.register(RUTA_SW, { scope: ALCANCE_SW, updateViaCache: "none" });
    return "registrado";
  } catch {
    // Sin service worker la app funciona igual (solo no abre sin conexión).
    return "fallo";
  }
}

/**
 * Al cerrar sesión (o perderla): que no quede en Cache Storage nada que no
 * sea el cascarón actual. Si hay un service worker activo, él lo hace (sabe
 * cuál es su versión); si no, se borran directamente las cachés de la app.
 * Nunca lanza: cerrar sesión no puede fallar por esto.
 */
export async function limpiarCachesAlSalir(
  navegador: Pick<Navigator, "serviceWorker"> | undefined = globalThis.navigator,
  almacen: CacheStorage | undefined = globalThis.caches,
): Promise<void> {
  try {
    const activo = navegador?.serviceWorker?.controller;
    if (activo) {
      activo.postMessage({ tipo: MENSAJE_LIMPIAR });
      return;
    }
    if (!almacen) return;
    for (const nombre of await almacen.keys()) {
      if (nombre.startsWith(PREFIJO_CACHE)) await almacen.delete(nombre);
    }
  } catch {
    /* sin acceso a Cache Storage: no hay nada guardado */
  }
}
