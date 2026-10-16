/**
 * Pulido de la experiencia (ítem 38) en un navegador de verdad contra la app
 * real y los datos inventados de scripts/servidor_e2e.py:
 *
 * - sincronizar al abrir (lo decide el servidor, una sola vez por apertura);
 * - categorizar en grupo en «Sin categorizar», con la regla incluida;
 * - accesibilidad con axe y CSP estricta (la vigila `test` de ./ayudas).
 *
 * Deshacer (saldo y categorías) se prueba en saldo.spec.ts y categorias.spec.ts.
 * Estas pruebas cambian datos: cada una termina con `/e2e/datos/reiniciar`.
 */
import type { Page } from "@playwright/test";
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

async function pedir(page: Page, ruta: string): Promise<void> {
  expect((await page.request.get(ruta)).ok(), ruta).toBe(true);
}

test.afterEach(async ({ page }) => {
  await pedir(page, "/e2e/gmail/ok");
  await pedir(page, "/e2e/datos/reiniciar");
});

/** Cuenta las sincronizaciones que lanza la pantalla (POST /api/sincronizacion). */
function contarSincronizaciones(page: Page): () => number {
  let cuantas = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && new URL(r.url()).pathname === "/api/sincronizacion") cuantas++;
  });
  return () => cuantas;
}

const esSincronizacion = (r: import("@playwright/test").Response) =>
  r.request().method() === "POST" && new URL(r.url()).pathname === "/api/sincronizacion";

test.describe("Sincronizar al abrir", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(TAMANOS.computador);
  });

  test("si el servidor dice que toca, sincroniza sola una vez y deja el estado al día", async ({ page }) => {
    await entrar(page);
    await page.waitForLoadState("networkidle");
    await pedir(page, "/e2e/datos/sincronizacion-vieja");
    const antes = (await (await page.request.get("/api/sincronizacion")).json()) as {
      debe_sincronizar_al_abrir: boolean;
    };
    expect(antes.debe_sincronizar_al_abrir).toBe(true);

    const cuantas = contarSincronizaciones(page);
    const termino = page.waitForResponse(esSincronizacion);
    await page.reload();
    // Sin tocar nada: la app sincroniza al abrir.
    expect((await termino).ok()).toBe(true);
    await expect(page.getByRole("main").getByRole("status").filter({ hasText: "Sincronización terminada" })).toContainText("Sincronización terminada");
    await page.waitForLoadState("networkidle");
    expect(cuantas()).toBe(1);

    // El servidor ya no pide sincronizar, y la última fue la de la web.
    const despues = (await (await page.request.get("/api/sincronizacion")).json()) as {
      debe_sincronizar_al_abrir: boolean;
      ultima: { origen: string };
    };
    expect(despues.debe_sincronizar_al_abrir).toBe(false);
    expect(despues.ultima.origen).toBe("web");

    // Ir a Movimientos y volver a Inicio no es abrir la app: no repite.
    await page.getByRole("navigation", { name: "Secciones" }).getByRole("link", { name: "Movimientos" }).first().click();
    await expect(page.getByRole("heading", { level: 1, name: "Movimientos" })).toBeVisible();
    await page.getByRole("navigation", { name: "Secciones" }).getByRole("link", { name: "Inicio" }).first().click();
    await expect(page.getByRole("region", { name: /^Resumen de / })).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(cuantas()).toBe(1);
  });

  test("si la última sincronización es reciente, no sincroniza al abrir", async ({ page }) => {
    await entrar(page);
    await page.waitForLoadState("networkidle");
    const cuantas = contarSincronizaciones(page);
    await page.reload();
    await expect(page.getByRole("region", { name: /^Resumen de / })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sincronizar ahora" })).toBeEnabled();
    await page.waitForLoadState("networkidle");
    expect(cuantas()).toBe(0);
  });

  test("si Gmail rechaza el permiso, lo dice una vez y no reintenta sola al volver a abrir", async ({ page }) => {
    await entrar(page);
    await page.waitForLoadState("networkidle");
    await pedir(page, "/e2e/gmail/revocado");
    await pedir(page, "/e2e/datos/sincronizacion-vieja");
    const cuantas = contarSincronizaciones(page);
    const termino = page.waitForResponse(esSincronizacion);
    await page.reload();
    await termino;
    // El aviso grande de siempre explica qué hacer.
    await expect(page.getByRole("alert")).toContainText("No se pudo sincronizar con Gmail");
    await page.waitForLoadState("networkidle");
    expect(cuantas()).toBe(1);

    // Aunque se abra otra vez, el servidor sabe que eso no se arregla solo: no reintenta.
    await page.reload();
    await expect(page.getByRole("alert")).toContainText("No se pudo sincronizar con Gmail");
    await page.waitForLoadState("networkidle");
    expect(cuantas()).toBe(1);
  });
});

test.describe("Sin categorizar: categorizar en grupo", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(TAMANOS.computador);
  });

  async function abrirBandeja(page: Page): Promise<void> {
    await entrar(page, "/app/movimientos?ver=sin-categorizar");
    await pedir(page, "/e2e/datos/reiniciar");
    await pedir(page, "/e2e/datos/grupos");
    await page.reload();
    await expect(page.getByRole("region", { name: "Movimientos que se repiten" })).toBeVisible();
  }
  const grupos = (page: Page) => page.getByRole("region", { name: "Movimientos que se repiten" });

  test("los 20 iguales salen en un grupo y los sueltos siguen como hoy", async ({ page }) => {
    await abrirBandeja(page);
    const item = grupos(page).getByRole("listitem");
    await expect(item).toHaveCount(1);
    await expect(item).toContainText("COBRO VIAJE TRANSPORTE MASIVO");
    await expect(item).toContainText("Compra · 20 veces");
    await expect(item).toContainText("$64.000");
    // Los 20 no salen sueltos; los demás pendientes, con sus opciones abiertas como siempre.
    const sueltos = page.getByRole("list", { name: "Movimientos sin categorizar, por día" });
    await expect(sueltos.getByText("COBRO VIAJE TRANSPORTE MASIVO")).toHaveCount(0);
    await expect(sueltos.getByText("PANADERIA EL TRIGAL", { exact: true })).toBeVisible();
    await expect(
      sueltos.getByRole("group", { name: "¿En qué categoría va? Toca una:" }).first(),
    ).toBeVisible();
    // Los 20 pendientes del grupo suman al número de «Sin categorizar».
    await expect(page.getByRole("button", { name: "Sin categorizar (25)" })).toBeVisible();
  });

  test("un toque categoriza los 20 y guarda la regla; el número baja", async ({ page }) => {
    await abrirBandeja(page);
    await grupos(page).getByRole("button", { name: /^Categorizar las 20/ }).click();
    await grupos(page).getByRole("group", { name: "¿En qué categoría van las 20? Toca una:" }).getByRole("button", { name: "Transporte" }).click();

    const aviso = grupos(page).getByRole("status");
    await expect(aviso).toContainText("20 movimientos categorizados en Transporte.");
    await expect(aviso).toContainText(
      "Regla creada: compras en COBRO VIAJE TRANSPORTE MASIVO van a Transporte.",
    );
    await expect(aviso).toBeFocused();
    await expect(page.getByRole("button", { name: "Sin categorizar (5)" })).toBeVisible();

    // Se guardó de verdad: los 20 en Transporte, a mano, y la regla.
    const bandeja = (await (await page.request.get("/api/movimientos/sin-categorizar")).json()) as {
      total: number;
      grupos: unknown[];
    };
    expect(bandeja.total).toBe(5);
    expect(bandeja.grupos).toEqual([]);
    const { reglas } = (await (await page.request.get("/api/reglas")).json()) as {
      reglas: { frase: string; categoria: { nombre: string } }[];
    };
    const regla = reglas.find((r) => r.frase.includes("cobro viaje transporte masivo"));
    expect(regla?.categoria.nombre).toBe("Transporte");
    const { movimientos } = (await (await page.request.get("/api/movimientos")).json()) as {
      movimientos: { descripcion: string; categoria: { nombre: string } | null; origen_categoria: string | null }[];
    };
    const viajes = movimientos.filter((m) => m.descripcion === "COBRO VIAJE TRANSPORTE MASIVO");
    expect(viajes).toHaveLength(20);
    expect(viajes.every((m) => m.categoria?.nombre === "Transporte" && m.origen_categoria === "manual")).toBe(true);

    // Al volver a abrir, ya no hay grupo y la regla aparece en Categorías y reglas.
    await page.reload();
    await expect(page.getByRole("list", { name: "Movimientos sin categorizar, por día" })).toBeVisible();
    await expect(grupos(page)).toHaveCount(0);
    await page.goto("/app/categorias");
    await expect(page.getByRole("region", { name: "Reglas" })).toContainText(
      "Si es una compra en «COBRO VIAJE TRANSPORTE MASIVO», va a Transporte",
    );
  });

  test("«Cancelar» cierra las opciones sin categorizar nada", async ({ page }) => {
    await abrirBandeja(page);
    await grupos(page).getByRole("button", { name: /^Categorizar las 20/ }).click();
    await grupos(page).getByRole("button", { name: "Cancelar" }).click();
    await expect(grupos(page).getByRole("button", { name: /^Categorizar las 20/ })).toBeVisible();
    const bandeja = (await (await page.request.get("/api/movimientos/sin-categorizar")).json()) as { grupos: unknown[] };
    expect(bandeja.grupos).toHaveLength(1);
  });
});

test("todo lo del grupo se toca con el dedo: al menos 44 × 44 px", async ({ page }) => {
  await page.setViewportSize(TAMANOS.celular);
  await entrar(page, "/app/movimientos?ver=sin-categorizar");
  await pedir(page, "/e2e/datos/grupos");
  await page.reload();
  const hoja = page.getByRole("region", { name: "Movimientos que se repiten" });
  await hoja.getByRole("button", { name: /^Categorizar las 20/ }).click();
  for (const elemento of await hoja.locator("button").all()) {
    const caja = (await elemento.boundingBox())!;
    const nombre = await elemento.innerText();
    expect(caja.height, nombre).toBeGreaterThanOrEqual(44);
  }
});

for (const tamano of Object.keys(TAMANOS) as Tamano[]) {
  for (const modo of ["claro", "oscuro"] as Modo[]) {
    test(`accesibilidad de los grupos de Sin categorizar ${tamano} ${modo}`, async ({ page }) => {
      await page.setViewportSize(TAMANOS[tamano]);
      await prepararModo(page, modo);
      await entrar(page, "/app/movimientos?ver=sin-categorizar");
      await pedir(page, "/e2e/datos/grupos");
      await page.reload();
      const hoja = page.getByRole("region", { name: "Movimientos que se repiten" });
      await expect(hoja).toBeVisible();
      await revisarAccesibilidad(page);

      await hoja.getByRole("button", { name: /^Categorizar las 20/ }).click();
      await expect(hoja.getByRole("group")).toBeVisible();
      await revisarAccesibilidad(page);

      await hoja.getByRole("group").getByRole("button", { name: "Transporte" }).click();
      await expect(hoja.getByRole("status")).toBeVisible();
      await revisarAccesibilidad(page);
    });
  }
}
