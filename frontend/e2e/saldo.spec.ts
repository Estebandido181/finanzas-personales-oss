/**
 * Saldo, ingresos y ajustes (ítem 16) en un navegador de verdad contra la app
 * real y los datos inventados de scripts/servidor_e2e.py: borrar un ingreso
 * es tocar y deshacer (ítem 38): baja el saldo exactamente en su monto y
 * «Deshacer» lo restaura (o dice con claridad que ya no se puede); un ajuste, un ingreso de Gmail o uno
 * anterior al último ajuste no muestran «Borrar ingreso» (y la API tampoco
 * deja borrarlos); un 409 se muestra sin tocar la lista; accesibilidad con
 * axe y CSP estricta (la vigila `test` de ./ayudas en cada prueba).
 *
 * Estas pruebas cambian datos: cada una empieza con `/e2e/datos/saldo` y
 * termina con `/e2e/datos/reiniciar` (solo existen en el servidor de pruebas).
 */
import type { APIRequestContext, Page } from "@playwright/test";
import type { components } from "../src/api/esquema";
import { pesos } from "../src/compartido/formatos/formato";
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

type Saldo = components["schemas"]["Saldo"];

/** Los de scripts/servidor_e2e.py (inventados). */
const BORRABLE = { descripcion: "Efectivo venta de libros EJEMPLO", centavos: 8_500_050 };
const ANTERIOR_AL_AJUSTE = "Efectivo arriendo garaje EJEMPLO";
const DE_GMAIL = "EMPRESA EJEMPLO S.A.S.";

async function abrirSaldo(page: Page): Promise<void> {
  await entrar(page, "/app/saldo");
  expect((await page.request.get("/e2e/datos/saldo")).ok()).toBe(true);
  await page.reload();
  await expect(page.getByRole("region", { name: "Registrar un ingreso" })).toBeVisible();
}

/** Lo que dice la API, con la cookie de la sesión de la página. */
async function leerSaldo(request: APIRequestContext): Promise<Saldo> {
  const r = await request.get("/api/saldo");
  expect(r.ok()).toBe(true);
  return (await r.json()) as Saldo;
}

async function tokenCsrf(request: APIRequestContext): Promise<string> {
  return ((await (await request.get("/api/sesion")).json()) as { csrf_token: string }).csrf_token;
}

const hojaSaldo = (page: Page) => page.getByRole("region", { name: "Saldo actual" });
const hojaLista = (page: Page) => page.getByRole("region", { name: /^Ingresos y ajustes de / });
const fila = (page: Page, descripcion: string) =>
  hojaLista(page).getByRole("listitem").filter({ has: page.getByText(descripcion, { exact: true }) });

test.afterEach(async ({ page }) => {
  expect((await page.request.get("/e2e/datos/reiniciar")).ok()).toBe(true);
});

test.describe("Saldo", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(TAMANOS.computador);
  });

  test("borrar un ingreso a mano es tocar y deshacer: baja el saldo exactamente en su monto", async ({ page }) => {
    await abrirSaldo(page);
    const antes = await leerSaldo(page.request);
    await expect(hojaSaldo(page)).toContainText(pesos(antes.saldo_centavos!));
    const filasAntes = await hojaLista(page).getByRole("listitem").count();

    await fila(page, BORRABLE.descripcion).getByRole("button", { name: `Borrar ingreso ${BORRABLE.descripcion}` }).click();
    // Sin pregunta: se borra y se ofrece deshacer.
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const aviso = hojaLista(page).getByRole("status");
    await expect(aviso).toContainText("Ingreso borrado. El saldo bajó $85.000,50.");
    await expect(aviso.getByRole("button", { name: "Deshacer" })).toBeVisible();
    await expect(aviso).toBeFocused();
    const despues = await leerSaldo(page.request);
    expect(despues.saldo_centavos).toBe(antes.saldo_centavos! - BORRABLE.centavos);
    expect(despues.desglose!.ingresos_centavos).toBe(antes.desglose!.ingresos_centavos - BORRABLE.centavos);
    await expect(hojaSaldo(page)).toContainText(pesos(despues.saldo_centavos!));
    await expect(fila(page, BORRABLE.descripcion)).toHaveCount(0);
    await expect(hojaLista(page).getByRole("listitem")).toHaveCount(filasAntes - 1);
  });

  test("Deshacer restaura el ingreso y el saldo como estaban, y el aviso se va", async ({ page }) => {
    await abrirSaldo(page);
    const antes = await leerSaldo(page.request);
    await fila(page, BORRABLE.descripcion).getByRole("button", { name: /^Borrar ingreso/ }).click();
    const aviso = hojaLista(page).getByRole("status");
    await aviso.getByRole("button", { name: "Deshacer" }).click();

    await expect(aviso).toContainText(`Ingreso restaurado. El saldo volvió a ${pesos(antes.saldo_centavos!)}.`);
    await expect(aviso.getByRole("button", { name: "Deshacer" })).toHaveCount(0);
    // El estado anterior, en la pantalla y en el servidor.
    await expect(fila(page, BORRABLE.descripcion)).toHaveCount(1);
    await expect(fila(page, BORRABLE.descripcion).getByRole("button", { name: /^Borrar ingreso/ })).toBeVisible();
    await expect(hojaSaldo(page)).toContainText(pesos(antes.saldo_centavos!));
    const despues = await leerSaldo(page.request);
    expect(despues.saldo_centavos).toBe(antes.saldo_centavos);
    expect(despues.desglose).toEqual(antes.desglose);
    expect(despues.del_mes.map((f) => [f.descripcion, f.monto_centavos])).toEqual(
      antes.del_mes.map((f) => [f.descripcion, f.monto_centavos]),
    );
  });

  test("el aviso de deshacer desaparece al acabarse el tiempo, y lo borrado se queda borrado", async ({ page }) => {
    await abrirSaldo(page);
    // El reloj de la página, para no esperar de verdad los 30 segundos que manda el servidor.
    await page.clock.install();
    const antes = await leerSaldo(page.request);
    await fila(page, BORRABLE.descripcion).getByRole("button", { name: /^Borrar ingreso/ }).click();
    const aviso = hojaLista(page).getByRole("status");
    await expect(aviso.getByRole("button", { name: "Deshacer" })).toBeVisible();
    await page.clock.fastForward(31_000);
    await expect(hojaLista(page).getByRole("status")).toHaveCount(0);
    await expect(fila(page, BORRABLE.descripcion)).toHaveCount(0);
    expect((await leerSaldo(page.request)).saldo_centavos).toBe(antes.saldo_centavos! - BORRABLE.centavos);
  });

  test("si el token ya se usó, Deshacer dice con claridad que ya no se puede (410)", async ({ page }) => {
    await abrirSaldo(page);
    const antes = await leerSaldo(page.request);
    const borrado = page.waitForResponse((r) => r.request().method() === "DELETE" && r.url().includes("/api/ingresos/"));
    await fila(page, BORRABLE.descripcion).getByRole("button", { name: /^Borrar ingreso/ }).click();
    const { deshacer } = (await (await borrado).json()) as { deshacer: { token: string } };
    // Otra pestaña usa el token primero.
    const otra = await page.request.post("/api/deshacer", {
      headers: { "X-CSRF-Token": await tokenCsrf(page.request) },
      data: { token: deshacer.token },
    });
    expect(otra.ok()).toBe(true);

    const aviso = hojaLista(page).getByRole("status");
    await aviso.getByRole("button", { name: "Deshacer" }).click();
    await expect(hojaLista(page).getByRole("alert")).toContainText(
      "Ya no se puede deshacer: pasó el tiempo o ya se deshizo.",
    );
    await expect(hojaLista(page).getByRole("button", { name: "Deshacer" })).toHaveCount(0);
    // El ingreso quedó restaurado una sola vez (por la otra pestaña).
    expect((await leerSaldo(page.request)).saldo_centavos).toBe(antes.saldo_centavos);
  });

  test("si un ajuste posterior lo impide, Deshacer dice el motivo (409) y no cambia nada", async ({ page }) => {
    await abrirSaldo(page);
    const antes = await leerSaldo(page.request);
    await fila(page, BORRABLE.descripcion).getByRole("button", { name: /^Borrar ingreso/ }).click();
    const aviso = hojaLista(page).getByRole("status");
    await expect(aviso.getByRole("button", { name: "Deshacer" })).toBeVisible();
    const sinIngreso = antes.saldo_centavos! - BORRABLE.centavos;
    // Otra pestaña ajusta el saldo: el ingreso ya quedaría antes del último ajuste.
    const ajuste = await page.request.post("/api/ajustes", {
      headers: { "X-CSRF-Token": await tokenCsrf(page.request) },
      data: { saldo_real_centavos: sinIngreso - 100 },
    });
    expect(ajuste.ok()).toBe(true);

    await aviso.getByRole("button", { name: "Deshacer" }).click();
    await expect(hojaLista(page).getByRole("alert")).toContainText("No se puede deshacer");
    await expect(fila(page, BORRABLE.descripcion)).toHaveCount(0);
    expect((await leerSaldo(page.request)).saldo_centavos).toBe(sinIngreso - 100);
  });

  test("en el celular, el aviso de deshacer queda a la vista al borrar un renglón de la lista", async ({ page }) => {
    await page.setViewportSize(TAMANOS.celular);
    await abrirSaldo(page);
    const boton = fila(page, BORRABLE.descripcion).getByRole("button", { name: /^Borrar ingreso/ });
    await boton.scrollIntoViewIfNeeded();
    await boton.click();
    const aviso = hojaLista(page).getByRole("status");
    await expect(aviso.getByRole("button", { name: "Deshacer" })).toBeVisible();
    await expect(aviso).toBeInViewport({ ratio: 1 });
  });

  test("la cuenta del aviso se pausa con el cursor encima y sigue al salir", async ({ page }) => {
    await abrirSaldo(page);
    await page.clock.install();
    await fila(page, BORRABLE.descripcion).getByRole("button", { name: /^Borrar ingreso/ }).click();
    const aviso = hojaLista(page).getByRole("status");
    await expect(aviso.getByRole("button", { name: "Deshacer" })).toBeVisible();
    await aviso.hover();
    await page.clock.fastForward(60_000);
    await expect(aviso.getByRole("button", { name: "Deshacer" })).toBeVisible();
    await page.mouse.move(0, 0);
    await page.clock.fastForward(31_000);
    await expect(hojaLista(page).getByRole("status")).toHaveCount(0);
  });

  test("un ajuste, un ingreso de Gmail o uno anterior al último ajuste no se pueden borrar", async ({ page }) => {
    await abrirSaldo(page);
    const lista = hojaLista(page);
    // Solo el ingreso a mano posterior a todos los ajustes lleva el botón.
    await expect(lista.getByRole("button", { name: /^Borrar ingreso/ })).toHaveCount(1);
    await expect(fila(page, BORRABLE.descripcion).getByRole("button")).toHaveCount(1);
    for (const descripcion of [ANTERIOR_AL_AJUSTE, DE_GMAIL, "Ajuste de saldo", "Efectivo venta bicicleta"]) {
      await expect(fila(page, descripcion).first()).toBeVisible();
      await expect(fila(page, descripcion).getByRole("button")).toHaveCount(0);
    }

    // Ni siquiera llamando directo a la API: 409 y la base no cambia.
    const saldo = await leerSaldo(page.request);
    const token = await tokenCsrf(page.request);
    const noBorrables = saldo.del_mes.filter((f) =>
      [ANTERIOR_AL_AJUSTE, DE_GMAIL, "Ajuste de saldo"].includes(f.descripcion),
    );
    expect(new Set(noBorrables.map((f) => f.descripcion)).size).toBe(3);
    for (const f of noBorrables) {
      expect(f.se_puede_borrar).toBe(false);
      const r = await page.request.delete(`/api/ingresos/${f.id}`, { headers: { "X-CSRF-Token": token } });
      expect(r.status(), f.descripcion).toBe(409);
    }
    const despues = await leerSaldo(page.request);
    expect(despues.saldo_centavos).toBe(saldo.saldo_centavos);
    expect(despues.del_mes).toEqual(saldo.del_mes);
  });

  test("un 409 de la API muestra el mensaje y deja la lista igual", async ({ page }) => {
    await abrirSaldo(page);
    const antes = await leerSaldo(page.request);

    // Desde "otra pestaña", un ajuste nuevo: el ingreso ya no se puede borrar,
    // pero esta pantalla todavía muestra el botón.
    const ajuste = await page.request.post("/api/ajustes", {
      headers: { "X-CSRF-Token": await tokenCsrf(page.request) },
      data: { saldo_real_centavos: antes.saldo_centavos! - 100 },
    });
    expect(ajuste.ok()).toBe(true);

    await fila(page, BORRABLE.descripcion).getByRole("button", { name: /^Borrar ingreso/ }).click();
    await expect(hojaLista(page).getByRole("alert")).toContainText("Este ingreso es anterior al último ajuste");
    await expect(hojaLista(page).getByRole("button", { name: "Deshacer" })).toHaveCount(0);

    // El ingreso sigue en la base y la pantalla se vuelve a leer: el botón ya no aparece.
    const despues = await leerSaldo(page.request);
    expect(despues.del_mes.some((f) => f.descripcion === BORRABLE.descripcion)).toBe(true);
    await expect(fila(page, BORRABLE.descripcion)).toHaveCount(1);
    await expect(fila(page, BORRABLE.descripcion).getByRole("button")).toHaveCount(0);
  });

  test("un 404 (ya se borró en otra pestaña) lo dice y la fila se va", async ({ page }) => {
    await abrirSaldo(page);
    const id = (await leerSaldo(page.request)).del_mes.find((f) => f.descripcion === BORRABLE.descripcion)!.id;
    const otra = await page.request.delete(`/api/ingresos/${id}`, {
      headers: { "X-CSRF-Token": await tokenCsrf(page.request) },
    });
    expect(otra.ok()).toBe(true);

    await fila(page, BORRABLE.descripcion).getByRole("button", { name: /^Borrar ingreso/ }).click();
    await expect(hojaLista(page).getByRole("alert")).toContainText("Ese ingreso ya no existe.");
    await expect(fila(page, BORRABLE.descripcion)).toHaveCount(0);
  });

  test("registrar un ingreso y borrarlo deja el saldo como estaba", async ({ page }) => {
    await abrirSaldo(page);
    const antes = await leerSaldo(page.request);
    const hoja = page.getByRole("region", { name: "Registrar un ingreso" });
    await hoja.getByLabel("Monto en pesos").fill("12.345,67");
    await hoja.getByLabel("Descripción (opcional)").fill("Efectivo prueba EJEMPLO");
    await hoja.getByRole("button", { name: "Registrar ingreso" }).click();
    await expect(hoja.getByRole("status")).toHaveText("Ingreso de $12.345,67 registrado.");
    const conIngreso = await leerSaldo(page.request);
    expect(conIngreso.saldo_centavos).toBe(antes.saldo_centavos! + 1_234_567);
    await expect(hojaSaldo(page)).toContainText(pesos(conIngreso.saldo_centavos!));

    await fila(page, "Efectivo prueba EJEMPLO").getByRole("button", { name: /^Borrar ingreso/ }).click();
    await expect(hojaLista(page).getByRole("status")).toContainText("Ingreso borrado. El saldo bajó $12.345,67.");
    expect((await leerSaldo(page.request)).saldo_centavos).toBe(antes.saldo_centavos);
  });

  test("ajustar el saldo: una O en lugar de un cero se explica en el campo", async ({ page }) => {
    await abrirSaldo(page);
    const hoja = page.getByRole("region", { name: "Ajustar el saldo" });
    const campo = hoja.getByLabel("Saldo real en Bancolombia");
    await campo.fill("4.73O.000");
    await hoja.getByRole("button", { name: "Ajustar saldo" }).click();
    await expect(campo).toHaveAttribute("aria-invalid", "true");
    await expect(campo).toHaveAccessibleDescription(
      "Ese monto tiene una letra O en lugar de un cero. Escríbelo solo con números, por ejemplo 4.730.000.",
    );
    await expect(campo).toBeFocused();
  });
});

test.describe("Saldo: accesibilidad", () => {
  for (const tamano of Object.keys(TAMANOS) as Tamano[]) {
    for (const modo of ["claro", "oscuro"] as Modo[]) {
      test(`axe sin violaciones (${tamano}, ${modo}), con el desglose abierto y con el aviso de deshacer`, async ({
        page,
      }) => {
        await page.setViewportSize(TAMANOS[tamano]);
        await prepararModo(page, modo);
        await abrirSaldo(page);
        await page.getByText("Ver cómo se calcula").click();
        await expect(hojaSaldo(page).getByText("Saldo inicial")).toBeVisible();
        // Error de campo a la vista (contraste del rojo sobre la hoja).
        const ajuste = page.getByRole("region", { name: "Ajustar el saldo" });
        await ajuste.getByLabel("Saldo real en Bancolombia").fill("4.73O.000");
        await ajuste.getByRole("button", { name: "Ajustar saldo" }).click();
        await revisarAccesibilidad(page);

        await fila(page, BORRABLE.descripcion).getByRole("button", { name: /^Borrar ingreso/ }).click();
        await expect(hojaLista(page).getByRole("button", { name: "Deshacer" })).toBeVisible();
        await revisarAccesibilidad(page);
        // Con el error de «ya no se puede deshacer» a la vista (contraste del aviso de error).
        await page.route("**/api/deshacer", (ruta) =>
          ruta.fulfill({
            status: 410,
            contentType: "application/json",
            body: JSON.stringify({ detalle: "Ya no se puede deshacer: pasó el tiempo o ya se deshizo." }),
          }),
        );
        await hojaLista(page).getByRole("button", { name: "Deshacer" }).click();
        await expect(hojaLista(page).getByRole("alert")).toBeVisible();
        await revisarAccesibilidad(page);
      });
    }
  }
});
