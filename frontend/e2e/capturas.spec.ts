/**
 * Capturas para revisión visual local (npm run capturas).
 * No se versionan ni se suben automáticamente como artefactos
 * (ver .gitignore y frontend/README.md). Solo datos inventados
 * (scripts/servidor_e2e.py).
 * Salen en frontend/capturas/NN-pantalla-{celular|computador}-{claro|oscuro}.png.
 */
import { fileURLToPath } from "node:url";
import { mesActualColombia } from "../src/compartido/formatos/formato";
import { entrar, expect, prepararModo, TAMANOS, test, type Modo, type Tamano } from "./ayudas";

const CARPETA = fileURLToPath(new URL("../capturas/", import.meta.url));

type Pagina = import("@playwright/test").Page;

function mesAntes(mes: string, cuantos: number): string {
  const [anio, numero] = mes.split("-").map(Number) as [number, number];
  const total = anio * 12 + (numero - 1) - cuantos;
  return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}`;
}
/** Mes pasado con datos (ingreso y ajuste entre los últimos) y uno sin movimientos. */
const MES_PASADO = mesAntes(mesActualColombia(), 1);
const MES_VACIO = mesAntes(mesActualColombia(), 3);

const CAPTURAS: {
  nombre: string;
  ruta: string;
  sinSesion?: boolean;
  /** Antes de abrir la ruta (p. ej. simular un fallo de red) y para deshacerlo. */
  preparar?: (page: Pagina) => Promise<void>;
  limpiar?: (page: Pagina) => Promise<void>;
  /** Qué hacer antes de capturar (y `despues`, para dejarlo como estaba). */
  antes?: (page: Pagina) => Promise<void>;
  despues?: (page: Pagina) => Promise<void>;
}[] = [
  { nombre: "01-entrar", ruta: "/app/", sinSesion: true },
  { nombre: "02-inicio", ruta: "/app/", antes: esperarInicio },
  {
    nombre: "02b-inicio-grafico-dona",
    ruta: "/app/",
    antes: async (page) => {
      await esperarInicio(page);
      await page.getByRole("button", { name: "Dona" }).click();
    },
    despues: async (page) => {
      await page.getByRole("button", { name: "Barras" }).click();
    },
  },
  {
    nombre: "02c-inicio-error-sincronizacion",
    ruta: "/app/",
    antes: async (page) => {
      await esperarInicio(page);
      await page.request.get("/e2e/gmail/revocado");
      await page.getByRole("main").getByRole("button", { name: "Sincronizar ahora" }).first().click();
      await expect(page.getByRole("alert")).toBeVisible();
    },
    despues: async (page) => {
      await page.request.get("/e2e/gmail/ok");
      await page.getByRole("main").getByRole("button", { name: "Sincronizar ahora" }).first().click();
      await expect(page.getByRole("alert")).toHaveCount(0);
    },
  },
  {
    // Ítem 38: el resultado de la sincronización que se lanza sola al abrir.
    nombre: "02g-inicio-sincroniza-al-abrir",
    ruta: "/app/",
    antes: async (page) => {
      await esperarInicio(page);
      expect((await page.request.get("/e2e/datos/sincronizacion-vieja")).ok()).toBe(true);
      await page.reload();
      await expect(page.getByRole("main").getByRole("status").filter({ hasText: "Sincronización terminada" })).toContainText("Sincronización terminada");
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: reiniciarDatos,
  },
  { nombre: "02d-inicio-mes-pasado", ruta: `/app/?mes=${MES_PASADO}`, antes: esperarInicio },
  {
    nombre: "02e-inicio-mes-sin-movimientos",
    ruta: `/app/?mes=${MES_VACIO}`,
    antes: async (page) => {
      await expect(page.getByRole("heading", { level: 2, name: /^Sin movimientos en / })).toBeVisible();
    },
  },
  {
    nombre: "02f-inicio-sin-conexion",
    ruta: "/app/",
    preparar: async (page) => {
      await page.route("**/api/reporte**", (r) => r.abort("internetdisconnected"));
    },
    limpiar: (page) => page.unroute("**/api/reporte**"),
    antes: async (page) => {
      await expect(page.getByRole("button", { name: "Volver a intentar" })).toBeVisible();
    },
  },
  { nombre: "03-mas", ruta: "/app/mas" },
  // Saldo (ítem 16): con los dos ingresos a mano de /e2e/datos/saldo; borrar no se confirma.
  {
    nombre: "11-saldo",
    ruta: "/app/saldo",
    antes: async (page) => {
      await datosDeSaldo(page);
      await page.getByText("Ver cómo se calcula").click();
    },
    despues: reiniciarDatos,
  },
  {
    // Ítem 38: borrar un ingreso no se confirma; el aviso ofrece «Deshacer».
    nombre: "11b-saldo-borrar",
    ruta: "/app/saldo",
    antes: async (page) => {
      await datosDeSaldo(page);
      await page.getByRole("button", { name: "Borrar ingreso Efectivo venta de libros EJEMPLO" }).click();
      const lista = page.getByRole("region", { name: /^Ingresos y ajustes de / });
      await expect(lista.getByRole("button", { name: "Deshacer" })).toBeVisible();
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: reiniciarDatos,
  },
  {
    // Ítem 38: el 410 de «Deshacer» (ya pasó el tiempo o ya se usó).
    nombre: "11g-saldo-ya-no-se-puede-deshacer",
    ruta: "/app/saldo",
    antes: async (page) => {
      await datosDeSaldo(page);
      await page.route("**/api/deshacer", (ruta) =>
        ruta.fulfill({
          status: 410,
          contentType: "application/json",
          body: JSON.stringify({ detalle: "Ya no se puede deshacer: pasó el tiempo o ya se deshizo." }),
        }),
      );
      await page.getByRole("button", { name: "Borrar ingreso Efectivo venta de libros EJEMPLO" }).click();
      await page.getByRole("button", { name: "Deshacer" }).click();
      await expect(page.getByRole("alert")).toBeVisible();
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: async (page) => {
      await page.unroute("**/api/deshacer");
      await reiniciarDatos(page);
    },
  },
  {
    nombre: "11c-saldo-errores-y-resultado",
    ruta: "/app/saldo",
    antes: async (page) => {
      await datosDeSaldo(page);
      const ingreso = page.getByRole("region", { name: "Registrar un ingreso" });
      await ingreso.getByLabel("Monto en pesos").fill("150.000");
      await ingreso.getByLabel("Descripción (opcional)").fill("Efectivo de una venta EJEMPLO");
      await ingreso.getByRole("button", { name: "Registrar ingreso" }).click();
      await expect(ingreso.getByRole("status")).toBeVisible();
      const ajuste = page.getByRole("region", { name: "Ajustar el saldo" });
      await ajuste.getByLabel("Saldo real en Bancolombia").fill("4.73O.000");
      await ajuste.getByRole("button", { name: "Ajustar saldo" }).click();
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: reiniciarDatos,
  },
  // Configurar saldo (ítem 16): sin saldo ni movimientos (/e2e/datos/sin-saldo) y fijo (datos de arranque).
  {
    nombre: "11d-configurar-saldo",
    ruta: "/app/saldo/configurar",
    antes: sinSaldo,
    despues: reiniciarDatos,
  },
  {
    nombre: "11e-configurar-saldo-error",
    ruta: "/app/saldo/configurar",
    antes: async (page) => {
      await sinSaldo(page);
      const hoja = page.getByRole("region", { name: "Tu punto de partida" });
      await hoja.getByLabel("Saldo inicial en pesos").fill("1.25O.000");
      await hoja.getByLabel("Fecha de inicio").fill(await mananaColombia(page));
      await hoja.getByRole("button", { name: "Guardar saldo inicial" }).click();
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: reiniciarDatos,
  },
  {
    nombre: "11f-configurar-saldo-fijo",
    ruta: "/app/saldo/configurar",
    antes: async (page) => {
      await expect(page.getByRole("link", { name: "Ajustar el saldo" })).toBeVisible();
    },
  },
  { nombre: "05-no-existe", ruta: "/app/esta-pagina-no-existe" },
  // Movimientos (ítem 14). Categorizar cambia datos: se reinician antes y después.
  { nombre: "08-movimientos", ruta: "/app/movimientos", antes: esperarMovimientos },
  {
    nombre: "08b-movimientos-sin-categorizar",
    ruta: "/app/movimientos?ver=sin-categorizar",
    antes: esperarMovimientos,
  },
  {
    // Ítem 38: los pendientes iguales, agrupados («20 veces») y categorizables con un toque.
    nombre: "08i-sin-categorizar-grupos",
    ruta: "/app/movimientos?ver=sin-categorizar",
    antes: async (page) => {
      await datosConGrupo(page);
    },
    despues: reiniciarDatos,
  },
  {
    nombre: "08j-sin-categorizar-grupo-opciones",
    ruta: "/app/movimientos?ver=sin-categorizar",
    antes: async (page) => {
      await datosConGrupo(page);
      await page.getByRole("button", { name: /^Categorizar las 20/ }).click();
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: reiniciarDatos,
  },
  {
    nombre: "08k-sin-categorizar-grupo-categorizado",
    ruta: "/app/movimientos?ver=sin-categorizar",
    antes: async (page) => {
      await datosConGrupo(page);
      await page.getByRole("button", { name: /^Categorizar las 20/ }).click();
      await page.getByRole("group", { name: /¿En qué categoría van las 20\?/ }).getByRole("button", { name: "Transporte" }).click();
      await expect(page.getByRole("region", { name: "Movimientos que se repiten" }).getByRole("status")).toBeVisible();
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: reiniciarDatos,
  },
  {
    nombre: "08c-movimientos-guardado-con-regla",
    ruta: "/app/movimientos",
    antes: async (page) => {
      await esperarMovimientos(page);
      await filaMovimiento(page, "PANADERIA EL TRIGAL").getByRole("button", { name: "Mercado" }).click();
      await expect(filaMovimiento(page, "PANADERIA EL TRIGAL").getByRole("status")).toBeVisible();
      // El foco va al aviso; se quita para que la captura no muestre el anillo.
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: reiniciarDatos,
  },
  {
    nombre: "08d-movimientos-cambiar",
    ruta: "/app/movimientos",
    antes: async (page) => {
      await esperarMovimientos(page);
      await page.getByRole("button", { name: "Cambiar categoría de SUPERMERCADO LA ESPIGA" }).click();
    },
  },
  {
    nombre: "08e-movimientos-filtro-vacio",
    ruta: `/app/movimientos?mes=${MES_PASADO}&ver=gastos&categoria=5`,
    antes: async (page) => {
      await expect(page.getByRole("heading", { level: 2, name: "Nada con este filtro" })).toBeVisible();
    },
  },
  {
    nombre: "08f-movimientos-todo-categorizado",
    ruta: "/app/movimientos?ver=sin-categorizar",
    // La bandeja es de todos los meses y los datos inventados tienen pendientes: se simula vacía.
    preparar: async (page) => {
      await page.route("**/api/movimientos/sin-categorizar", (r) =>
        r.fulfill({ status: 200, contentType: "application/json", body: '{"total":0,"movimientos":[],"grupos":[]}' }),
      );
    },
    limpiar: (page) => page.unroute("**/api/movimientos/sin-categorizar"),
    antes: async (page) => {
      await expect(page.getByRole("heading", { level: 2, name: "Todo categorizado" })).toBeVisible();
    },
  },
  // Reglas combinables (ítem 17): dos transferencias inventadas de $3.200 a cuentas
  // distintas; se ofrecen las tres reglas, se crea la de monto y se ve en las dos pantallas.
  {
    nombre: "08g-movimientos-ofertas-de-regla",
    ruta: "/app/movimientos?ver=sin-categorizar",
    antes: async (page) => {
      await reiniciarDatos(page);
      expect((await page.request.get("/e2e/datos/buses")).ok()).toBe(true);
      await page.reload();
      await esperarMovimientos(page);
      await filaMovimiento(page, "*3000000002").getByRole("button", { name: "Transporte" }).click();
      await expect(filaMovimiento(page, "*3000000002").getByRole("status").getByRole("button")).toHaveCount(3);
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: async (page) => {
      const bus = filaMovimiento(page, "*3000000002");
      await bus.getByRole("button", { name: "Transferencias de $3.200" }).click();
      await expect(bus.getByRole("status")).toContainText("Regla creada");
    },
  },
  { nombre: "08h-movimientos-por-regla-de-monto", ruta: "/app/movimientos", antes: esperarMovimientos },
  {
    nombre: "10d-categorias-regla-por-monto",
    ruta: "/app/categorias",
    antes: async (page) => {
      await esperarCategorias(page);
      await expect(page.getByRole("region", { name: "Reglas" })).toContainText("transferencia de $3.200");
    },
    despues: reiniciarDatos,
  },
  // Categorías y reglas (ítem 15). Crear y borrar no se confirman: los datos no cambian.
  { nombre: "10-categorias", ruta: "/app/categorias", antes: esperarCategorias },
  {
    nombre: "10b-categorias-borrar",
    ruta: "/app/categorias",
    antes: async (page) => {
      await esperarCategorias(page);
      await page.getByRole("button", { name: "Editar Antojos" }).click();
      await page.getByRole("dialog").getByRole("button", { name: "Borrar categoría" }).click();
      await expect(page.getByRole("dialog", { name: "Borrar la categoría Antojos" })).toBeVisible();
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: async (page) => {
      await page.keyboard.press("Escape");
    },
  },
  {
    // Ítem 38: una categoría sin movimientos ni reglas se borra al tocar; el aviso ofrece «Deshacer».
    nombre: "10e-categorias-borrar-deshacer",
    ruta: "/app/categorias",
    antes: async (page) => {
      await esperarCategorias(page);
      await page.getByRole("button", { name: "Editar Préstamos" }).click();
      await page.getByRole("dialog").getByRole("button", { name: "Borrar categoría" }).click();
      await expect(page.getByRole("status").getByRole("button", { name: "Deshacer" })).toBeVisible();
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: reiniciarDatos,
  },
  {
    nombre: "10f-categorias-regla-borrada-deshacer",
    ruta: "/app/categorias",
    antes: async (page) => {
      await esperarCategorias(page);
      await page
        .getByRole("region", { name: "Reglas" })
        .getByRole("listitem")
        .filter({ hasText: "«SUPERMERCADO LA ESPIGA»" })
        .getByRole("button", { name: "Borrar regla" })
        .click();
      await expect(page.getByRole("status").getByRole("button", { name: "Deshacer" })).toBeVisible();
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: reiniciarDatos,
  },
  {
    nombre: "10c-categorias-crear",
    ruta: "/app/categorias",
    antes: async (page) => {
      await esperarCategorias(page);
      await page.getByRole("button", { name: "Nueva categoría" }).click();
      const dialogo = page.getByRole("dialog", { name: "Nueva categoría" });
      await dialogo.getByLabel("Nombre").fill("Arriendos cobrados");
      await dialogo.locator("label", { has: page.getByRole("radio", { name: "Ingreso", exact: true }) }).click();
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: async (page) => {
      await page.keyboard.press("Escape");
    },
  },
  // Correos no reconocidos (ítem 19). Reprocesar cambia datos: se reinician después.
  { nombre: "09-no-reconocidos", ruta: "/app/no-reconocidos", antes: esperarNoReconocidos },
  {
    nombre: "09b-no-reconocidos-resultado",
    ruta: "/app/no-reconocidos",
    antes: async (page) => {
      await esperarNoReconocidos(page);
      await page.getByRole("button", { name: "Volver a procesar todos" }).click();
      await expect(page.getByRole("status")).toBeVisible();
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: reiniciarDatos,
  },
  {
    nombre: "09c-no-reconocidos-vacio",
    ruta: "/app/no-reconocidos",
    preparar: async (page) => {
      await page.route("**/api/no-reconocidos", (r) =>
        r.request().method() === "GET"
          ? r.fulfill({ status: 200, contentType: "application/json", body: '{"correos":[]}' })
          : r.continue(),
      );
    },
    limpiar: (page) => page.unroute("**/api/no-reconocidos"),
    antes: async (page) => {
      await expect(page.getByRole("heading", { level: 2, name: "No hay correos sin reconocer" })).toBeVisible();
    },
  },
  {
    nombre: "09d-no-reconocidos-error-al-cargar",
    ruta: "/app/no-reconocidos",
    preparar: async (page) => {
      await page.route("**/api/no-reconocidos", (r) => r.abort("internetdisconnected"));
    },
    limpiar: (page) => page.unroute("**/api/no-reconocidos"),
    antes: async (page) => {
      await expect(page.getByRole("button", { name: "Volver a intentar" })).toBeVisible();
    },
  },
  {
    nombre: "09e-no-reconocidos-error-al-reprocesar",
    ruta: "/app/no-reconocidos",
    antes: async (page) => {
      await esperarNoReconocidos(page);
      await page.request.get("/e2e/gmail/revocado");
      await page.getByRole("button", { name: "Volver a procesar todos" }).click();
      await expect(page.getByRole("alert")).toBeVisible();
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
    despues: async (page) => {
      await page.request.get("/e2e/gmail/ok");
    },
  },
  {
    nombre: "06-sin-conexion-al-abrir",
    ruta: "/app/",
    preparar: async (page) => {
      await page.route("**/api/sesion", (r) => r.abort("internetdisconnected"));
    },
    limpiar: (page) => page.unroute("**/api/sesion"),
    antes: async (page) => {
      await expect(page.getByRole("button", { name: "Volver a intentar" })).toBeVisible();
    },
  },
  {
    nombre: "07-error-al-abrir",
    ruta: "/app/",
    preparar: async (page) => {
      await page.route("**/api/sesion", (r) =>
        r.fulfill({ status: 500, contentType: "application/json", body: "{}" }),
      );
    },
    limpiar: (page) => page.unroute("**/api/sesion"),
    antes: async (page) => {
      await expect(page.getByRole("button", { name: "Volver a intentar" })).toBeVisible();
    },
  },
];

/** Los datos de Saldo (ítem 16) y la pantalla vuelta a leer con ellos. */
async function datosDeSaldo(page: Pagina): Promise<void> {
  expect((await page.request.get("/e2e/datos/saldo")).ok()).toBe(true);
  await page.reload();
  await expect(page.getByRole("region", { name: "Registrar un ingreso" })).toBeVisible();
}

/** Ítem 38: 20 compras iguales pendientes (un grupo) y la bandeja vuelta a leer con ellas. */
async function datosConGrupo(page: Pagina): Promise<void> {
  expect((await page.request.get("/e2e/datos/grupos")).ok()).toBe(true);
  await page.reload();
  await expect(page.getByRole("region", { name: "Movimientos que se repiten" })).toBeVisible();
}

/** Sin saldo configurado ni movimientos, y "Configurar saldo" vuelta a leer. */
async function sinSaldo(page: Pagina): Promise<void> {
  expect((await page.request.get("/e2e/datos/sin-saldo")).ok()).toBe(true);
  await page.reload();
  await expect(page.getByRole("button", { name: "Guardar saldo inicial" })).toBeVisible();
}

/** Mañana en Colombia ("AAAA-MM-DD"), a partir del `hoy` de la API. */
async function mananaColombia(page: Pagina): Promise<string> {
  const { hoy } = (await (await page.request.get("/api/saldo")).json()) as { hoy: string };
  const [a, m, d] = hoy.split("-").map(Number) as [number, number, number];
  return new Date(Date.UTC(a, m - 1, d + 1)).toISOString().slice(0, 10);
}

async function reiniciarDatos(page: Pagina): Promise<void> {
  expect((await page.request.get("/e2e/datos/reiniciar")).ok()).toBe(true);
}

async function esperarMovimientos(page: Pagina): Promise<void> {
  await expect(page.getByRole("list", { name: /^Movimientos .*, por día$/ })).toBeVisible();
}

/** La fila de un movimiento (el `li` más interno con su descripción). */
function filaMovimiento(page: Pagina, descripcion: string) {
  return page.getByRole("listitem").filter({ has: page.getByText(descripcion, { exact: true }) }).last();
}

async function esperarCategorias(page: Pagina): Promise<void> {
  await expect(page.getByRole("region", { name: "Reglas" })).toBeVisible();
}

async function esperarNoReconocidos(page: Pagina): Promise<void> {
  await expect(page.getByRole("heading", { level: 2, name: "3 correos" })).toBeVisible();
}

async function esperarInicio(page: Pagina): Promise<void> {
  await expect(page.getByRole("region", { name: /^Resumen de / })).toBeVisible();
}

for (const tamano of Object.keys(TAMANOS) as Tamano[]) {
  for (const modo of ["claro", "oscuro"] as Modo[]) {
    test(`capturas ${tamano} ${modo}`, async ({ page }) => {
      await page.setViewportSize(TAMANOS[tamano]);
      await prepararModo(page, modo);
      for (const { nombre, ruta, sinSesion, preparar, limpiar, antes, despues } of CAPTURAS) {
        // Diagnóstico local de un escenario; sin filtro, CI conserva todos.
        if (process.env.CAPTURA_SOLO && nombre !== process.env.CAPTURA_SOLO) continue;
        await preparar?.(page);
        if (sinSesion || preparar) await page.goto(ruta);
        else if (!page.url().includes("/app/") || (await page.getByLabel("Contraseña").count()))
          await entrar(page, ruta);
        else await page.goto(ruta);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await antes?.(page);
        await page.evaluate(() => document.fonts.ready);
        // Puntero fuera de todo: que ningún elemento salga con el estilo de hover.
        await page.mouse.move(0, 0);
        // Página completa con la ventana del alto de la página: así la barra
        // inferior fija del celular queda al pie (como en el prototipo) y no
        // a mitad de la captura. No se inyectan estilos (la CSP no lo deja).
        const alto = await page.evaluate(() => document.documentElement.scrollHeight);
        await page.setViewportSize({ width: TAMANOS[tamano].width, height: Math.max(alto, TAMANOS[tamano].height) });
        await page.screenshot({
          path: `${CARPETA}${nombre}-${tamano}-${modo}.png`,
          animations: "disabled",
        });
        await page.setViewportSize(TAMANOS[tamano]);
        await despues?.(page);
        await limpiar?.(page);
      }
    });
  }
}
