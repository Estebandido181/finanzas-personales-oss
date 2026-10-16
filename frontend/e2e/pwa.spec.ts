/**
 * Instalable en el celular (ítem 18), en un navegador de verdad contra la app
 * real: manifest enlazado y válido para Chrome, íconos, service worker y,
 * sobre todo, que en Cache Storage nunca quede nada de /api ni datos
 * financieros (con sesión, tras cerrar sesión y sin conexión). La CSP la
 * vigila `test` (ayudas.ts) en cada prueba. Solo datos inventados.
 */
import type { Page } from "@playwright/test";
import { entrar, expect, revisarAccesibilidad, TAMANOS, test } from "./ayudas";
import { TEXTOS } from "../src/compartido/textos/textos";

/** Nombre de caché → rutas guardadas. */
async function contenidoCaches(page: Page): Promise<Record<string, string[]>> {
  return page.evaluate(async () => {
    const salida: Record<string, string[]> = {};
    for (const nombre of await caches.keys()) {
      const cache = await caches.open(nombre);
      salida[nombre] = (await cache.keys()).map((r) => new URL(r.url).pathname + new URL(r.url).search);
    }
    return salida;
  });
}

/** Espera a que el service worker esté activo y controle la página. */
async function esperarServiceWorker(page: Page): Promise<void> {
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
}

/** Ancho y alto de un PNG (cabecera IHDR). */
function medidasPng(png: Buffer): [number, number] {
  expect(png.subarray(1, 4).toString("latin1")).toBe("PNG");
  return [png.readUInt32BE(16), png.readUInt32BE(20)];
}

const CACHE_DE_VERSION = /^finanzas-cascaron-[0-9a-f]{16}$/;

test.describe("manifest e íconos", () => {
  test("el manifest se sirve con su tipo, la CSP y sin caché HTTP", async ({ request }) => {
    const r = await request.get("/app/manifest.webmanifest");
    expect(r.status()).toBe(200);
    expect(r.headers()["content-type"]).toBe("application/manifest+json");
    expect(r.headers()["content-security-policy"]).toContain("default-src 'self'");
    const m = await r.json();
    expect(m).toMatchObject({
      id: "/app/",
      name: "Finanzas personales",
      short_name: "Finanzas",
      start_url: "/app/",
      scope: "/app/",
      display: "standalone",
      theme_color: "#E6DAC0",
      background_color: "#E6DAC0",
    });
    const propositos = (m.icons as { sizes: string; purpose: string }[]).map((i) => `${i.sizes} ${i.purpose}`);
    expect(propositos).toEqual(["192x192 any", "512x512 any", "512x512 maskable"]);
  });

  test("los íconos existen, son PNG y miden lo que dicen", async ({ request }) => {
    const iconos: [string, number][] = [
      ["/app/iconos/icono-192.png", 192],
      ["/app/iconos/icono-512.png", 512],
      ["/app/iconos/icono-maskable-512.png", 512],
      ["/app/iconos/apple-touch-icon.png", 180],
    ];
    for (const [ruta, lado] of iconos) {
      const r = await request.get(ruta);
      expect(r.status(), ruta).toBe(200);
      expect(r.headers()["content-type"]).toBe("image/png");
      expect(medidasPng(await r.body()), ruta).toEqual([lado, lado]);
    }
  });

  test("el HTML enlaza el manifest y lo de iPhone, y Chrome la da por instalable", async ({ page }) => {
    await page.goto("/app/");
    const cabeza = page.locator("head");
    await expect(cabeza.locator('link[rel="manifest"]')).toHaveAttribute("href", "/app/manifest.webmanifest");
    await expect(cabeza.locator('link[rel="apple-touch-icon"]')).toHaveAttribute(
      "href",
      "/app/iconos/apple-touch-icon.png",
    );
    await expect(cabeza.locator('meta[name="apple-mobile-web-app-capable"]')).toHaveAttribute("content", "yes");
    await expect(cabeza.locator('meta[name="apple-mobile-web-app-title"]')).toHaveAttribute("content", "Finanzas");
    await expect(cabeza.locator('meta[name="theme-color"]')).toHaveCount(2);

    // Lo que dice el propio Chrome (como en DevTools > Application > Manifest).
    await esperarServiceWorker(page);
    const cdp = await page.context().newCDPSession(page);
    const manifest = await cdp.send("Page.getAppManifest");
    expect(manifest.url).toMatch(/\/app\/manifest\.webmanifest$/);
    expect(manifest.errors).toEqual([]);
    const { installabilityErrors } = await cdp.send("Page.getInstallabilityErrors");
    // Los contextos de Playwright son de incógnito, donde Chrome nunca ofrece
    // instalar; cualquier otro motivo (manifest, íconos, alcance…) es un error.
    expect(installabilityErrors.map((e) => e.errorId).filter((id) => id !== "in-incognito")).toEqual([]);
  });
});

test.describe("service worker", () => {
  test("/app/sw.js se sirve como JavaScript, sin caché HTTP y con la CSP", async ({ request }) => {
    const r = await request.get("/app/sw.js");
    expect(r.status()).toBe(200);
    expect(r.headers()["content-type"]).toBe("text/javascript; charset=utf-8");
    expect(r.headers()["cache-control"]).toBe("no-store");
    expect(r.headers()["content-security-policy"]).toContain("script-src 'self'");
  });

  test("se registra con alcance /app/ y guarda solo el cascarón", async ({ page }) => {
    await page.goto("/app/");
    await esperarServiceWorker(page);
    const registro = await page.evaluate(async () => {
      const r = await navigator.serviceWorker.ready;
      return { alcance: r.scope, script: r.active?.scriptURL ?? "" };
    });
    expect(new URL(registro.alcance).pathname).toBe("/app/");
    expect(new URL(registro.script).pathname).toBe("/app/sw.js");
    const guardado = await contenidoCaches(page);
    const nombres = Object.keys(guardado);
    expect(nombres).toHaveLength(1);
    expect(nombres[0]).toMatch(CACHE_DE_VERSION);
    const rutas = guardado[nombres[0]!]!;
    expect(rutas).toContain("/app/");
    expect(rutas).toContain("/app/manifest.webmanifest");
    expect(rutas.some((r) => /^\/app\/assets\/index-[\w-]+\.js$/.test(r))).toBe(true);
    for (const ruta of rutas) {
      expect(ruta).toMatch(/^\/app\/(|assets\/[\w.-]+|iconos\/[\w.-]+\.png|manifest\.webmanifest|tema-inicial\.js)$/);
    }
  });
});

test.describe("nada financiero en Cache Storage", () => {
  test("con sesión, tras recorrer las pantallas, /api nunca queda guardada", async ({ page }) => {
    await entrar(page);
    await esperarServiceWorker(page);
    // Con el service worker ya controlando, se recorren pantallas que leen la API.
    for (const ruta of ["/app/", "/app/movimientos", "/app/no-reconocidos", "/app/mas"]) {
      const respuesta = page.waitForResponse((r) => new URL(r.url()).pathname.startsWith("/api/"));
      await page.goto(ruta);
      const api = await respuesta;
      // La API llega de la red, nunca del service worker.
      expect(api.fromServiceWorker()).toBe(false);
      expect(api.headers()["cache-control"]).toBe("no-store");
    }
    const guardado = await contenidoCaches(page);
    const rutas = Object.values(guardado).flat();
    expect(rutas.length).toBeGreaterThan(0);
    expect(rutas.filter((r) => r.startsWith("/api"))).toEqual([]);
    expect(rutas.filter((r) => !r.startsWith("/app/"))).toEqual([]);
    // El índice guardado es el cascarón vacío: sin montos ni nombres de comercios.
    const indice = await page.evaluate(async () => {
      const r = await caches.match("/app/");
      return r ? r.text() : "";
    });
    expect(indice).toContain('<div id="raiz"></div>');
    expect(indice).not.toContain("$");
  });

  test("al cerrar sesión se borran las cachés viejas y lo que no es del cascarón", async ({ page }) => {
    await page.setViewportSize(TAMANOS.celular);
    await entrar(page, "/app/mas");
    await esperarServiceWorker(page);
    const actual = Object.keys(await contenidoCaches(page))[0]!;
    // Simula restos que no deberían existir: una versión vieja y una respuesta de la API.
    await page.evaluate(async (nombre) => {
      const vieja = await caches.open("finanzas-cascaron-0000000000000000");
      await vieja.put("/app/assets/index-viejo.js", new Response("// viejo"));
      const c = await caches.open(nombre);
      await c.put("/api/reporte", new Response('{"total": 123400}'));
    }, actual);
    expect(Object.keys(await contenidoCaches(page))).toHaveLength(2);

    await page.getByRole("button", { name: "Cerrar sesión" }).click();
    await expect(page.getByLabel("Contraseña")).toBeVisible();
    await expect
      .poll(async () => {
        const guardado = await contenidoCaches(page);
        return { nombres: Object.keys(guardado), api: Object.values(guardado).flat().filter((r) => r.startsWith("/api")) };
      })
      .toEqual({ nombres: [actual], api: [] });
  });

  test("sin conexión abre la pantalla «sin conexión», sin datos", async ({ page, context }) => {
    await entrar(page);
    await esperarServiceWorker(page);
    await context.setOffline(true);
    try {
      await page.goto("/app/movimientos");
      await expect(page.getByRole("alert")).toHaveText(TEXTOS.errores.sinConexion);
      await expect(page.getByRole("button", { name: TEXTOS.errores.volverAIntentar })).toBeVisible();
      await expect(page.getByText("$")).toHaveCount(0);
      await revisarAccesibilidad(page);
    } finally {
      await context.setOffline(false);
    }
    await page.getByRole("button", { name: TEXTOS.errores.volverAIntentar }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Movimientos" })).toBeVisible();
  });
});
