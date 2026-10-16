/**
 * Correos no reconocidos (ítem 19) en un navegador de verdad, contra la app
 * real y los datos inventados de scripts/servidor_e2e.py: tres correos, de
 * los que el Gmail falso hace que uno (el de asunto «Bancolombia te informa»)
 * se reconozca al reprocesar. Cubre la lista, reprocesar (uno se va, los otros
 * se quedan y se cuentan), el estado vacío, el error, accesibilidad con axe en
 * celular y computador, claro y oscuro, y áreas táctiles de 44 px. La CSP
 * estricta la vigila `test` de ./ayudas en cada prueba.
 *
 * Reprocesar cambia datos: cada prueba empieza y termina con
 * `/e2e/datos/reiniciar` y deja el Gmail falso en «ok».
 */
import type { Page } from "@playwright/test";
import { entrar, expect, prepararModo, revisarAccesibilidad, TAMANOS, test, type Modo, type Tamano } from "./ayudas";

const ASUNTOS = ["Alertas y Notificaciones", "Bancolombia te informa", "Aviso de transacción"];
const BOTON = "Volver a procesar todos";

async function preparar(page: Page): Promise<void> {
  await entrar(page, "/app/no-reconocidos");
  expect((await page.request.get("/e2e/datos/reiniciar")).ok()).toBe(true);
  await page.reload();
  await expect(page.getByRole("heading", { level: 2, name: "3 correos" })).toBeVisible();
}

function asuntos(page: Page) {
  return page.getByRole("main").getByRole("listitem").locator("p:first-child");
}

test.afterEach(async ({ page }) => {
  await page.request.get("/e2e/gmail/ok");
  await page.request.get("/e2e/datos/reiniciar");
});

test.describe("Correos no reconocidos", () => {
  test("lista los correos con asunto y fecha, y el botón", async ({ page }) => {
    await preparar(page);
    await expect(page.getByRole("heading", { level: 1, name: "Correos no reconocidos" })).toBeVisible();
    await expect(asuntos(page)).toHaveText(ASUNTOS);
    // Fecha con año y hora de 12 horas, p. ej. "28 de septiembre de 2026, 9:28 p. m.".
    const fechas = page.getByRole("main").getByRole("listitem").locator("p:nth-child(2)");
    for (const fecha of await fechas.allInnerTexts()) {
      expect(fecha).toMatch(/^\d{1,2} de [a-záéíóú]+ de \d{4}, \d{1,2}:\d{2}\s[ap]\.\sm\.$/);
    }
    await expect(page.getByRole("button", { name: BOTON })).toBeEnabled();
  });

  test("reprocesar: uno se reconoce y se va, los otros quedan, y se cuentan", async ({ page }) => {
    await page.setViewportSize(TAMANOS.computador);
    await preparar(page);
    const lateral = page.getByRole("complementary").getByRole("navigation", { name: "Secciones" });
    await expect(lateral.getByRole("link", { name: /^No reconocidos\s*3 correos$/ })).toBeVisible();

    await page.getByRole("button", { name: BOTON }).click();
    await expect(page.getByRole("status")).toHaveText(
      "Se volvieron a procesar 3 correos. 1 creó un movimiento nuevo; 2 siguen sin reconocerse.",
    );
    await expect(page.getByRole("heading", { level: 2, name: "2 correos" })).toBeVisible();
    await expect(asuntos(page)).toHaveText(["Alertas y Notificaciones", "Aviso de transacción"]);
    await expect(lateral.getByRole("link", { name: /^No reconocidos\s*2 correos$/ })).toBeVisible();
    await revisarAccesibilidad(page);

    // Los que siguen sin reconocerse permanecen aunque se vuelva a procesar.
    await page.getByRole("button", { name: BOTON }).click();
    await expect(page.getByRole("status")).toHaveText(
      "Se volvieron a procesar 2 correos. Ninguno creó un movimiento nuevo; 2 siguen sin reconocerse.",
    );
    await expect(asuntos(page)).toHaveText(["Alertas y Notificaciones", "Aviso de transacción"]);

    // El movimiento nuevo está en Movimientos, y sin duplicar.
    await lateral.getByRole("link", { name: "Movimientos" }).click();
    await expect(page.getByText("TIENDA REPROCESADA EJEMPLO", { exact: true })).toHaveCount(1);
  });

  test("si Gmail rechaza el permiso, muestra el mismo aviso que Sincronizar y la lista no cambia", async ({
    page,
  }) => {
    await preparar(page);
    await page.request.get("/e2e/gmail/revocado");
    await page.getByRole("button", { name: BOTON }).click();
    const aviso = page.getByRole("alert");
    await expect(aviso).toContainText("Gmail rechazó el permiso de lectura de la app");
    await expect(aviso.getByRole("link", { name: "Ver cómo autorizar Gmail" })).toBeVisible();
    await expect(asuntos(page)).toHaveText(ASUNTOS);
    await revisarAccesibilidad(page);
  });

  test("sin correos: estado vacío y sin botón", async ({ page }) => {
    await page.route("**/api/no-reconocidos", (r) =>
      r.request().method() === "GET"
        ? r.fulfill({ status: 200, contentType: "application/json", body: '{"correos":[]}' })
        : r.continue(),
    );
    await entrar(page, "/app/no-reconocidos");
    await expect(page.getByRole("heading", { level: 2, name: "No hay correos sin reconocer" })).toBeVisible();
    await expect(page.getByRole("button", { name: BOTON })).toHaveCount(0);
    await page.getByRole("link", { name: "Volver al inicio" }).click();
    await expect(page).toHaveURL(/\/app\/$/);
  });

  test("error al cargar: lo dice y deja volver a intentar", async ({ page }) => {
    await entrar(page, "/app/no-reconocidos");
    await page.route("**/api/no-reconocidos", (r) => r.abort("internetdisconnected"));
    await page.reload();
    await expect(page.getByRole("alert")).toContainText("No hay conexión con la app.");
    await page.unroute("**/api/no-reconocidos");
    await page.getByRole("button", { name: "Volver a intentar" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "3 correos" })).toBeVisible();
  });

  test("409: hay una sincronización en curso", async ({ page }) => {
    await preparar(page);
    await page.route("**/api/no-reconocidos/reprocesar", (r) =>
      r.fulfill({ status: 409, contentType: "application/json", body: '{"detalle":"Hay una sincronización en curso."}' }),
    );
    await page.getByRole("button", { name: BOTON }).click();
    await expect(page.getByRole("alert")).toHaveText("Ya hay una sincronización en curso. Espera a que termine.");
    await expect(asuntos(page)).toHaveText(ASUNTOS);
    await page.unroute("**/api/no-reconocidos/reprocesar");
  });

  test("todo lo que se toca mide al menos 44 × 44 px (celular, con «Más»)", async ({ page }) => {
    await page.setViewportSize(TAMANOS.celular);
    await preparar(page);
    for (const elemento of await page.locator("main a, main button").all()) {
      const caja = (await elemento.boundingBox())!;
      expect(caja.height, await elemento.innerText()).toBeGreaterThanOrEqual(44);
    }
    await page.goto("/app/mas");
    const enlace = page.getByRole("link", { name: /^Correos no reconocidos\s*3 correos$/ });
    expect((await enlace.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await enlace.click();
    await expect(page.getByRole("heading", { level: 1, name: "Correos no reconocidos" })).toBeFocused();
  });
});

for (const tamano of Object.keys(TAMANOS) as Tamano[]) {
  for (const modo of ["claro", "oscuro"] as Modo[]) {
    test(`accesibilidad no reconocidos ${tamano} ${modo}: lista, resultado y vacío`, async ({ page }) => {
      await page.setViewportSize(TAMANOS[tamano]);
      await prepararModo(page, modo);
      await preparar(page);
      await revisarAccesibilidad(page);
      await page.getByRole("button", { name: BOTON }).click();
      await expect(page.getByRole("status")).toBeVisible();
      await revisarAccesibilidad(page);
      await page.route("**/api/no-reconocidos", (r) =>
        r.request().method() === "GET"
          ? r.fulfill({ status: 200, contentType: "application/json", body: '{"correos":[]}' })
          : r.continue(),
      );
      await page.goto("/app/no-reconocidos");
      await expect(page.getByRole("heading", { level: 2, name: "No hay correos sin reconocer" })).toBeVisible();
      await revisarAccesibilidad(page);
    });
  }
}

test("celular: en No reconocidos la barra inferior marca «Más»", async ({ page }) => {
  await page.setViewportSize(TAMANOS.celular);
  await preparar(page);
  const barra = page.getByRole("navigation", { name: "Secciones" });
  await expect(barra.getByRole("link", { name: "Más" })).toHaveAttribute("aria-current", "page");
});
