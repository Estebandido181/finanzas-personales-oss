/**
 * Inicio (ítem 13) en un navegador de verdad contra la app real y los datos
 * inventados de scripts/servidor_e2e.py (relativos al mes actual): totales
 * iguales a los que calcula la API, cambio de mes, mes sin datos, sincronizar (bien y
 * con el permiso de Gmail revocado), accesibilidad con axe y CSP estricta
 * (la vigila `test` de ./ayudas en cada prueba).
 */
import type { APIRequestContext, Page } from "@playwright/test";
import { mesActualColombia, nombreMesCorto, tituloMes } from "../src/compartido/formatos/formato";
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

function mesAntes(mes: string, cuantos: number): string {
  const [anio, numero] = mes.split("-").map(Number) as [number, number];
  const total = anio * 12 + (numero - 1) - cuantos;
  return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}`;
}

const ACTUAL = mesActualColombia();
const ANTERIOR = mesAntes(ACTUAL, 1);
const SIN_DATOS = mesAntes(ACTUAL, 3);

/** "$1.842.450" o "$1.842.450,00" a centavos, para comparar. */
function centavos(texto: string): number {
  const limpio = texto.replace(/[^\d,−-]/g, "");
  const [enteros = "0", decimales = "00"] = limpio.replace(/[−-]/, "").split(",");
  return Number(enteros) * 100 + Number(decimales.padEnd(2, "0"));
}

/** Deja Gmail como antes y la última sincronización correcta (para las pruebas que siguen). */
async function restaurarSincronizacion(request: APIRequestContext, baseURL: string): Promise<void> {
  await request.get("/e2e/gmail/ok");
  const sesion = await request.get("/api/sesion");
  if (!sesion.ok()) return;
  const { csrf_token } = (await sesion.json()) as { csrf_token: string };
  await request.post("/api/sincronizacion", {
    headers: { "X-CSRF-Token": csrf_token, "Content-Type": "application/json", Origin: baseURL },
  });
}

/** El del encabezado (en un mes vacío hay otro más abajo). */
function botonSincronizar(page: Page) {
  return page.getByRole("main").getByRole("button", { name: "Sincronizar ahora" }).first();
}

async function fallarSincronizacion(page: Page): Promise<void> {
  await page.request.get("/e2e/gmail/revocado");
  await botonSincronizar(page).click();
  await expect(page.getByRole("alert")).toContainText("No se pudo sincronizar con Gmail");
}

test.afterEach(async ({ page, baseURL }) => {
  await restaurarSincronizacion(page.request, baseURL!);
});

test.describe("Inicio", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(TAMANOS.computador);
  });

  test("los totales coinciden con los de la API; ingresos y ajustes no cuentan como gasto", async ({
    page,
  }) => {
    await entrar(page);
    await expect(page.getByRole("heading", { level: 1, name: tituloMes(ACTUAL) })).toBeVisible();
    const resumen = page.getByRole("region", { name: /^Resumen de / });
    await expect(resumen).toContainText("$1.842.450");
    await expect(resumen).toContainText("$4.739.150");
    await expect(resumen).toContainText("+$5.350.000");
    const filas = page.getByRole("list", { name: /^Gasto por categoría en / }).getByRole("listitem");
    await expect(filas).toHaveCount(10);
    const v2 = new Map<string, number>();
    for (const fila of await filas.all()) {
      const [nombre, monto] = (await fila.innerText()).split("\n").map((t) => t.trim());
      v2.set(nombre!, centavos(monto!));
    }
    // Ítem 15: los gastos pendientes y el ingreso pendiente van aparte, nunca sumados.
    const pendientes = page.getByRole("region", { name: /movimientos sin categorizar$/ });
    await expect(pendientes).toContainText("Los gastos suman $34.700.");
    await expect(pendientes).toContainText("Aparte, los ingresos suman +$400.000.");

    // Lo que calcula el backend (única fuente de las reglas de negocio), con
    // la misma sesión y el mismo mes. Antes se comparaba con la v1 (ítem 20).
    const r = await page.request.get(`/api/reporte?mes=${ACTUAL}`);
    expect(r.status()).toBe(200);
    const reporte = (await r.json()) as {
      total_gasto_centavos: number;
      por_categoria: { nombre: string; centavos: number }[];
    };
    const api = new Map(reporte.por_categoria.map((g) => [g.nombre, g.centavos]));
    expect(v2).toEqual(api);
    expect(reporte.total_gasto_centavos).toBe(184_245_000);
    expect([...v2.values()].reduce((a, b) => a + b, 0)).toBe(reporte.total_gasto_centavos);
  });

  test("cambiar de mes, y un mes sin movimientos", async ({ page }) => {
    await entrar(page);
    const selector = page.getByRole("navigation", { name: "Cambiar de mes" });
    await expect(selector.getByRole("link")).toHaveCount(1); // en el mes actual, sin siguiente
    await selector.getByRole("link", { name: nombreMesCorto(ANTERIOR) }).click();
    await expect(page).toHaveURL(new RegExp(`/app/\\?mes=${ANTERIOR}$`));
    await expect(page.getByRole("heading", { level: 1, name: tituloMes(ANTERIOR) })).toBeFocused();
    await expect(page.getByRole("region", { name: /^Resumen de / })).toContainText("$4.807.000");
    await expect(selector.getByRole("link", { name: nombreMesCorto(ACTUAL) })).toHaveAttribute("rel", "next");
    await revisarAccesibilidad(page);

    await page.goto(`/app/?mes=${SIN_DATOS}`);
    await expect(page.getByRole("heading", { level: 2, name: /^Sin movimientos en / })).toBeVisible();
    await revisarAccesibilidad(page);
  });

  test("«Sincronizar ahora» que sale bien", async ({ page }) => {
    await entrar(page);
    await botonSincronizar(page).click();
    await expect(page.getByRole("status").filter({ hasText: "Sincronización terminada" })).toHaveText(
      "Sincronización terminada: no hay movimientos nuevos.",
    );
    await expect(page.getByText(/^Sincronizado hoy a la/)).toBeVisible();
  });

  test("permiso de Gmail revocado: lo dice arriba, con qué hacer, y sigue al recargar", async ({ page }) => {
    await entrar(page);
    await fallarSincronizacion(page);
    const alerta = page.getByRole("alert");
    await expect(alerta).toContainText("Gmail rechazó el permiso de lectura de la app");
    await expect(alerta).toContainText("Qué hacer:");
    await expect(alerta.getByRole("link", { name: "Ver cómo autorizar Gmail" })).toHaveAttribute(
      "href",
      "https://github.com/Estebandido181/finanzas-personales-oss/blob/main/docs/GMAIL.md",
    );
    await expect(page.getByText(/^Falló la sincronización\. Última correcta: /)).toBeVisible();
    await revisarAccesibilidad(page);

    // Como si hubiera fallado el temporizador: al volver a abrir, sigue ahí.
    await page.reload();
    await expect(page.getByRole("alert")).toContainText("No se pudo sincronizar con Gmail");

    // Una sincronización correcta lo quita.
    await page.request.get("/e2e/gmail/ok");
    await botonSincronizar(page).click();
    await expect(page.getByRole("status").filter({ hasText: "Sincronización terminada" })).toContainText("Sincronización terminada");
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("todo lo que se toca mide al menos 44 × 44 px", async ({ page }) => {
    await page.setViewportSize(TAMANOS.celular);
    await entrar(page);
    const tocables = page.locator("main a, main button");
    for (const elemento of await tocables.all()) {
      const caja = (await elemento.boundingBox())!;
      expect(caja.height, await elemento.innerText()).toBeGreaterThanOrEqual(44);
    }
  });
});

// Accesibilidad: normal, en dona y con la sincronización fallida; celular y computador; claro y oscuro.
for (const tamano of Object.keys(TAMANOS) as Tamano[]) {
  for (const modo of ["claro", "oscuro"] as Modo[]) {
    test(`accesibilidad de Inicio ${tamano} ${modo}`, async ({ page }) => {
      await page.setViewportSize(TAMANOS[tamano]);
      await prepararModo(page, modo);
      await entrar(page);
      await expect(page.getByRole("region", { name: /^Resumen de / })).toBeVisible();
      await revisarAccesibilidad(page);
      await page.getByRole("button", { name: "Dona" }).click();
      await expect(page.locator("path[data-categoria]")).toHaveCount(10);
      await revisarAccesibilidad(page);
      await page.getByRole("button", { name: "Barras" }).click();
      await fallarSincronizacion(page);
      await revisarAccesibilidad(page);
    });
  }
}
