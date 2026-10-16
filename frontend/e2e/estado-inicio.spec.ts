import { fileURLToPath } from "node:url";
import type { components } from "../src/api/esquema";
import type { Page, Request } from "@playwright/test";
import { entrar, expect, revisarAccesibilidad, TAMANOS, test } from "./ayudas";

type Estado = components["schemas"]["EstadoInicio"];

// Peticiones a /api/ que la página lanzó y aún no terminan. Se espera a que no
// quede ninguna en vez de usar `networkidle`, que cuenta cualquier petición de
// la página y en el CI a veces nunca llegaba: la prueba se cortaba a los 30 s
// sin decir qué esperaba. Como `networkidle`, exige 500 ms sin ninguna: así no
// se cuela entre dos peticiones encadenadas. Si una se cuelga, el mensaje la nombra.
const pendientes = new WeakMap<Page, { enCurso: Set<Request>; todas: Set<Request>; ultimoCambio: number }>();

async function esperarApiQuieta(page: Page): Promise<void> {
  const red = pendientes.get(page)!;
  const sinTerminar = () => {
    if (red.enCurso.size > 0) return [...red.enCurso].map((p) => `${p.method()} ${new URL(p.url()).pathname}`);
    return Date.now() - red.ultimoCambio < 500 ? ["(menos de 500 ms sin peticiones)"] : [];
  };
  await expect.poll(sinTerminar, { message: "peticiones a /api/ sin terminar", timeout: 15_000 }).toEqual([]);
}

test.beforeEach(async ({ page }) => {
  const red = { enCurso: new Set<Request>(), todas: new Set<Request>(), ultimoCambio: Date.now() };
  pendientes.set(page, red);
  page.on("request", (peticion) => {
    red.todas.add(peticion);
    if (!new URL(peticion.url()).pathname.startsWith("/api/")) return;
    red.enCurso.add(peticion);
    red.ultimoCambio = Date.now();
  });
  const terminar = (peticion: Request) => {
    red.todas.delete(peticion);
    if (red.enCurso.delete(peticion)) red.ultimoCambio = Date.now();
  };
  page.on("requestfinished", terminar);
  page.on("requestfailed", terminar);
});

test.afterEach(async ({ page, baseURL }, info) => {
  // Diagnóstico de la intermitencia: si la prueba falla, deja escrito qué
  // peticiones de la página (de la API o no: fuentes, service worker…) seguían abiertas.
  if (info.status !== info.expectedStatus) {
    const abiertas = [...pendientes.get(page)!.todas].map((p) => `${p.method()} ${p.url()} (${p.resourceType()}${p.serviceWorker() ? ", service worker" : ""})`);
    await info.attach("peticiones-abiertas", { body: abiertas.join("\n") || "(ninguna)", contentType: "text/plain" });
    console.log(`Peticiones abiertas al fallar:\n${abiertas.join("\n") || "(ninguna)"}`);
  }
  await esperarApiQuieta(page);
  await page.request.get("/e2e/gmail/ok");
  const sesion = await page.request.get("/api/sesion");
  if (sesion.ok()) {
    const datos: components["schemas"]["Sesion"] = await sesion.json();
    await page.request.post("/api/sincronizacion", { headers: { "X-CSRF-Token": datos.csrf_token, "Content-Type": "application/json", Origin: baseURL! } });
  }
  expect((await page.request.get("/e2e/datos/reiniciar")).ok()).toBe(true);
});

test("Inicio muestra estado del servidor, error con reintento, desglose real y recarga tras sincronizar", async ({ page }) => {
  const alDia: Estado = { todo_al_dia: true, total_acciones: 0, texto: "Todo al día", areas: [] };
  await page.route("**/api/inicio/estado", (ruta) => ruta.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(alDia) }), { times: 1 });
  await entrar(page);
  await expect(page.getByText("Todo al día", { exact: true })).toBeVisible();
  await esperarApiQuieta(page);
  await revisarAccesibilidad(page);
  await page.route("**/api/inicio/estado", (ruta) => ruta.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detalle: "Falla inventada de consulta." }) }), { times: 1 });
  await page.reload();
  await expect(page.getByText(/No se pudieron consultar las revisiones/)).toBeVisible();
  await expect(page.getByText("Todo al día", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Volver a consultar las revisiones" }).click();
  const antes: Estado = await (await page.request.get("/api/inicio/estado")).json();
  await expect(page.getByText(antes.texto, { exact: true })).toBeVisible();
  await page.getByText(antes.texto, { exact: true }).click();
  const lista = page.getByRole("list", { name: "Revisiones pendientes" });
  for (const area of antes.areas) await expect(lista.getByRole("link", { name: `${area.titulo}: ${area.cantidad}`, exact: true })).toHaveAttribute("href", `/app${area.href}`);
  await expect(lista.getByRole("link")).toHaveCount(antes.areas.length);
  await revisarAccesibilidad(page);
  if (process.env.CAPTURAS_38) {
    for (const [tamano, medidas] of Object.entries(TAMANOS)) for (const modo of ["claro", "oscuro"]) {
      await esperarApiQuieta(page);
      await page.setViewportSize(medidas);
      await page.evaluate((tema) => document.documentElement.setAttribute("data-tema", tema), modo);
      await revisarAccesibilidad(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      const alto = await page.evaluate(() => document.documentElement.scrollHeight);
      await page.setViewportSize({ width: medidas.width, height: Math.max(alto, medidas.height) });
      await page.screenshot({ path: fileURLToPath(new URL(`../capturas/02-inicio-${tamano}-${modo}.png`, import.meta.url)), fullPage: true, animations: "disabled" });
    }
  }
  await esperarApiQuieta(page);
  expect((await page.request.get("/e2e/gmail/revocado")).ok()).toBe(true);
  let liberar!: () => void;
  const espera = new Promise<void>((resolver) => { liberar = resolver; });
  await page.route("**/api/sincronizacion", async (ruta) => { await espera; await ruta.continue(); }, { times: 1 });
  const sincronizada = page.waitForResponse((respuesta) => respuesta.url().endsWith("/api/sincronizacion") && respuesta.request().method() === "POST");
  await page.getByRole("button", { name: "Sincronizar ahora", exact: true }).first().click();
  await expect(page.getByText("Consultando las revisiones…", { exact: true })).toBeVisible();
  liberar();
  await sincronizada;
  const despues: Estado = await (await page.request.get("/api/inicio/estado")).json();
  await expect(page.getByText(despues.texto, { exact: true })).toBeVisible();
  await expect(page.getByText(antes.texto, { exact: true })).toHaveCount(0);
  expect(despues.areas.some((area) => area.codigo === "sincronizacion_fallida")).toBe(true);
  await revisarAccesibilidad(page);
});
