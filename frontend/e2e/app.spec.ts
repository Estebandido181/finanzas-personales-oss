/**
 * Base del frontend en /app (ítem 12), en un navegador de verdad contra la app
 * real: login, navegación, apariencia, accesibilidad (axe) y CSP estricta.
 * Solo datos inventados (scripts/servidor_e2e.py).
 */
import {
  entrar,
  expect,
  prepararModo,
  revisarAccesibilidad,
  TAMANOS,
  test,
  type Modo,
  type Tamano,
} from "./ayudas";
import { mesActualColombia, tituloMes } from "../src/compartido/formatos/formato";

/** Inicio se titula con el mes actual en Colombia ("Septiembre de 2026"). */
const TITULO_INICIO = tituloMes(mesActualColombia());

const PANTALLAS = [
  { ruta: "/app/", titulo: TITULO_INICIO },
  { ruta: "/app/movimientos", titulo: "Movimientos" },
  { ruta: "/app/saldo", titulo: "Saldo" },
  { ruta: "/app/categorias", titulo: "Categorías y reglas" },
  { ruta: "/app/no-reconocidos", titulo: "Correos no reconocidos" },
  { ruta: "/app/mas", titulo: "Más" },
  { ruta: "/app/no-existe", titulo: "Esta página no existe" },
];

test.describe("servidor", () => {
  test("/app lleva la CSP estricta de la v1, sin excepciones", async ({ request }) => {
    const r = await request.get("/app/");
    expect(r.status()).toBe(200);
    const csp = r.headers()["content-security-policy"]!;
    expect(csp).toContain("script-src 'self';");
    expect(csp).toContain("style-src 'self';");
    expect(csp).not.toContain("unsafe-inline");
    expect(csp).not.toContain("unsafe-eval");
    expect(csp).not.toContain("nonce-");
    expect(r.headers()["cache-control"]).toBe("no-store");
  });

  test("el HTML compilado no tiene scripts ni estilos en línea", async ({ request }) => {
    const html = await (await request.get("/app/")).text();
    expect(html).not.toMatch(/<style/i);
    expect(html).not.toMatch(/\sstyle=/i);
    expect(html).not.toMatch(/\son[a-z]+=/i);
    for (const script of html.match(/<script[^>]*>[\s\S]*?<\/script>/gi) ?? []) {
      expect(script).toMatch(/\ssrc="/);
      expect(script.replace(/<script[^>]*>|<\/script>/gi, "").trim()).toBe("");
    }
  });

  test("las direcciones de la v1 llevan a la app (ítem 20)", async ({ page, request }) => {
    for (const [vieja, nueva] of [
      ["/", "/app/"],
      ["/login", "/app/"],
      ["/saldo", "/app/saldo"],
      ["/sin-categorizar", "/app/movimientos"],
      ["/reglas", "/app/categorias"],
    ]) {
      const r = await request.get(vieja!, { maxRedirects: 0 });
      expect(r.status(), vieja).toBe(307);
      expect(r.headers()["location"], vieja).toBe(nueva);
    }
    // ?mes= se conserva si es válido.
    const r = await request.get("/?mes=2026-09", { maxRedirects: 0 });
    expect(r.headers()["location"]).toBe("/app/?mes=2026-09");
    // En el navegador, / termina en la pantalla de entrar de la app.
    await page.goto("/");
    await expect(page).toHaveURL(/\/app\/$/);
    await expect(page.getByLabel("Contraseña")).toBeVisible();
  });
});

test.describe("entrar y salir", () => {
  test("contraseña incorrecta y luego correcta", async ({ page }) => {
    await page.goto("/app/saldo");
    await expect(page.getByRole("heading", { level: 1, name: "Finanzas personales" })).toBeVisible();
    await page.getByLabel("Contraseña").fill("otra-clave-inventada");
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page.getByLabel("Contraseña")).toHaveAccessibleDescription(
      "Contraseña incorrecta. Revísala y vuelve a intentarlo.",
    );
    await page.getByLabel("Contraseña").fill("clave-e2e-inventada");
    await page.getByRole("button", { name: "Entrar" }).click();
    // Vuelve a la dirección que se pidió.
    await expect(page.getByRole("heading", { level: 1, name: "Saldo" })).toBeVisible();
    await expect(page).toHaveURL(/\/app\/saldo$/);
  });

  test("la sesión se conserva al recargar y al entrar por /", async ({ page }) => {
    await entrar(page);
    await page.reload();
    await expect(page.getByRole("heading", { level: 1, name: TITULO_INICIO })).toBeVisible();
    await page.goto("/"); // la dirección de la v1 lleva a la app, con la sesión abierta
    await expect(page).toHaveURL(/\/app\/$/);
    await expect(page.getByRole("heading", { level: 1, name: TITULO_INICIO })).toBeVisible();
  });

  test("cerrar sesión envía el token CSRF y cierra también la API", async ({ page }) => {
    await page.setViewportSize(TAMANOS.computador);
    await entrar(page);
    const cierre = page.waitForRequest((r) => r.method() === "DELETE" && r.url().endsWith("/api/sesion"));
    await page.getByRole("complementary").getByRole("button", { name: "Cerrar sesión" }).click();
    expect((await cierre).headers()["x-csrf-token"]).toBeTruthy();
    await expect(page.getByLabel("Contraseña")).toBeVisible();
    const r = await page.request.get("/api/sesion");
    expect(r.status()).toBe(401);
  });

  test("si la sesión se cierra por fuera, la app vuelve a entrar y lo dice", async ({
    page,
    context,
  }) => {
    await page.setViewportSize(TAMANOS.celular);
    await entrar(page, "/app/mas");
    // Que terminen las peticiones de la pantalla antes de borrar la cookie: si
    // una sale sin sesión, la app vuelve sola a "Entrar" y el botón desaparece
    // antes del clic (carrera vista en el CI).
    await page.waitForLoadState("networkidle");
    await context.clearCookies();
    await page.getByRole("button", { name: "Cerrar sesión" }).click();
    await expect(page.getByText("Tu sesión se cerró. Entra de nuevo para seguir.")).toBeVisible();
    await expect(page.getByLabel("Contraseña")).toBeVisible();
  });

  test("no guarda nada financiero en el navegador", async ({ page }) => {
    await entrar(page);
    for (const { ruta } of PANTALLAS) await page.goto(ruta);
    await page.goto("/app/mas");
    await page.getByRole("button", { name: "Oscuro" }).last().click();
    const almacenado = await page.evaluate(async () => ({
      local: Object.keys(localStorage),
      sesion: Object.keys(sessionStorage),
      // Ítem 18: el único service worker es el de /app/ (solo guarda el
      // cascarón estático; lo de Cache Storage lo prueba e2e/pwa.spec.ts).
      trabajadores: ((await navigator.serviceWorker?.getRegistrations()) ?? []).map(
        (r) => new URL(r.scope).pathname,
      ),
      cachesConApi: (
        await Promise.all(
          (await caches.keys()).map(async (n) => (await (await caches.open(n)).keys()).map((r) => r.url)),
        )
      )
        .flat()
        .filter((u) => new URL(u).pathname.startsWith("/api")),
      cookiesVisibles: document.cookie,
    }));
    expect(almacenado.local).toEqual(["finanzas-tema"]);
    expect(almacenado.sesion).toEqual([]);
    expect(almacenado.trabajadores).toEqual(["/app/"]);
    expect(almacenado.cachesConApi).toEqual([]);
    // La cookie de sesión es HttpOnly: el JavaScript de la página no la ve.
    expect(almacenado.cookiesVisibles).toBe("");
  });
});

test.describe("navegación", () => {
  test("celular: barra inferior de 5 secciones, sin barra lateral", async ({ page }) => {
    await page.setViewportSize(TAMANOS.celular);
    await entrar(page);
    const barra = page.getByRole("navigation", { name: "Secciones" });
    await expect(barra).toHaveCount(1); // la lateral está oculta
    await expect(barra.getByRole("link")).toHaveText([
      "Inicio",
      "Movimientos",
      "Saldo",
      "Categorías",
      "Más",
    ]);
    await expect(page.getByRole("complementary")).toBeHidden();
    await barra.getByRole("link", { name: "Más" }).click();
    await expect(page).toHaveURL(/\/app\/mas$/);
    await expect(barra.getByRole("link", { name: "Más" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("link", { name: /^Correos no reconocidos\s*3 correos$/ })).toBeVisible();
    // Todo lo que se toca mide al menos 44 × 44 px (SISTEMA.md).
    for (const enlace of await barra.getByRole("link").all()) {
      const caja = (await enlace.boundingBox())!;
      expect(caja.height).toBeGreaterThanOrEqual(44);
      expect(caja.width).toBeGreaterThanOrEqual(44);
    }
  });

  test("computador: barra lateral con contador, sin barra inferior", async ({ page }) => {
    await page.setViewportSize(TAMANOS.computador);
    await entrar(page);
    const lateral = page.getByRole("complementary").getByRole("navigation", { name: "Secciones" });
    await expect(page.getByRole("navigation", { name: "Secciones" })).toHaveCount(1);
    await expect(lateral.getByRole("link", { name: /^No reconocidos\s*3 correos$/ })).toBeVisible();
    await lateral.getByRole("link", { name: "Categorías y reglas" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Categorías y reglas" })).toBeFocused();
    // La pantalla de Categorías es la de verdad (ítem 15).
    await expect(page.getByRole("button", { name: "Nueva categoría" })).toBeVisible();
    // Y la de Saldo (ítem 16), sin enlaces a la versión anterior.
    await lateral.getByRole("link", { name: "Saldo" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Saldo" })).toBeFocused();
    await expect(page.getByRole("region", { name: "Registrar un ingreso" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Abrir la versión anterior" })).toHaveCount(0);
    // La barra lateral se queda fija al hacer scroll (no se va con el contenido).
    const lateralCaja = (await page.getByRole("complementary").boundingBox())!;
    expect(lateralCaja.width).toBe(248);
  });

  test("con teclado: «Saltar al contenido» es lo primero", async ({ page }) => {
    await entrar(page);
    // Se espera a que Inicio termine de cargar: antes, al llegar los datos, el
    // título le quitaba el foco al enlace (la prueba fallaba según quién
    // llegara primero, el Tab o los datos).
    await expect(page.getByRole("navigation", { name: "Cambiar de mes" })).toBeVisible();
    await expect(page.locator("body")).toBeFocused();
    await page.keyboard.press("Tab");
    const salto = page.getByRole("link", { name: "Saltar al contenido" });
    await expect(salto).toBeFocused();
    await expect(salto).toBeVisible();
    // Y lleva al contenido.
    await page.keyboard.press("Enter");
    await expect(page.getByRole("main")).toBeFocused();
  });
});

test.describe("apariencia", () => {
  test("la elección se recuerda y se aplica antes de pintar", async ({ page }) => {
    await page.setViewportSize(TAMANOS.celular);
    await page.emulateMedia({ colorScheme: "light" });
    await entrar(page, "/app/mas");
    await page.getByRole("button", { name: "Oscuro" }).click();
    await expect(page.getByRole("button", { name: "Oscuro" })).toHaveAttribute("aria-pressed", "true");
    // Al recargar, el modo ya está puesto cuando llega el HTML (tema-inicial.js),
    // antes de que React arranque: sin destello.
    const alCargar = page.waitForEvent("domcontentloaded");
    await page.reload();
    await alCargar;
    const fondo = await page.evaluate(() => ({
      tema: document.documentElement.dataset.tema,
      fondo: getComputedStyle(document.body).backgroundColor,
    }));
    expect(fondo).toEqual({ tema: "oscuro", fondo: "rgb(24, 36, 34)" }); // --background oscuro
    await page.getByRole("button", { name: "Sistema" }).click();
    expect(await page.evaluate(() => localStorage.getItem("finanzas-tema"))).toBeNull();
  });

  test("«Sistema» sigue el modo del sistema", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goto("/app/");
    const fondo = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    expect(fondo).toBe("rgb(24, 36, 34)");
  });

  test("las fuentes son las del sistema de diseño, servidas desde /app", async ({ page }) => {
    const fuentes: string[] = [];
    page.on("response", (r) => {
      if (r.url().endsWith(".woff2")) fuentes.push(new URL(r.url()).pathname);
    });
    await entrar(page);
    await page.evaluate(() => document.fonts.ready);
    expect(fuentes.length).toBeGreaterThan(0);
    for (const ruta of fuentes) expect(ruta).toMatch(/^\/app\/assets\/.+\.woff2$/);
    const familia = await page.evaluate(
      () => getComputedStyle(document.querySelector("h1")!).fontFamily,
    );
    expect(familia).toContain("Alegreya");
  });
});

// Accesibilidad: cada pantalla, en celular y computador, claro y oscuro.
for (const tamano of Object.keys(TAMANOS) as Tamano[]) {
  for (const modo of ["claro", "oscuro"] as Modo[]) {
    test.describe(`accesibilidad ${tamano} ${modo}`, () => {
      test.beforeEach(async ({ page }) => {
        await page.setViewportSize(TAMANOS[tamano]);
        await prepararModo(page, modo);
      });

      test("entrar (con y sin error)", async ({ page }) => {
        await page.goto("/app/");
        await expect(page.getByRole("button", { name: "Entrar" })).toBeVisible();
        await revisarAccesibilidad(page);
        await page.getByRole("button", { name: "Entrar" }).click();
        await expect(page.getByText("Escribe tu contraseña.")).toBeVisible();
        await revisarAccesibilidad(page);
      });

      test("todas las pantallas con sesión", async ({ page }) => {
        await entrar(page);
        for (const { ruta, titulo } of PANTALLAS) {
          await page.goto(ruta);
          await expect(page.getByRole("heading", { level: 1, name: titulo })).toBeVisible();
          await revisarAccesibilidad(page);
        }
      });
    });
  }
}
