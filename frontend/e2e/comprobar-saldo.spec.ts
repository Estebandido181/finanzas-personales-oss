import { fileURLToPath } from "node:url";
import { entrar, expect, revisarAccesibilidad, TAMANOS, test } from "./ayudas";
import { elegirReporte } from "./excel-inventado";
import { pesos } from "../src/compartido/formatos/formato";
import type { components } from "../src/api/esquema";

type Saldo = components["schemas"]["Saldo"];
type Comprobacion = components["schemas"]["ComprobacionSaldo"];
const etiqueta = "Escribe el saldo que ves ahora en Bancolombia";

test.afterEach(async ({ page, request }) => {
  await page.waitForLoadState("networkidle");
  expect((await request.get("/e2e/datos/reiniciar")).ok()).toBe(true);
});

test("comprobar un centavo en Saldo no ajusta; editar y registrar ingreso invalidan el diagnóstico", async ({ page, request }) => {
  expect((await request.get("/e2e/datos/saldo")).ok()).toBe(true);
  await entrar(page, "/app/saldo");
  await page.waitForLoadState("networkidle");
  const antes: Saldo = await (await page.request.get("/api/saldo")).json();
  const comprobador = page.getByRole("region", { name: "Comprobar saldo", exact: true });
  await comprobador.getByLabel(etiqueta).fill(pesos(antes.saldo_centavos! + 1).slice(1));
  const respuesta = page.waitForResponse((r) => r.url().endsWith("/api/saldo/comprobar") && r.request().method() === "POST");
  await comprobador.getByRole("button", { name: "Comprobar saldo" }).click();
  const dato: Comprobacion = await (await respuesta).json();
  expect(dato.diferencia_centavos).toBe(1);
  await expect(comprobador.getByText("+$0,01", { exact: true })).toBeVisible();
  expect((await (await page.request.get("/api/saldo")).json() as Saldo).saldo_centavos).toBe(antes.saldo_centavos);
  await revisarAccesibilidad(page);
  if (process.env.CAPTURAS_COMPROBACION) {
    for (const [tamano, medidas] of Object.entries(TAMANOS)) for (const modo of ["claro", "oscuro"]) {
      await page.waitForLoadState("networkidle");
      await page.setViewportSize(medidas);
      await page.evaluate((tema) => document.documentElement.setAttribute("data-tema", tema), modo);
      await revisarAccesibilidad(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      const alto = await page.evaluate(() => document.documentElement.scrollHeight);
      await page.setViewportSize({ width: medidas.width, height: Math.max(alto, medidas.height) });
      await page.screenshot({ path: fileURLToPath(new URL(`../capturas/11-saldo-${tamano}-${modo}.png`, import.meta.url)), fullPage: true, animations: "disabled" });
    }
  }
  await comprobador.getByLabel(etiqueta).fill(pesos(antes.saldo_centavos!).slice(1));
  await expect(comprobador.getByText("+$0,01", { exact: true })).toHaveCount(0);
  await comprobador.getByRole("button", { name: "Comprobar saldo" }).click();
  await expect(comprobador.getByText(/Los saldos coinciden.*no garantiza/)).toBeVisible();
  await page.waitForLoadState("networkidle");
  const ingreso = page.getByRole("region", { name: "Registrar un ingreso" });
  await ingreso.getByLabel("Monto en pesos").fill("1");
  await ingreso.getByRole("button", { name: "Registrar ingreso" }).click();
  await expect(ingreso.getByText(/Ingreso de.*registrado/)).toBeVisible();
  await expect(comprobador.getByText(/Los saldos coinciden/)).toHaveCount(0);
});

test("preview separa impacto y diferencia; comprobar no consume análisis y tras confirmar consulta saldo actual", async ({ page, request }) => {
  expect((await request.get("/e2e/datos/importacion")).ok()).toBe(true);
  await entrar(page, "/app/importar");
  const previa = page.waitForResponse((r) => r.url().endsWith("/api/importaciones/analizar"));
  await elegirReporte(page);
  const analisis: components["schemas"]["VistaPreviaImportacion"] = await (await previa).json();
  await page.getByLabel(etiqueta).fill(pesos(analisis.saldo_despues_centavos + 1).slice(1));
  const respuesta = page.waitForResponse((r) => r.url().endsWith("/api/saldo/comprobar"));
  await page.getByRole("button", { name: "Comprobar saldo" }).click();
  const diagnostico: Comprobacion = await (await respuesta).json();
  expect(diagnostico.diferencia_centavos).toBe(1);
  expect(diagnostico.efecto_conciliacion_centavos).toBe(analisis.diferencia_centavos);
  await expect(page.getByText("Impacto de esta importación", { exact: true })).toBeVisible();
  await expect(page.getByText("Resto sin explicar", { exact: true })).toBeVisible();
  await revisarAccesibilidad(page);
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Sí, importar" }).click();
  await page.getByRole("link", { name: "Ver el resultado de la importación" }).click();
  await expect(page.getByText("Impacto de esta importación", { exact: true })).toHaveCount(0);
  const saldo: Saldo = await (await page.request.get("/api/saldo")).json();
  await page.getByLabel(etiqueta).fill(pesos(saldo.saldo_centavos!).slice(1));
  const actual = page.waitForResponse((r) => r.url().endsWith("/api/saldo/comprobar"));
  await page.getByRole("button", { name: "Comprobar saldo" }).click();
  const nueva: Comprobacion = await (await actual).json();
  expect(nueva.origen).toBe("actual"); expect(nueva.diferencia_centavos).toBe(0);
  expect((await actual).request().postDataJSON()).not.toHaveProperty("token_analisis");
  await expect(page.getByText(/Los saldos coinciden.*no garantiza/)).toBeVisible();
  await revisarAccesibilidad(page);
});

test.describe("Errores inyectados de comprobación", () => {
  // page.route no intercepta solicitudes controladas por un service worker.
  // Sólo este caso de inyección HTTP usa un contexto sin service worker.
  test.use({ serviceWorkers: "block" });

test("409 y 410 al comprobar retiran la confirmación y exigen un análisis nuevo", async ({ page, request }) => {
  await page.addInitScript(() => {
    const registro = { iniciadas: 0, abortInicial: 0, abortPosterior: 0, rechazadas: 0,
      status: null as number | null, csrfPresente: false, payloadLeido: false,
      importeEsCero: false, tokenPresente: false, tipoImportacion: false };
    Object.assign(window, { __diagnosticoComprobacion: registro });
    const original = window.fetch.bind(window);
    window.fetch = (entrada, opciones) => {
      const url = new URL(entrada instanceof Request ? entrada.url : String(entrada), location.href);
      if (url.origin !== location.origin || url.pathname !== "/api/saldo/comprobar") return original(entrada, opciones);
      registro.iniciadas++;
      const peticion = entrada instanceof Request ? entrada : new Request(entrada, opciones);
      registro.csrfPresente = peticion.headers.has("X-CSRF-Token");
      if (peticion.signal.aborted) registro.abortInicial++;
      peticion.signal.addEventListener("abort", () => { registro.abortPosterior++; }, { once: true });
      void peticion.clone().json().then((cuerpo) => {
        registro.payloadLeido = true;
        registro.importeEsCero = cuerpo.saldo_real_centavos === 0;
        registro.tokenPresente = typeof cuerpo.token_analisis === "string" && cuerpo.token_analisis.length > 0;
        registro.tipoImportacion = cuerpo.tipo_analisis === "importacion";
      }, () => {});
      return original(entrada, opciones).then((respuesta) => {
        registro.status = respuesta.status;
        return respuesta;
      }, (error: unknown) => { registro.rechazadas++; throw error; });
    };
  });
  expect((await request.get("/e2e/datos/importacion")).ok()).toBe(true);
  await entrar(page, "/app/importar");
  await elegirReporte(page);
  for (const estado of [409, 410]) {
    await page.waitForLoadState("networkidle");
    await page.evaluate(() => {
      const registro = (window as unknown as { __diagnosticoComprobacion: Record<string, boolean | number | null> }).__diagnosticoComprobacion;
      for (const clave of ["iniciadas", "abortInicial", "abortPosterior", "rechazadas"]) registro[clave] = 0;
      for (const clave of ["csrfPresente", "payloadLeido", "importeEsCero", "tokenPresente", "tipoImportacion"]) registro[clave] = false;
      registro.status = null;
    });
    const eventos: string[] = [];
    const esComprobacion = (r: import("@playwright/test").Request) => new URL(r.url()).pathname === "/api/saldo/comprobar";
    page.on("request", (r) => { if (esComprobacion(r)) eventos.push(`request ${r.method()}`); });
    page.on("requestfailed", (r) => { if (esComprobacion(r)) eventos.push("requestfailed"); });
    page.on("pageerror", () => eventos.push("pageerror"));
    await page.route("**/api/saldo/comprobar", (ruta) => {
      eventos.push(`mock ${estado}`);
      return ruta.fulfill({ status: estado, contentType: "application/json", body: JSON.stringify({ detalle: "Revisión inventada obsoleta." }) });
    }, { times: 1 });
    const campo = page.getByLabel(etiqueta);
    const boton = page.getByRole("button", { name: "Comprobar saldo" });
    await campo.fill("0");
    await expect(campo).toHaveValue("0");
    await expect(boton).toBeEnabled();
    await campo.evaluate((elemento: HTMLInputElement) => {
      const form = elemento.form!;
      form.dataset.envios = "0";
      form.addEventListener("submit", (evento) => {
        form.dataset.envios = String(Number(form.dataset.envios) + 1);
        form.dataset.ceroEnviado = String(elemento.value === "0");
        form.dataset.valido = String(form.checkValidity());
        queueMicrotask(() => { form.dataset.reactAtendio = String(evento.defaultPrevented); });
      }, { capture: true });
    });
    // Verifica la inyección antes del mensaje: un fallo distingue el HTTP,
    // el token de la previa y la reacción de la pantalla.
    // La promesa se maneja desde su creación, incluso si falla el submit.
    const respuesta = page.waitForResponse((r) => r.url().endsWith("/api/saldo/comprobar") && r.request().method() === "POST")
      .then((r) => ({ respuesta: r }), (error: unknown) => ({ error }));
    const diagnosticar = async () => {
      const formulario = await campo.evaluate((elemento: HTMLInputElement) => ({
        valorEsCero: elemento.value === "0", deshabilitado: elemento.disabled,
        envios: elemento.form?.dataset.envios, ceroEnviado: elemento.form?.dataset.ceroEnviado,
        valido: elemento.form?.dataset.valido, reactAtendio: elemento.form?.dataset.reactAtendio,
        worker: !!navigator.serviceWorker.controller,
      })).catch(() => null);
      const fetch = await page.evaluate(() =>
        (window as unknown as { __diagnosticoComprobacion: Record<string, boolean | number | null> }).__diagnosticoComprobacion).catch(() => null);
      console.log("Diagnóstico de comprobación", { estado, eventos, formulario, fetch,
        enImportar: new URL(page.url()).pathname === "/app/importar", alertas: await page.getByRole("alert").count() });
    };
    let comprobacion: import("@playwright/test").Response;
    try {
      await boton.click();
      await expect(campo.locator("xpath=ancestor::form")).toHaveAttribute("data-envios", "1");
      await expect.poll(() => eventos).toContain(`mock ${estado}`);
      const recibida = await respuesta;
      if ("error" in recibida) throw recibida.error;
      comprobacion = recibida.respuesta;
      expect(comprobacion.status()).toBe(estado);
      const entrada = comprobacion.request().postDataJSON();
      expect(entrada.saldo_real_centavos).toBe(0);
      expect(typeof entrada.token_analisis).toBe("string");
      expect(entrada.tipo_analisis).toBe("importacion");
      await expect(page.getByText("La revisión cambió o venció. Vuelve a analizar el archivo antes de importar.", { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Sí, importar" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Comprobar saldo" })).toBeDisabled();
      await page.getByRole("button", { name: "Analizar otra vez" }).click();
      await expect(page.getByRole("button", { name: "Sí, importar" })).toBeVisible();
      await expect(page.getByLabel(etiqueta)).toHaveValue("");
    } catch (error) {
      await diagnosticar();
      throw error;
    }
  }
  await revisarAccesibilidad(page);
});
});
