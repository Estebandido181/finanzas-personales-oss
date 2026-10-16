/**
 * Configurar saldo (ítem 16) en un navegador de verdad contra la app real y
 * los datos inventados de scripts/servidor_e2e.py: configurar desde cero (la
 * API guarda centavos enteros y la fecha), la fecha futura y la letra O se
 * explican en su campo sin llamar a la API, y con movimientos la pantalla es
 * de solo lectura y lleva a «Ajustar el saldo». Accesibilidad con axe y CSP
 * estricta (la vigila `test` de ./ayudas en cada prueba).
 *
 * Estas pruebas cambian datos: las que configuran empiezan con
 * `/e2e/datos/sin-saldo` y todas terminan con `/e2e/datos/reiniciar`.
 */
import type { Page } from "@playwright/test";
import type { components } from "../src/api/esquema";
import { entrar, expect, prepararModo, revisarAccesibilidad, TAMANOS, test, type Modo, type Tamano } from "./ayudas";

type Saldo = components["schemas"]["Saldo"];

const RUTA = "/app/saldo/configurar";

async function leerSaldo(page: Page): Promise<Saldo> {
  const r = await page.request.get("/api/saldo");
  expect(r.ok()).toBe(true);
  return (await r.json()) as Saldo;
}

/** Entra, deja la base sin saldo ni movimientos y abre "Configurar saldo". */
async function abrirSinSaldo(page: Page): Promise<void> {
  await entrar(page, RUTA);
  expect((await page.request.get("/e2e/datos/sin-saldo")).ok()).toBe(true);
  await page.reload();
  await expect(page.getByRole("button", { name: "Guardar saldo inicial" })).toBeVisible();
}

/** Un día más ("AAAA-MM-DD"), sin zonas horarias de por medio. */
function diaSiguiente(fecha: string): string {
  const [a, m, d] = fecha.split("-").map(Number) as [number, number, number];
  return new Date(Date.UTC(a, m - 1, d + 1)).toISOString().slice(0, 10);
}

const hoja = (page: Page) => page.getByRole("region", { name: "Tu punto de partida" });

test.afterEach(async ({ page }) => {
  expect((await page.request.get("/e2e/datos/reiniciar")).ok()).toBe(true);
});

test.describe("Configurar saldo", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(TAMANOS.computador);
  });

  test("configurar desde cero guarda centavos enteros y la fecha", async ({ page }) => {
    await abrirSinSaldo(page);
    expect((await leerSaldo(page)).configuracion).toBeNull();
    const { hoy } = await leerSaldo(page);
    const fechaInicio = `${hoy.slice(0, 8)}01`;
    await expect(hoja(page).getByLabel("Fecha de inicio")).toHaveValue(fechaInicio);

    await hoja(page).getByLabel("Saldo inicial en pesos").fill("1.250.000,50");
    await hoja(page).getByRole("button", { name: "Guardar saldo inicial" }).click();
    await expect(hoja(page).getByRole("status")).toContainText("Saldo inicial guardado: $1.250.000,50 desde el 1 de ");

    const despues = await leerSaldo(page);
    expect(despues.configuracion).toEqual({ saldo_inicial_centavos: 125_000_050, fecha_inicio: fechaInicio });
    expect(despues.saldo_centavos).toBe(125_000_050);

    // Saldo ya no dice «Empieza por tu saldo».
    await page.getByRole("navigation", { name: "Secciones" }).first().getByRole("link", { name: "Saldo" }).click();
    await expect(page.getByRole("region", { name: "Registrar un ingreso" })).toBeVisible();
  });

  test("desde Saldo sin configurar, «Configurar saldo» abre la pantalla nueva (no la v1)", async ({ page }) => {
    await abrirSinSaldo(page);
    await page.goto("/app/saldo");
    await page.getByRole("link", { name: "Configurar saldo" }).click();
    await expect(page).toHaveURL(/\/app\/saldo\/configurar$/);
    await expect(page.getByRole("heading", { level: 1, name: "Configurar saldo" })).toBeVisible();
  });

  test("una fecha futura y una letra O se explican en su campo, sin guardar nada", async ({ page }) => {
    await abrirSinSaldo(page);
    const { hoy } = await leerSaldo(page);
    let envios = 0;
    page.on("request", (r) => {
      if (r.method() === "PUT" && r.url().endsWith("/api/saldo/configuracion")) envios++;
    });

    const monto = hoja(page).getByLabel("Saldo inicial en pesos");
    const fecha = hoja(page).getByLabel("Fecha de inicio");
    await monto.fill("1.25O.000");
    await fecha.fill(diaSiguiente(hoy));
    await hoja(page).getByRole("button", { name: "Guardar saldo inicial" }).click();

    await expect(monto).toHaveAttribute("aria-invalid", "true");
    await expect(monto).toBeFocused();
    await expect(hoja(page)).toContainText(
      "Ese monto tiene una letra O en lugar de un cero. Escríbelo solo con números, por ejemplo 1.250.000.",
    );
    await expect(fecha).toHaveAttribute("aria-invalid", "true");
    await expect(fecha).toHaveAccessibleDescription(
      /La fecha de inicio no puede ser futura\. Elige hoy o un día anterior\.$/,
    );

    // Con el monto bien, sigue frenando la fecha futura.
    await monto.fill("1.250.000");
    await hoja(page).getByRole("button", { name: "Guardar saldo inicial" }).click();
    await expect(fecha).toBeFocused();
    expect(envios).toBe(0);
    expect((await leerSaldo(page)).configuracion).toBeNull();

    // La API también la rechaza si se le manda directo.
    const token = ((await (await page.request.get("/api/sesion")).json()) as { csrf_token: string }).csrf_token;
    const directo = await page.request.put("/api/saldo/configuracion", {
      headers: { "X-CSRF-Token": token },
      data: { saldo_inicial_centavos: 125_000_000, fecha_inicio: diaSiguiente(hoy) },
    });
    expect(directo.status()).toBe(400);
  });

  test("con movimientos queda fijo y «Ajustar el saldo» lleva a Saldo", async ({ page }) => {
    await entrar(page, RUTA);
    const saldo = await leerSaldo(page);
    expect(saldo.configuracion).not.toBeNull();
    await expect(hoja(page)).toBeVisible();
    await expect(hoja(page).getByRole("textbox")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Guardar saldo inicial" })).toHaveCount(0);
    const nota = page.getByRole("note");
    await expect(nota).toContainText("El saldo inicial ya no se puede cambiar");
    await expect(nota).toContainText("Ya hay movimientos desde el 1 de ");

    await nota.getByRole("link", { name: "Ajustar el saldo" }).click();
    await expect(page).toHaveURL(/\/app\/saldo$/);
    await expect(page.getByRole("region", { name: "Ajustar el saldo" })).toBeVisible();
  });
});

test.describe("Configurar saldo: configuracion_fija", () => {
  test("un movimiento anterior a la fecha de inicio también la deja fija", async ({ page }) => {
    await page.setViewportSize(TAMANOS.celular);
    await entrar(page, RUTA);
    expect((await page.request.get("/e2e/datos/movimiento-anterior")).ok()).toBe(true);
    // Idempotente: dos veces dejan lo mismo.
    expect((await page.request.get("/e2e/datos/movimiento-anterior")).ok()).toBe(true);
    const saldo = await leerSaldo(page);
    // El desglose y las filas no la ven, pero la API dice que quedó fija.
    expect(saldo.configuracion_fija).toBe(true);
    expect(saldo.desglose).toMatchObject({ ingresos_centavos: 0, gastos_centavos: 0, ajustes_centavos: 0 });
    expect(saldo.del_mes).toEqual([]);

    await page.reload();
    await expect(page.getByRole("note")).toContainText("El saldo inicial ya no se puede cambiar");
    await expect(page.getByRole("button", { name: "Guardar saldo inicial" })).toHaveCount(0);
    await expect(hoja(page).getByRole("textbox")).toHaveCount(0);
    await revisarAccesibilidad(page);
  });

  test("si entra un movimiento con la pantalla abierta, al guardar pasa a fija", async ({ page }) => {
    await page.setViewportSize(TAMANOS.computador);
    await abrirSinSaldo(page);
    // "Otra pestaña" (o la sincronización): ahora hay un movimiento.
    expect((await page.request.get("/e2e/datos/movimiento-anterior")).ok()).toBe(true);

    await hoja(page).getByLabel("Saldo inicial en pesos").fill("1.250.000");
    await hoja(page).getByRole("button", { name: "Guardar saldo inicial" }).click();
    await expect(page.getByRole("note")).toContainText("El saldo inicial ya no se puede cambiar");
    await expect(page.getByRole("button", { name: "Guardar saldo inicial" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Ajustar el saldo" })).toBeVisible();
  });
});

test.describe("Configurar saldo: accesibilidad", () => {
  for (const tamano of Object.keys(TAMANOS) as Tamano[]) {
    for (const modo of ["claro", "oscuro"] as Modo[]) {
      test(`axe sin violaciones (${tamano}, ${modo}): con errores y fijo`, async ({ page }) => {
        await page.setViewportSize(TAMANOS[tamano]);
        await prepararModo(page, modo);
        await abrirSinSaldo(page);
        const { hoy } = await leerSaldo(page);
        await hoja(page).getByLabel("Saldo inicial en pesos").fill("1.25O.000");
        await hoja(page).getByLabel("Fecha de inicio").fill(diaSiguiente(hoy));
        await hoja(page).getByRole("button", { name: "Guardar saldo inicial" }).click();
        await expect(hoja(page).getByLabel("Saldo inicial en pesos")).toHaveAttribute("aria-invalid", "true");
        await revisarAccesibilidad(page);

        expect((await page.request.get("/e2e/datos/reiniciar")).ok()).toBe(true);
        await page.reload();
        await expect(page.getByRole("link", { name: "Ajustar el saldo" })).toBeVisible();
        await revisarAccesibilidad(page);
      });
    }
  }
});
