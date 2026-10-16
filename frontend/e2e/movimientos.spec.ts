/**
 * Movimientos y "Sin categorizar" (ítem 14) en un navegador de verdad contra
 * la app real y los datos inventados de scripts/servidor_e2e.py: el flujo
 * completo (de Inicio a la bandeja, categorizar con un toque, crear la regla
 * con otro, corregir uno categorizado por regla), los filtros, accesibilidad
 * con axe y CSP estricta (la vigila `test` de ./ayudas en cada prueba).
 *
 * Estas pruebas cambian datos: cada una empieza con `/e2e/datos/reiniciar`
 * (solo existe en el servidor de pruebas) y deja los datos como estaban.
 */
import type { Page } from "@playwright/test";
import { mesActualColombia, nombreMes, nombreMesCorto } from "../src/compartido/formatos/formato";
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
const MES = nombreMes(ACTUAL);
const OPCIONES = "¿En qué categoría va? Toca una:";

/** La fila de un movimiento (el `li` más interno que tiene su descripción). */
function fila(page: Page, descripcion: string) {
  return page
    .getByRole("listitem")
    .filter({ has: page.getByText(descripcion, { exact: true }) })
    .last();
}

async function reiniciarDatos(page: Page): Promise<void> {
  const r = await page.request.get("/e2e/datos/reiniciar");
  expect(r.ok()).toBe(true);
}

async function abrirMovimientos(page: Page, busqueda = ""): Promise<void> {
  await entrar(page, `/app/movimientos${busqueda}`);
  await reiniciarDatos(page);
  await page.reload();
  await expect(page.getByRole("list", { name: `Movimientos de ${MES}, por día` })).toBeVisible();
}

test.afterEach(async ({ page }) => {
  await reiniciarDatos(page);
});

test.describe("Movimientos", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(TAMANOS.computador);
  });

  test("flujo completo: de Inicio a la bandeja, un toque para categorizar, otro para la regla, y corregir", async ({
    page,
  }) => {
    await entrar(page);
    await reiniciarDatos(page);
    await page.reload();
    // El número de Inicio es el de la bandeja (todos los meses): 3 de este mes y, del
    // anterior, un gasto y un ingreso (ítem 15: los ingresos sin categoría también cuentan).
    const avisoInicio = page.getByRole("region", { name: /movimientos? sin categorizar$/ });
    await expect(avisoInicio).toHaveAccessibleName("5 movimientos sin categorizar");
    await avisoInicio.getByRole("link", { name: "Categorizar ahora" }).click();
    await expect(page).toHaveURL(/\/app\/movimientos\?ver=sin-categorizar$/);
    await expect(page.getByRole("heading", { level: 1, name: "Movimientos" })).toBeFocused();
    const mostrar = page.getByRole("group", { name: "Mostrar" });
    await expect(mostrar.getByRole("button", { name: "Sin categorizar (5)" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // Una sola bandeja, de todos los meses: sin selector de mes ni "Gastado".
    await expect(page.getByText("Sin categorizar · todos los meses")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Cambiar de mes" })).toHaveCount(0);
    const bandeja = page.getByRole("list", { name: "Movimientos sin categorizar, por día" });
    await expect(bandeja).not.toContainText("Gastado");
    await expect(fila(page, "CAFETERIA EL PARQUE EJEMPLO")).toBeVisible();
    // En la bandeja, cada pendiente ya muestra sus opciones: un toque basta.
    await expect(page.getByRole("group", { name: OPCIONES })).toHaveCount(5);

    const panaderia = fila(page, "PANADERIA EL TRIGAL");
    await panaderia.getByRole("button", { name: "Mercado" }).click();
    const aviso = panaderia.getByRole("status");
    await expect(aviso).toContainText("Guardado en Mercado.");
    await expect(aviso).toContainText("¿Categorizar igual las siguientes? Crea una regla con un toque:");
    await expect(aviso).toBeFocused();
    await expect(mostrar.getByRole("button", { name: "Sin categorizar (4)" })).toBeVisible();
    await expect(panaderia).toContainText("Mercado, a mano");

    // Un toque más: la regla.
    await aviso.getByRole("button", { name: "Compras en PANADERIA EL TRIGAL" }).click();
    await expect(panaderia.getByRole("status")).toHaveText(
      "Regla creada: compras en PANADERIA EL TRIGAL van a Mercado.",
    );
    await revisarAccesibilidad(page);

    // En la lista completa: a mano, y la regla quedó guardada.
    await mostrar.getByRole("button", { name: "Todos" }).click();
    await expect(page).toHaveURL(/\/app\/movimientos$/);
    await expect(fila(page, "PANADERIA EL TRIGAL")).toContainText("Mercado, a mano");
    const reglas = await (await page.request.get("/api/reglas")).json();
    expect(reglas.reglas.map((r: { texto: string }) => r.texto)).toContain("panaderia el trigal");

    // Corregir uno categorizado por regla: queda a mano y la regla no cambia.
    const espiga = fila(page, "SUPERMERCADO LA ESPIGA");
    await expect(espiga).toContainText("Mercado, por regla: compra en «SUPERMERCADO LA ESPIGA»");
    await espiga.getByRole("button", { name: "Cambiar categoría de SUPERMERCADO LA ESPIGA" }).click();
    const opciones = espiga.getByRole("group", { name: OPCIONES });
    await expect(opciones.getByRole("button", { name: "Mercado" })).toHaveAttribute("aria-pressed", "true");
    await expect(opciones.getByRole("button").last()).toHaveText("Otros");
    await opciones.getByRole("button", { name: "Restaurantes" }).click();
    await expect(espiga.getByRole("status")).toHaveText(
      "Cambiado a Restaurantes.Ahora está categorizado a mano; la regla sigue igual para los demás.",
    );
    await expect(espiga).toContainText("Restaurantes, a mano");
    await revisarAccesibilidad(page);

    // Se guardó de verdad.
    await page.reload();
    await expect(fila(page, "SUPERMERCADO LA ESPIGA")).toContainText("Restaurantes, a mano");
    await expect(fila(page, "*3000000001")).toContainText(
      "Transporte, por regla: transferencia a «*3000000001»",
    );
    await expect(fila(page, "PAPELERIA EJEMPLO")).toContainText(
      "Otros, no se sabe si fue a mano o por regla",
    );
    const reglasDespues = await (await page.request.get("/api/reglas")).json();
    const espigaRegla = reglasDespues.reglas.find((r: { texto: string }) => r.texto === "supermercado la espiga");
    expect(espigaRegla.categoria.nombre).toBe("Mercado");
  });

  test("en la lista, el primer pendiente ya muestra las opciones y el siguiente se abre con «Categorizar»", async ({
    page,
  }) => {
    await abrirMovimientos(page);
    await expect(fila(page, "PANADERIA EL TRIGAL").getByRole("group", { name: OPCIONES })).toBeVisible();
    const laura = fila(page, "LAURA GÓMEZ EJEMPLO");
    await expect(laura.getByRole("group", { name: OPCIONES })).toHaveCount(0);
    await laura.getByRole("button", { name: "Categorizar LAURA GÓMEZ EJEMPLO" }).click();
    await laura.getByRole("button", { name: "Restaurantes" }).click();
    await expect(laura.getByRole("status")).toContainText("Guardado en Restaurantes.");
    await expect(
      laura.getByRole("button", { name: "Transferencias a LAURA GÓMEZ EJEMPLO" }),
    ).toBeVisible();
  });

  test("filtros por tipo y por categoría, en la dirección; y un filtro sin resultados", async ({ page }) => {
    await abrirMovimientos(page);
    await page.getByRole("button", { name: "Ingresos" }).click();
    await expect(page).toHaveURL(/ver=ingresos$/);
    await expect(fila(page, "EMPRESA EJEMPLO S.A.S.")).toContainText("+$4.800.000");
    await expect(page.getByText("PANADERIA EL TRIGAL", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Ingresos" })).toBeFocused();

    await page.getByLabel("Categoría", { exact: true }).selectOption({ label: "Salud" });
    await expect(page).toHaveURL(/\/app\/movimientos\?categoria=\d+$/);
    await expect(fila(page, "DROGUERIA EJEMPLO")).toContainText("Salud, a mano");
    await expect(page.getByRole("list", { name: `Movimientos de ${MES}, por día` }).getByRole("heading")).toHaveCount(1);
    await expect(page.getByRole("button", { name: "Todos" })).toHaveAttribute("aria-pressed", "true");

    // El mes anterior no tiene nada de Salud: lo dice y ofrece ver todos.
    await page
      .getByRole("navigation", { name: "Cambiar de mes" })
      .getByRole("link", { name: nombreMesCorto(ANTERIOR) })
      .click();
    await expect(page).toHaveURL(new RegExp(`\\?mes=${ANTERIOR}&categoria=\\d+$`));
    await expect(page.getByRole("heading", { level: 2, name: "Nada con este filtro" })).toBeVisible();
    await expect(page.getByText(/^No hay movimientos de Salud en /)).toBeVisible();
    await revisarAccesibilidad(page);
    await page.getByRole("link", { name: "Ver todos los movimientos" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Nada con este filtro" })).toHaveCount(0);
    await expect(page.getByLabel("Categoría", { exact: true })).toHaveValue("");
  });

  test("todo lo que se toca mide al menos 44 × 44 px", async ({ page }) => {
    await page.setViewportSize(TAMANOS.celular);
    await abrirMovimientos(page);
    for (const elemento of await page.locator("main a, main button, main select").all()) {
      const caja = (await elemento.boundingBox())!;
      expect(caja.height, await elemento.innerText()).toBeGreaterThanOrEqual(44);
    }
  });
});

async function abrirBandeja(page: Page): Promise<void> {
  await entrar(page, "/app/movimientos?ver=sin-categorizar");
  await reiniciarDatos(page);
  await page.reload();
  await expect(page.getByRole("list", { name: "Movimientos sin categorizar, por día" })).toBeVisible();
}

// Ítem 17: al categorizar se ofrecen las reglas que manda la API (por texto, por
// monto y las dos cosas juntas en transferencias e ingresos; en compras, solo por texto).
test.describe("Reglas combinables", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(TAMANOS.computador);
  });

  test("una regla «transferencia + $3.200» categoriza sola las de ese monto, sin importar el destino", async ({
    page,
  }) => {
    await entrar(page, "/app/movimientos?ver=sin-categorizar");
    await reiniciarDatos(page);
    expect((await page.request.get("/e2e/datos/buses")).ok()).toBe(true);
    await page.reload();
    await expect(page.getByRole("button", { name: "Sin categorizar (7)" })).toBeVisible();

    const bus = fila(page, "*3000000002");
    await bus.getByRole("button", { name: "Transporte" }).click();
    const aviso = bus.getByRole("status");
    await expect(aviso).toContainText("Guardado en Transporte.");
    await expect(aviso.getByRole("button")).toHaveText([
      "Transferencias a *3000000002",
      "Transferencias de $3.200",
      "Las dos cosas juntas",
    ]);
    await revisarAccesibilidad(page);
    await aviso.getByRole("button", { name: "Transferencias de $3.200" }).click();
    await expect(bus.getByRole("status")).toHaveText("Regla creada: transferencias de $3.200 van a Transporte.");
    // La otra, a otra cuenta, salió de la bandeja: la categorizó la regla.
    await expect(page.getByRole("button", { name: "Sin categorizar (5)" })).toBeVisible();
    await expect(page.getByText("*3000000003", { exact: true })).toHaveCount(0);

    await page.getByRole("group", { name: "Mostrar" }).getByRole("button", { name: "Todos" }).click();
    await expect(fila(page, "*3000000003")).toContainText("Transporte, por regla: transferencia de $3.200");
    await expect(fila(page, "*3000000002")).toContainText("Transporte, a mano");
    // La regla de la v1 (por texto) sigue igual.
    await expect(fila(page, "*3000000001")).toContainText("Transporte, por regla: transferencia a «*3000000001»");
    const { reglas } = await (await page.request.get("/api/reglas")).json();
    const creada = reglas.find((r: { monto_centavos: number | null }) => r.monto_centavos === 320_000);
    expect(creada).toMatchObject({ condiciones: "monto", texto: null, tipo_movimiento: "transferencia" });

    await page.goto("/app/categorias");
    await expect(page.getByRole("region", { name: "Reglas" })).toContainText(
      "Si es una transferencia de $3.200, va a Transporte",
    );
    await revisarAccesibilidad(page);
  });

  test("una compra solo ofrece la regla por texto", async ({ page }) => {
    await abrirBandeja(page);
    const panaderia = fila(page, "PANADERIA EL TRIGAL");
    await panaderia.getByRole("button", { name: "Mercado" }).click();
    const aviso = panaderia.getByRole("status");
    await expect(aviso).toContainText("Guardado en Mercado.");
    await expect(aviso.getByRole("button")).toHaveText(["Compras en PANADERIA EL TRIGAL"]);
    await aviso.getByRole("button", { name: "Compras en PANADERIA EL TRIGAL" }).click();
    await expect(panaderia.getByRole("status")).toHaveText("Regla creada: compras en PANADERIA EL TRIGAL van a Mercado.");
    const { reglas } = await (await page.request.get("/api/reglas")).json();
    expect(reglas.find((r: { texto: string | null }) => r.texto === "panaderia el trigal")).toMatchObject({
      condiciones: "texto",
      monto_centavos: null,
    });
  });

  test("un ingreso ofrece las tres reglas; «Las dos cosas juntas» crea la de quien envía y monto", async ({ page }) => {
    await abrirBandeja(page);
    const carlos = fila(page, "CARLOS RUIZ EJEMPLO");
    await carlos.getByRole("button", { name: "Préstamos" }).click();
    const aviso = carlos.getByRole("status");
    await expect(aviso.getByRole("button")).toHaveText([
      "Ingresos de CARLOS RUIZ EJEMPLO",
      "Ingresos de $400.000",
      "Las dos cosas juntas",
    ]);
    // Al oírlo, "Las dos cosas juntas" dice cuáles son.
    await aviso
      .getByRole("button", { name: "Las dos cosas juntas: ingresos de «CARLOS RUIZ EJEMPLO» por $400.000" })
      .click();
    await expect(carlos.getByRole("status")).toHaveText(
      "Regla creada: ingresos de «CARLOS RUIZ EJEMPLO» por $400.000 van a Préstamos.",
    );
    await revisarAccesibilidad(page);
    await page.goto("/app/categorias");
    await expect(page.getByRole("region", { name: "Reglas" })).toContainText(
      "Si es un ingreso de «CARLOS RUIZ EJEMPLO» por $400.000, va a Préstamos",
    );
  });
});

test("el número de pendientes es el mismo en Inicio y en Movimientos, también en un mes pasado", async ({ page }) => {
  await entrar(page, `/app/?mes=${ANTERIOR}`);
  await reiniciarDatos(page);
  await page.reload();
  await expect(page.getByRole("region", { name: /movimientos? sin categorizar$/ })).toHaveAccessibleName(
    "5 movimientos sin categorizar",
  );
  await page.goto(`/app/movimientos?mes=${ANTERIOR}`);
  await expect(page.getByRole("button", { name: "Sin categorizar (5)" })).toBeVisible();
  await expect(fila(page, "CAFETERIA EL PARQUE EJEMPLO")).toContainText("Sin categorizar");
});

// Accesibilidad: la lista, la bandeja y el resultado de categorizar; celular y computador; claro y oscuro.
for (const tamano of Object.keys(TAMANOS) as Tamano[]) {
  for (const modo of ["claro", "oscuro"] as Modo[]) {
    test(`accesibilidad de Movimientos ${tamano} ${modo}`, async ({ page }) => {
      await page.setViewportSize(TAMANOS[tamano]);
      await prepararModo(page, modo);
      await abrirMovimientos(page);
      await revisarAccesibilidad(page);
      await page.getByRole("button", { name: /^Sin categorizar \(\d+\)$/ }).click();
      await expect(page.getByRole("group", { name: OPCIONES })).toHaveCount(5);
      await revisarAccesibilidad(page);
      await fila(page, "PANADERIA EL TRIGAL").getByRole("button", { name: "Mercado" }).click();
      await expect(fila(page, "PANADERIA EL TRIGAL").getByRole("status")).toBeVisible();
      await revisarAccesibilidad(page);
      // Ítem 17: las tres ofertas de regla de una transferencia.
      await fila(page, "LAURA GÓMEZ EJEMPLO").getByRole("button", { name: "Restaurantes" }).click();
      await expect(fila(page, "LAURA GÓMEZ EJEMPLO").getByRole("status").getByRole("button")).toHaveCount(3);
      await revisarAccesibilidad(page);
    });
  }
}
