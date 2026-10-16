import { describe, expect, it, vi } from "vitest";
import { ALCANCE_SW, limpiarCachesAlSalir, registrarServiceWorker, RUTA_SW } from "./registrar";

function navegadorCon(serviceWorker: Partial<ServiceWorkerContainer> | undefined) {
  return { serviceWorker } as unknown as Pick<Navigator, "serviceWorker">;
}

describe("registrarServiceWorker", () => {
  it("registra /app/sw.js con alcance /app/ y sin caché HTTP del script", async () => {
    const register = vi.fn(async () => ({}) as ServiceWorkerRegistration);
    expect(await registrarServiceWorker(navegadorCon({ register }), true)).toBe("registrado");
    expect(register).toHaveBeenCalledWith(RUTA_SW, { scope: ALCANCE_SW, updateViaCache: "none" });
    expect(RUTA_SW).toBe("/app/sw.js");
    expect(ALCANCE_SW).toBe("/app/");
  });

  it("en desarrollo no registra nada", async () => {
    const register = vi.fn();
    expect(await registrarServiceWorker(navegadorCon({ register }), false)).toBe("desactivado");
    expect(register).not.toHaveBeenCalled();
  });

  it("sin soporte (o sin HTTPS) la app sigue sin service worker", async () => {
    expect(await registrarServiceWorker(navegadorCon(undefined), true)).toBe("sin-soporte");
    expect(await registrarServiceWorker(undefined, true)).toBe("sin-soporte");
  });

  it("si el registro falla, no lanza", async () => {
    const register = vi.fn(async () => {
      throw new DOMException("inseguro", "SecurityError");
    });
    expect(await registrarServiceWorker(navegadorCon({ register }), true)).toBe("fallo");
  });
});

describe("limpiarCachesAlSalir", () => {
  it("con un service worker activo, le pide limpiar (él sabe cuál es su versión)", async () => {
    const postMessage = vi.fn();
    const almacen = { keys: vi.fn(), delete: vi.fn() } as unknown as CacheStorage;
    await limpiarCachesAlSalir(
      navegadorCon({ controller: { postMessage } as unknown as ServiceWorker }),
      almacen,
    );
    expect(postMessage).toHaveBeenCalledWith({ tipo: "limpiar" });
    expect(almacen.delete).not.toHaveBeenCalled();
  });

  it("sin service worker activo, borra las cachés de la app y deja las ajenas", async () => {
    const borradas: string[] = [];
    const almacen = {
      keys: async () => ["finanzas-cascaron-v1", "finanzas-cascaron-v2", "de-otra-app"],
      delete: async (n: string) => {
        borradas.push(n);
        return true;
      },
    } as unknown as CacheStorage;
    await limpiarCachesAlSalir(navegadorCon({ controller: null }), almacen);
    expect(borradas).toEqual(["finanzas-cascaron-v1", "finanzas-cascaron-v2"]);
  });

  it("nunca lanza (sin Cache Storage o con error)", async () => {
    await expect(limpiarCachesAlSalir(undefined, undefined)).resolves.toBeUndefined();
    const roto = {
      keys: async () => {
        throw new Error("sin acceso");
      },
    } as unknown as CacheStorage;
    await expect(limpiarCachesAlSalir(navegadorCon(undefined), roto)).resolves.toBeUndefined();
  });
});
