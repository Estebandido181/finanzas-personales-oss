/**
 * Categorías y reglas (ítem 15) en un navegador de verdad contra la app real
 * y los datos inventados de scripts/servidor_e2e.py: crear, renombrar y
 * borrar una categoría (pasando lo suyo a otra, con confirmación; una vacía
 * al tocar, con «Deshacer», ítem 38), borrar una regla (al tocar, con «Deshacer»),
 * categorizar un ingreso con su regla por quien envía, el número de
 * pendientes de Inicio igual al de la bandeja, accesibilidad con axe y CSP
 * estricta (la vigila `test` de ./ayudas en cada prueba).
 *
 * Estas pruebas cambian datos: cada una empieza y termina con
 * `/e2e/datos/reiniciar` (solo existe en el servidor de pruebas).
 */
import type { Locator, Page } from "@playwright/test";
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

async function reiniciarDatos(page: Page): Promise<void> {
  expect((await page.request.get("/e2e/datos/reiniciar")).ok()).toBe(true);
}

async function abrirCategorias(page: Page): Promise<void> {
  await entrar(page, "/app/categorias");
  await reiniciarDatos(page);
  await page.reload();
  await expect(page.getByRole("region", { name: "Reglas" })).toBeVisible();
}

const hoja = (page: Page, nombre: string) => page.getByRole("region", { name: nombre });

/** Toca una opción (clase, color o ícono) como el dueño: en su cuadro, que es la etiqueta del radio. */
async function elegir(dialogo: Locator, nombre: string): Promise<void> {
  await dialogo.locator("label", { has: dialogo.page().getByRole("radio", { name: nombre, exact: true }) }).click();
  await expect(dialogo.getByRole("radio", { name: nombre, exact: true })).toBeChecked();
}

test.afterEach(async ({ page }) => {
  await reiniciarDatos(page);
});

test.describe("Categorías y reglas", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(TAMANOS.computador);
  });

  test("crear, renombrar y borrar una categoría pasando sus movimientos y reglas a otra", async ({ page }) => {
    await abrirCategorias(page);
    const gasto = hoja(page, "Categorías de gasto");
    await expect(gasto.getByRole("button", { name: "Editar Mascotas" })).toBeVisible();

    // Crear (de ingreso), con color e ícono.
    await page.getByRole("button", { name: "Nueva categoría" }).click();
    let dialogo = page.getByRole("dialog", { name: "Nueva categoría" });
    await elegir(dialogo, "Ingreso");
    await dialogo.getByLabel("Nombre").fill("Arriendos cobrados");
    await elegir(dialogo, "Bronce");
    await elegir(dialogo, "Casa");
    await dialogo.getByRole("button", { name: "Crear categoría" }).click();
    await expect(page.getByRole("status")).toHaveText("Categoría Arriendos cobrados creada.");
    await expect(dialogo).toHaveCount(0);
    await expect(hoja(page, "Categorías de ingreso").getByRole("button", { name: "Editar Arriendos cobrados" })).toBeVisible();

    // Renombrar la propia (y cambiarle el color).
    await gasto.getByRole("button", { name: "Editar Mascotas" }).click();
    dialogo = page.getByRole("dialog", { name: "Editar Mascotas" });
    await dialogo.getByLabel("Nombre").fill("Mascotas y veterinaria");
    await elegir(dialogo, "Ciruela");
    await dialogo.getByRole("button", { name: "Guardar cambios" }).click();
    await expect(page.getByRole("status")).toHaveText("Cambios guardados en Mascotas y veterinaria.");
    // Su regla la sigue teniendo.
    await expect(hoja(page, "Reglas")).toContainText("Si es una compra en «VETERINARIA EJEMPLO», va a Mascotas y veterinaria");

    // Borrar: el destino solo ofrece categorías de gasto; se elige Compras.
    await gasto.getByRole("button", { name: "Editar Mascotas y veterinaria" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Borrar categoría" }).click();
    dialogo = page.getByRole("dialog", { name: "Borrar la categoría Mascotas y veterinaria" });
    await expect(dialogo).toContainText("Mascotas y veterinaria tiene 1 regla. Elige a qué categoría pasa.");
    const destino = dialogo.getByLabel("Pasar movimientos y reglas a");
    await expect(destino).toHaveValue(/\d+/);
    await expect(destino.locator("option:checked")).toHaveText("Otros");
    await expect(destino.locator("option", { hasText: "Sueldo" })).toHaveCount(0);
    await revisarAccesibilidad(page);
    await destino.selectOption({ label: "Compras" });
    await dialogo.getByRole("button", { name: "Borrar y pasar a Compras" }).click();
    await expect(page.getByRole("status")).toHaveText(
      "Categoría Mascotas y veterinaria borrada: 1 regla pasó a Compras.",
    );
    await expect(gasto.getByRole("button", { name: "Editar Mascotas y veterinaria" })).toHaveCount(0);
    await expect(hoja(page, "Reglas")).toContainText("Si es una compra en «VETERINARIA EJEMPLO», va a Compras");

    // Se guardó de verdad.
    await page.reload();
    await expect(hoja(page, "Categorías de ingreso").getByRole("button", { name: "Editar Arriendos cobrados" })).toBeVisible();
    await expect(hoja(page, "Categorías de gasto").getByRole("button", { name: "Editar Mascotas y veterinaria" })).toHaveCount(0);
  });

  test("Escape cierra un diálogo sin cambiar nada", async ({ page }) => {
    await abrirCategorias(page);
    await hoja(page, "Categorías de gasto").getByRole("button", { name: "Editar Antojos" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(hoja(page, "Categorías de gasto").getByRole("button", { name: "Editar Antojos" })).toBeFocused();
  });

  test("borrar una regla es tocar y deshacer: los movimientos conservan su categoría", async ({ page }) => {
    await abrirCategorias(page);
    const reglas = hoja(page, "Reglas");
    const fila = reglas.getByRole("listitem").filter({ hasText: "«SUPERMERCADO LA ESPIGA»" });
    await fila.getByRole("button", { name: "Borrar regla" }).click();
    // Sin pregunta: se borra y se ofrece deshacer.
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const aviso = page.getByRole("status");
    await expect(aviso).toContainText("Regla borrada. Los movimientos que ya categorizó conservan su categoría.");
    await expect(aviso.getByRole("button", { name: "Deshacer" })).toBeVisible();
    await expect(aviso).toBeFocused();
    await expect(reglas).not.toContainText("SUPERMERCADO LA ESPIGA");
    await page.goto("/app/movimientos");
    await expect(
      page.getByRole("listitem").filter({ has: page.getByText("SUPERMERCADO LA ESPIGA", { exact: true }) }).last(),
    ).toContainText("Mercado, por una regla que ya se borró");
  });

  test("Deshacer devuelve la regla igual que estaba", async ({ page }) => {
    await abrirCategorias(page);
    const reglas = hoja(page, "Reglas");
    const filas = reglas.getByRole("listitem");
    const antes = await filas.allInnerTexts();
    const fila = filas.filter({ hasText: "«SUPERMERCADO LA ESPIGA»" });
    await fila.getByRole("button", { name: "Borrar regla" }).click();
    await expect(reglas).not.toContainText("SUPERMERCADO LA ESPIGA");
    await page.getByRole("status").getByRole("button", { name: "Deshacer" }).click();

    await expect(page.getByRole("status")).toHaveText("Regla restaurada.");
    await expect(page.getByRole("button", { name: "Deshacer" })).toHaveCount(0);
    await expect.poll(async () => (await filas.allInnerTexts()).sort()).toEqual([...antes].sort());
    // Y sigue categorizando: el movimiento vuelve a quedar «por regla» al categorizarse otro igual.
    const respuesta = await page.request.get("/api/reglas");
    const { reglas: enServidor } = (await respuesta.json()) as { reglas: { frase: string }[] };
    expect(enServidor.some((r) => r.frase.includes("supermercado la espiga"))).toBe(true);
  });

  test("el aviso de deshacer desaparece al acabarse el tiempo y la regla se queda borrada", async ({ page }) => {
    await abrirCategorias(page);
    // El reloj de la página, para no esperar de verdad los 30 segundos que manda el servidor.
    await page.clock.install();
    const reglas = hoja(page, "Reglas");
    await reglas
      .getByRole("listitem")
      .filter({ hasText: "«SUPERMERCADO LA ESPIGA»" })
      .getByRole("button", { name: "Borrar regla" })
      .click();
    await expect(page.getByRole("status").getByRole("button", { name: "Deshacer" })).toBeVisible();
    await page.clock.fastForward(31_000);
    await expect(page.getByRole("status")).toHaveCount(0);
    await expect(reglas).not.toContainText("SUPERMERCADO LA ESPIGA");
  });

  test("en el celular, el aviso de deshacer queda a la vista al borrar la última regla", async ({ page }) => {
    await page.setViewportSize(TAMANOS.celular);
    await abrirCategorias(page);
    const boton = hoja(page, "Reglas").getByRole("button", { name: "Borrar regla" }).last();
    await boton.scrollIntoViewIfNeeded();
    await boton.click();
    const aviso = page.getByRole("status");
    await expect(aviso.getByRole("button", { name: "Deshacer" })).toBeVisible();
    await expect(aviso).toBeInViewport({ ratio: 1 });
  });

  test("una categoría sin movimientos ni reglas se borra al tocar, y Deshacer la devuelve", async ({ page }) => {
    await abrirCategorias(page);
    const ingreso = hoja(page, "Categorías de ingreso");
    // Préstamos no tiene movimientos ni reglas en los datos de arranque.
    await ingreso.getByRole("button", { name: "Editar Préstamos" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Borrar categoría" }).click();
    // Sin segundo diálogo.
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const aviso = page.getByRole("status");
    await expect(aviso).toContainText("Categoría Préstamos borrada.");
    await expect(aviso).toBeFocused();
    await expect(ingreso.getByRole("button", { name: "Editar Préstamos" })).toHaveCount(0);

    await aviso.getByRole("button", { name: "Deshacer" }).click();
    await expect(page.getByRole("status")).toHaveText("Categoría Préstamos restaurada.");
    await expect(ingreso.getByRole("button", { name: "Editar Préstamos" })).toBeVisible();
    await page.reload();
    await expect(hoja(page, "Categorías de ingreso").getByRole("button", { name: "Editar Préstamos" })).toBeVisible();
  });

  test("una categoría con movimientos o reglas sigue pidiendo confirmación y no se deshace", async ({ page }) => {
    await abrirCategorias(page);
    await hoja(page, "Categorías de gasto").getByRole("button", { name: "Editar Antojos" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Borrar categoría" }).click();
    const dialogo = page.getByRole("dialog", { name: "Borrar la categoría Antojos" });
    await expect(dialogo).toBeVisible();
    await dialogo.getByRole("button", { name: /^Borrar y pasar a/ }).click();
    await expect(page.getByRole("status")).toContainText("Categoría Antojos borrada:");
    await expect(page.getByRole("button", { name: "Deshacer" })).toHaveCount(0);
  });

  test("si el token ya se usó, Deshacer dice con claridad que ya no se puede (410)", async ({ page }) => {
    await abrirCategorias(page);
    const borrada = page.waitForResponse((r) => r.request().method() === "DELETE" && r.url().includes("/api/reglas/"));
    await hoja(page, "Reglas")
      .getByRole("listitem")
      .filter({ hasText: "«SUPERMERCADO LA ESPIGA»" })
      .getByRole("button", { name: "Borrar regla" })
      .click();
    const { deshacer } = (await (await borrada).json()) as { deshacer: { token: string } };
    const csrf = ((await (await page.request.get("/api/sesion")).json()) as { csrf_token: string }).csrf_token;
    // Otra pestaña usa el token primero.
    expect(
      (await page.request.post("/api/deshacer", { headers: { "X-CSRF-Token": csrf }, data: { token: deshacer.token } }))
        .ok(),
    ).toBe(true);
    await page.getByRole("status").getByRole("button", { name: "Deshacer" }).click();
    await expect(page.getByRole("alert")).toContainText("Ya no se puede deshacer: pasó el tiempo o ya se deshizo.");
    await expect(page.getByRole("button", { name: "Deshacer" })).toHaveCount(0);
  });

  test("si algo cambió, Deshacer dice el motivo (409): la regla ya existe de nuevo", async ({ page }) => {
    await abrirCategorias(page);
    await hoja(page, "Reglas")
      .getByRole("listitem")
      .filter({ hasText: "«SUPERMERCADO LA ESPIGA»" })
      .getByRole("button", { name: "Borrar regla" })
      .click();
    await expect(page.getByRole("status").getByRole("button", { name: "Deshacer" })).toBeVisible();
    // Otra pestaña crea una regla igual categorizando una compra de ese comercio.
    const csrf = ((await (await page.request.get("/api/sesion")).json()) as { csrf_token: string }).csrf_token;
    const movimientos = (await (await page.request.get("/api/movimientos")).json()) as {
      movimientos: { id: number; descripcion: string }[];
    };
    const id = movimientos.movimientos.find((m) => m.descripcion === "SUPERMERCADO LA ESPIGA")!.id;
    const categorias = (await (await page.request.get("/api/categorias")).json()) as {
      categorias: { id: number; nombre: string }[];
    };
    const mercado = categorias.categorias.find((c) => c.nombre === "Mercado")!.id;
    const nueva = await page.request.put(`/api/movimientos/${id}/categoria`, {
      headers: { "X-CSRF-Token": csrf },
      data: { categoria_id: mercado, recordar: true },
    });
    expect(nueva.ok()).toBe(true);

    await page.getByRole("status").getByRole("button", { name: "Deshacer" }).click();
    await expect(page.getByRole("alert")).toContainText("No se puede deshacer: ya hay una regla con esas mismas condiciones.");
  });
});

test("un ingreso se categoriza desde la bandeja con su regla, y el número de Inicio es el de la bandeja", async ({
  page,
}) => {
  await page.setViewportSize(TAMANOS.computador);
  await entrar(page);
  await reiniciarDatos(page);
  await page.reload();
  const aviso = page.getByRole("region", { name: /movimientos? sin categorizar$/ });
  await expect(aviso).toHaveAccessibleName("5 movimientos sin categorizar");
  // Los montos de gastos e ingresos pendientes van aparte.
  await expect(aviso).toContainText("Los gastos suman $34.700.");
  await expect(aviso).toContainText("Aparte, los ingresos suman +$400.000.");
  await aviso.getByRole("link", { name: "Categorizar ahora" }).click();
  await expect(page.getByRole("button", { name: "Sin categorizar (5)" })).toBeVisible();

  const carlos = page
    .getByRole("listitem")
    .filter({ has: page.getByText("CARLOS RUIZ EJEMPLO", { exact: true }) })
    .last();
  const opciones = carlos.getByRole("group", { name: "¿En qué categoría va? Toca una:" });
  await expect(opciones.getByRole("button")).toHaveText(["Sueldo", "Préstamos", "Otros ingresos"]);
  await opciones.getByRole("button", { name: "Préstamos" }).click();
  await expect(carlos.getByRole("status")).toContainText("Guardado en Préstamos.");
  await carlos.getByRole("button", { name: "Ingresos de CARLOS RUIZ EJEMPLO" }).click();
  await expect(carlos.getByRole("status")).toHaveText(
    "Regla creada: ingresos de CARLOS RUIZ EJEMPLO van a Préstamos.",
  );
  await expect(page.getByRole("button", { name: "Sin categorizar (4)" })).toBeVisible();

  // La regla aparece en "Categorías y reglas" y el número de Inicio bajó igual.
  await page.goto("/app/categorias");
  await expect(hoja(page, "Reglas")).toContainText("Si es un ingreso de «CARLOS RUIZ EJEMPLO», va a Préstamos");
  await page.goto("/app/");
  await expect(aviso).toHaveAccessibleName("4 movimientos sin categorizar");
  await expect(aviso).toContainText("Suman $34.700.");
  await expect(aviso).not.toContainText("ingresos suman");
});

test("todo lo que se toca mide al menos 44 × 44 px", async ({ page }) => {
  await page.setViewportSize(TAMANOS.celular);
  await abrirCategorias(page);
  const medir = async (ambito: string) => {
    for (const elemento of await page.locator(`${ambito} a, ${ambito} button, ${ambito} select, ${ambito} input:not([type=radio]), ${ambito} label:has(input[type=radio])`).all()) {
      const caja = (await elemento.boundingBox())!;
      const nombre = (await elemento.getAttribute("aria-label")) ?? (await elemento.innerText());
      expect(caja.height, nombre).toBeGreaterThanOrEqual(44);
      expect(caja.width, nombre).toBeGreaterThanOrEqual(44);
    }
  };
  await medir("main");
  await page.getByRole("button", { name: "Nueva categoría" }).click();
  await medir("dialog");
  await page.getByRole("dialog").getByRole("button", { name: "Cancelar" }).click();
  await hoja(page, "Categorías de gasto").getByRole("button", { name: "Editar Antojos" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Borrar categoría" }).click();
  await medir("dialog");
  await page.getByRole("dialog").getByRole("button", { name: "Cancelar" }).click();
  // El aviso de deshacer (ítem 38) también se toca con el dedo.
  await hoja(page, "Reglas").getByRole("button", { name: "Borrar regla" }).first().click();
  await expect(page.getByRole("status").getByRole("button", { name: "Deshacer" })).toBeVisible();
  await medir('[role="status"]');
});

// Accesibilidad: la pantalla, el formulario y el diálogo de borrar; celular y computador; claro y oscuro.
for (const tamano of Object.keys(TAMANOS) as Tamano[]) {
  for (const modo of ["claro", "oscuro"] as Modo[]) {
    test(`accesibilidad de Categorías y reglas ${tamano} ${modo}`, async ({ page }) => {
      await page.setViewportSize(TAMANOS[tamano]);
      await prepararModo(page, modo);
      await abrirCategorias(page);
      await revisarAccesibilidad(page);
      await page.getByRole("button", { name: "Nueva categoría" }).click();
      // Con el error del campo a la vista.
      await page.getByRole("dialog").getByRole("button", { name: "Crear categoría" }).click();
      await expect(page.getByRole("dialog")).toContainText("Escribe el nombre de la categoría.");
      await revisarAccesibilidad(page);
      await page.getByRole("dialog").getByRole("button", { name: "Cancelar" }).click();
      await hoja(page, "Categorías de gasto").getByRole("button", { name: "Editar Antojos" }).click();
      await page.getByRole("dialog").getByRole("button", { name: "Borrar categoría" }).click();
      await expect(page.getByRole("dialog", { name: "Borrar la categoría Antojos" })).toBeVisible();
      await revisarAccesibilidad(page);
      await page.getByRole("dialog").getByRole("button", { name: "Cancelar" }).click();
      // El aviso de deshacer (ítem 38) y su error de «ya no se puede».
      await hoja(page, "Reglas")
        .getByRole("listitem")
        .filter({ hasText: "«SUPERMERCADO LA ESPIGA»" })
        .getByRole("button", { name: "Borrar regla" })
        .click();
      await expect(page.getByRole("status").getByRole("button", { name: "Deshacer" })).toBeVisible();
      await revisarAccesibilidad(page);
      await page.route("**/api/deshacer", (ruta) =>
        ruta.fulfill({
          status: 410,
          contentType: "application/json",
          body: JSON.stringify({ detalle: "Ya no se puede deshacer: pasó el tiempo o ya se deshizo." }),
        }),
      );
      await page.getByRole("button", { name: "Deshacer" }).click();
      await expect(page.getByRole("alert")).toBeVisible();
      await revisarAccesibilidad(page);
    });
  }
}
